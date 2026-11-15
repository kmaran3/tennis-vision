"""Provider protocol and local configuration regressions; no external calls."""
import json
import os
from pathlib import Path
import subprocess
import sys

import httpx
import pytest

from baseline import analyst
from baseline import provider,evaluation
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_tool_round_trip_preserves_ids_signatures_and_budget(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','offline-test-key')
    monkeypatch.setenv('GEMINI_FREE_TIER_CONFIRMED','true')
    requests=[]
    calls=[{'functionCall':{'name':'list_metrics','args':{},'id':f'call-{i}'},'thoughtSignature':f'signature-{i}'} for i in range(6)]
    def respond(request):
        payload=json.loads(request.content);requests.append(payload)
        if len(requests)==1:
            return httpx.Response(200,json={'candidates':[{'content':{'role':'model','parts':calls}}]})
        return httpx.Response(200,json={'candidates':[{'content':{'role':'model','parts':[{'text':'finished'}]}}]})
    client=httpx.AsyncClient
    monkeypatch.setattr(analyst.httpx,'AsyncClient',lambda **kwargs:client(transport=httpx.MockTransport(respond),**kwargs))
    result=await analyst.run_analyst('List supported metrics')
    assert result['tool_calls']==5 and len(result['evidence'])==5
    assert len(requests)==2 and 'tools' not in requests[1]
    assert requests[1]['contents'][1]['parts']==calls
    replies=requests[1]['contents'][2]['parts']
    assert [r['functionResponse']['id'] for r in replies]==[f'call-{i}' for i in range(6)]
    assert replies[-1]['functionResponse']['response']=={'error':'tool_budget_exhausted'}


def test_saved_configuration_wins_without_removing_other_shell_settings(tmp_path):
    path=tmp_path/'test.env';path.write_text('BASELINE_TEST_SETTING="saved value with spaces"\n')
    script=Path(__file__).resolve().parents[1]/'scripts/with_env.py'
    code='import os,json;print(json.dumps([os.environ["BASELINE_TEST_SETTING"],os.environ["BASELINE_UNMENTIONED"]]))'
    result=subprocess.run([sys.executable,str(script),'--env-file',str(path),'python','-c',code],env={**os.environ,'BASELINE_TEST_SETTING':'inherited','BASELINE_UNMENTIONED':'preserved'},capture_output=True,text=True,check=True)
    assert json.loads(result.stdout)==['saved value with spaces','preserved']


@pytest.mark.asyncio
async def test_provider_retries_same_model_with_a_finite_budget(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','offline-test-key');monkeypatch.setenv('GEMINI_FREE_TIER_CONFIRMED','true')
    requests=[];delays=[]
    def respond(request):
        requests.append(str(request.url))
        return httpx.Response(503,json={'error':{'status':'UNAVAILABLE'}}) if len(requests)<3 else httpx.Response(200,json={'candidates':[]})
    async def sleep(seconds):delays.append(seconds)
    client=httpx.AsyncClient
    monkeypatch.setattr(provider.httpx,'AsyncClient',lambda **kwargs:client(transport=httpx.MockTransport(respond),**kwargs))
    monkeypatch.setattr(provider.asyncio,'sleep',sleep)
    _,attempts=await provider.generate_content({'contents':[]})
    assert attempts==3 and delays==[2,4] and len(set(requests))==1


@pytest.mark.asyncio
async def test_provider_does_not_retry_exhausted_quota(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','offline-test-key');monkeypatch.setenv('GEMINI_FREE_TIER_CONFIRMED','true')
    requests=[]
    def respond(request):
        requests.append(request)
        return httpx.Response(429,json={'error':{'details':[{'violations':[{'quotaMetric':'free_requests','quotaValue':'20'}]}]}})
    client=httpx.AsyncClient
    monkeypatch.setattr(provider.httpx,'AsyncClient',lambda **kwargs:client(transport=httpx.MockTransport(respond),**kwargs))
    with pytest.raises(HTTPException) as failure:await provider.generate_content({'contents':[]})
    assert len(requests)==1 and failure.value.status_code==429
    assert failure.value.detail['quota_limits'][0]['quotaValue']=='20'


@pytest.mark.asyncio
async def test_evaluation_resumes_without_repeating_completed_provider_stages(tmp_path,monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','offline-test-key');monkeypatch.setenv('GEMINI_FREE_TIER_CONFIRMED','true')
    (tmp_path/'eval').mkdir();(tmp_path/'eval/questions-v1.json').write_text(json.dumps([{'id':'test','question':'An unsupported request','expected':{'behavior':'reject_unsupported'}}]))
    monkeypatch.setattr(evaluation,'ROOT',tmp_path);monkeypatch.setattr(evaluation,'ARTIFACTS',tmp_path/'artifacts')
    analyst_calls=[];provider_calls=[]
    async def run(question):
        analyst_calls.append(question);return {'answer':'unsupported','evidence':[],'tool_calls':0}
    async def generate(contents,system):
        provider_calls.append(contents)
        if len(provider_calls)==2:raise HTTPException(429,detail={'code':'quota_exhausted'})
        return ('CLARIFY' if len(provider_calls)==1 else '{}'),{'provider_requests':1,'token_usage':{}}
    monkeypatch.setattr(evaluation,'run_analyst',run);monkeypatch.setattr(evaluation,'provider',generate)
    await evaluation.evaluate()
    path=tmp_path/'artifacts/agent-evaluation.json';report=json.loads(path.read_text())
    assert report['status']=='paused_provider_quota' and report['pending']['baseline_sql']=='CLARIFY'
    await evaluation.evaluate();report=json.loads(path.read_text())
    assert report['status']=='completed_requires_review' and len(report['results'])==1
    assert len(analyst_calls)==1 and len(provider_calls)==3 and 'pending' not in report
