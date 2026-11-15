"""Resumable external analyst evaluation. Results are never fabricated offline."""
from __future__ import annotations
import json
import os
import time
import asyncio
from pathlib import Path
import httpx
from fastapi import HTTPException
from .config import ROOT,ARTIFACTS,write_json,connect,serving_path,records,digest
from .analyst import run_analyst,MODEL,tool
from .provider import generate_content

async def provider(contents,system):
    result,requests=await generate_content({"systemInstruction":{"parts":[{"text":system}]},"contents":[{"role":"user","parts":[{"text":contents}]}],"generationConfig":{"maxOutputTokens":2000,"thinkingConfig":{"thinkingLevel":"low"}}})
    candidates=result.get("candidates",[])
    text="".join(p.get("text","") for p in candidates[0].get("content",{}).get("parts",[])) if candidates else ""
    if not text:raise HTTPException(503,detail="Provider returned no evaluation answer")
    return text,{'provider_requests':requests,'token_usage':result.get('usageMetadata',{})}


def baseline_sql(sql):
    # This baseline is deliberately separate from the public tool dispatcher.
    import sqlglot
    from sqlglot import exp
    statements=sqlglot.parse(sql,read="duckdb")
    allowed={"player_matches","players","matches","rankings"}
    if len(statements)!=1 or not isinstance(statements[0],exp.Select):raise ValueError("Baseline requires a single SELECT")
    if any(t.name not in allowed for t in statements[0].find_all(exp.Table)):raise ValueError("Baseline table not allowlisted")
    if any(isinstance(t.this,exp.Func) for t in statements[0].find_all(exp.Table)):raise ValueError("No external table functions")
    con=connect(serving_path(),True)
    import threading
    timer=threading.Timer(10,con.interrupt);timer.daemon=True;timer.start()
    try:
        con.execute("SET enable_external_access=false")
        return records(con,"SELECT * FROM ("+statements[0].sql(dialect="duckdb")+") LIMIT 500")
    finally:timer.cancel();con.close()

async def evaluate():
    cases_path=ROOT/"eval/questions-v1.json";questions=json.loads(cases_path.read_text())
    path=ARTIFACTS/"agent-evaluation.json"
    checksum=digest(cases_path)
    report=json.loads(path.read_text()) if path.exists() else dict(dataset_sha256=checksum,results=[],status="pending")
    if report["dataset_sha256"]!=checksum:raise ValueError("Evaluation questions changed; start a separate versioned report")
    revision=digest(Path(__file__).with_name('analyst.py'))+':'+digest(Path(__file__).with_name('provider.py'))
    if report.get('agent_revision') not in (None,revision) and (report['results'] or report.get('pending')):
        write_json(ARTIFACTS/'evaluation-history'/f"{report['agent_revision'][:12]}-{time.time_ns()}.json",report)
        report=dict(dataset_sha256=checksum,results=[],status='pending')
    report.update(agent_revision=revision,model=MODEL)
    if not os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMINI_FREE_TIER_CONFIRMED")!="true":
        report.update(status="blocked_credentials",reason="No verified free-tier key with billing disabled; no live calls or measured accuracy.")
        write_json(path,report);print(report["reason"]);return
    done={r["id"] for r in report["results"]}
    report.pop('reason',None);report['status']='running';write_json(path,report)
    schema="""Return only one DuckDB SELECT, or CLARIFY if ambiguous/unsupported. No external access. Allowed marts: player_matches(player_id,tour,surface,season,level,observed_date,won,service_points,first_in,first_won,second_won,aces,double_faults,bp_saved,bp_faced,opp_service_points,opp_first_won,opp_second_won,opp_bp_saved,opp_bp_faced), players(player_id,tour,name), matches(match_id,tour,event,season,observed_date,winner_id,loser_id,score), rankings(player_id,tour,ranking_date,rank). Rates require ratio of summed valid numerator and denominator pairs. Limit results to 500."""
    for case in questions:
        if case["id"] in done:continue
        pending=report.get('pending',{})
        if pending.get('id')!=case['id']:pending={'id':case['id'],'stage_seconds':{}}
        report['pending']=pending
        print(f"Evaluating {case['id']} ({len(report['results'])}/{len(questions)} complete)",flush=True)
        try:
            if 'analyst' not in pending:
                started=time.monotonic();pending['analyst']=await run_analyst(case['question'])
                pending['stage_seconds']['analyst']=time.monotonic()-started;write_json(path,report)
            if 'baseline_sql' not in pending:
                started=time.monotonic();sql,usage=await provider(case['question'],schema)
                pending['baseline_sql']=sql.strip().removeprefix('```sql').removeprefix('```').removesuffix('```').strip()
                pending['baseline_usage']=usage;pending['stage_seconds']['baseline']=time.monotonic()-started;write_json(path,report)
            if 'baseline' not in pending:
                try:pending['baseline']=baseline_sql(pending['baseline_sql']) if pending['baseline_sql']!='CLARIFY' else 'CLARIFY'
                except Exception as e:pending['baseline']={'error':str(e)}
                write_json(path,report)
            expected=case['expected'];reference=None
            if all(k in expected for k in ('tour','start','end')) and ('metric' in expected or 'metrics' in expected):
                query={k:expected[k] for k in ('tour','start','end','surface','group_by') if k in expected}
                query['metrics']=expected.get('metrics',[expected.get('metric')])
                reference=tool('query_metrics',{'query':json.dumps(query)})
            started=time.monotonic()
            judgment,usage=await provider(json.dumps(dict(case=case,analyst=pending['analyst'],baseline=pending['baseline'],governed_reference=reference),default=str),"Grade the fixed tennis evaluation case. Return JSON with separate analyst and SQL-baseline grades for numerical_correctness, clarification, unsupported_request_handling, provenance, and comments. Use null when a dimension cannot be verified. Compare values, denominators and sample sizes against governed_reference when supplied. Do not infer a passing numerical grade without matching evidence and filters. Never change the question.")
            pending['stage_seconds']['judgment']=time.monotonic()-started
            result=dict(id=case['id'],analyst=pending['analyst'],baseline_sql=pending['baseline_sql'],baseline=pending['baseline'],judgment=judgment,governed_reference=reference,baseline_usage=pending['baseline_usage'],judgment_usage=usage,stage_seconds=pending['stage_seconds'],latency_seconds=sum(pending['stage_seconds'].values()))
            report["results"].append(result);report["status"]="running"
            report.pop('pending',None)
            write_json(path,report)
        except HTTPException as e:
            report.update(status="paused_provider_quota" if e.status_code==429 else "provider_unavailable",reason=e.detail);write_json(path,report);print(f"Evaluation paused: {report['status']}",flush=True);return
        except (TimeoutError,httpx.TimeoutException):
            report.update(status='provider_unavailable',reason={'code':'provider_timeout'});write_json(path,report);print('Evaluation paused: provider timeout',flush=True);return
    report["status"]="completed_requires_review";write_json(path,report)
