"""Auditable, checkpointed Slam/MCP replay using as-of serve/return priors."""
from __future__ import annotations
import gzip
import hashlib
import json
import re
import math
import pandas as pd
from .config import connect,records,ARTIFACTS,DATA,ROOT,write_json,digest,reserve
from .scoring import State,Rules,slam_rules
from .identity import normalize,event_name


def short_name_matches(source,canonical):
    if normalize(source)==normalize(canonical):return True
    if "." not in str(source):return False
    surname=str(source).split(".")[-1].strip()
    return bool(surname and normalize(canonical).endswith(normalize(surname)) and normalize(source)[0]==normalize(canonical)[0])


def serve_priors(feature,p1,p2):
    if not feature:return .62,.62,"Population Beta(31,19) backoff; no uniquely resolved as-of player history"
    a=feature["player_a"]
    def get(name,p):
        value=feature.get(name+("_a" if p==a else "_b"))
        return value if value is not None and math.isfinite(value) else None
    values=[]
    for p,opponent in ((p1,p2),(p2,p1)):
        own=get("serve",p);opp=get("return",opponent)
        observed=[v for v in (own,1-opp if opp is not None else None) if v is not None]
        # Shrink sparse/unavailable form toward the population prior.
        mean=(sum(observed)+.62)/(len(observed)+1)
        values.append(min(.85,max(.4,mean)))
    return *values,"As-of serve/return priors, shrunk to population 0.62; 50 effective service points; cutoff "+str(feature["feature_cutoff"])


def build_replays(limit=None):
    reserve(2)
    con=connect()
    snapshot=con.execute("SELECT snapshot FROM meta.build").fetchone()[0]
    code_hash="".join(digest(ROOT/p) for p in ("baseline/replay.py","baseline/scoring.py","baseline/temporal.py","baseline/charting.py","dbt/models/marts/matches.sql"))
    version=hashlib.sha256((snapshot+code_hash).encode()).hexdigest()[:16]
    cache_dir=DATA/"cache/replay"/version;cache_dir.mkdir(parents=True,exist_ok=True)
    features={f["match_id"]:f for f in records(con,"SELECT match_id,player_a,player_b,feature_cutoff,serve_a,serve_b,return_a,return_b FROM main.features")}
    canonical=records(con,"SELECT match_id,tour,season,event,winner_name,loser_name,winner_id,loser_id FROM main.matches WHERE level='G'")
    events={}
    for m in canonical:
        event=event_name(m["event"]);event="ausopen" if event=="australianopen" else event
        events.setdefault((m["tour"],m["season"],event),[]).append(m)
    chart_bridges={r["source_match_id"]:r for r in records(con,"SELECT * FROM main.chart_matches")}
    con.execute("CREATE OR REPLACE TABLE main.replay_points(match_id VARCHAR,point INT,probability DOUBLE,server INT,score VARCHAR,break_point BOOLEAN,set_point BOOLEAN,match_point BOOLEAN,large_change BOOLEAN,model_version VARCHAR,source_file VARCHAR,source_row BIGINT)")
    catalog=[];excluded=[];point_batch=[];point_count=0;processed=0
    def flush():
        if point_batch:
            con.register("replay_batch",pd.DataFrame(point_batch));con.execute("INSERT INTO main.replay_points BY NAME SELECT * FROM replay_batch");point_batch.clear()
    for source in ("slam","chart_atp","chart_wta"):
        metadata=records(con,f"SELECT * FROM raw.{source}_matches")
        chart=source!="slam"
        if chart:
            points=con.execute(f"SELECT * FROM raw.{source}_points WHERE PtWinner IN ('1','2') AND Svr IN ('1','2') ORDER BY match_id,try_cast(Pt AS INT),source_file,source_row").df()
        else:
            points=con.execute("SELECT * FROM raw.slam_points WHERE PointWinner IN ('1','2') AND PointServer IN ('1','2') ORDER BY match_id,try_cast(PointNumber AS INT),source_file,source_row").df()
        groups=points.groupby("match_id",sort=False)
        seen=set()
        for meta in metadata:
            mid=meta["match_id"];cache=None
            if mid in seen:continue
            seen.add(mid)
            if mid not in groups.indices:
                excluded.append(dict(match_id=("charting:" if chart else "slam:")+str(mid),reason="missing_point_records"))
                continue
            canonical_id=None;p1id=p2id=None
            try:
                if chart:
                    bridge=chart_bridges.get(mid)
                    if not bridge:raise ValueError("no_unique_main_tour_bridge")
                    tour=bridge["tour"];year=int(meta["Date"][:4]);event=meta["Tournament"]
                    if year<1980:raise ValueError("legacy_nonfinal_set_rules_require_verification")
                    p1,p2=meta["Player 1"],meta["Player 2"];p1id,p2id=bridge["player1"],bridge["player2"];canonical_id=bridge["match_id"]
                    code=str(meta.get("Final TB?","")).strip()
                    formats={"1":(6,7),"0":(None,7),"A":(6,10),"T":(12,7)}
                    if code not in formats:raise ValueError("unknown_scoring_rules")
                    at,target=formats[code];best=int(meta["Best of"])
                    if best not in (3,5):raise ValueError("unsupported_match_format")
                    rules=Rules(best,at,target,"Verified MCP Final TB format code "+code)
                else:
                    match=re.fullmatch(r"(\d{4})-([a-z]+)-([12])\d{3}",mid or "")
                    if not match:raise ValueError("outside_singles_scope")
                    y,event,gender=match.groups();year=int(y);tour="ATP" if gender=="1" else "WTA"
                    p1,p2=meta.get("player1"),meta.get("player2");rules=slam_rules(event,year,tour)
                    candidates=[]
                    for m in events.get((tour,year,event),[]):
                        if short_name_matches(p1,m["winner_name"]) and short_name_matches(p2,m["loser_name"]):candidates.append((m,m["winner_id"],m["loser_id"]))
                        elif short_name_matches(p1,m["loser_name"]) and short_name_matches(p2,m["winner_name"]):candidates.append((m,m["loser_id"],m["winner_id"]))
                    if len(candidates)==1:
                        m,p1id,p2id=candidates[0];canonical_id=m["match_id"]
                s1_prior,s2_prior,prior_text=serve_priors(features.get(canonical_id),p1id,p2id)
                qualified=("charting:" if chart else "slam:")+mid
                cache=cache_dir/(hashlib.sha256(qualified.encode()).hexdigest()+".json.gz")
                if cache.exists():
                    with gzip.open(cache,"rt") as f:cached=json.load(f)
                    if "exclusion" in cached:excluded.append(cached["exclusion"]);continue
                    results=cached["points"];entry=cached["match"]
                else:
                    rows=groups.get_group(mid).to_dict("records")
                    server_key="Svr" if chart else "PointServer";winner_key="PtWinner" if chart else "PointWinner";point_key="Pt" if chart else "PointNumber"
                    state=State(rules,server=int(rows[0][server_key])-1)
                    service_wins=[0,0];service_counts=[0,0];results=[];previous=None
                    for ordinal,r in enumerate(rows,1):
                        point=int(r[point_key])
                        if point!=ordinal:raise ValueError("missing_or_duplicate_point_number")
                        server=int(r[server_key])-1;winner=int(r[winner_key])-1
                        if server!=state.server:raise ValueError("server_progression_mismatch")
                        if chart and ([int(r["Set1"]),int(r["Set2"])]!=state.sets or [int(r["Gm1"]),int(r["Gm2"])]!=state.games):raise ValueError("pre_point_score_mismatch")
                        s1=(50*s1_prior+service_wins[0])/(50+service_counts[0]);s2=(50*s2_prior+service_wins[1])/(50+service_counts[1])
                        probability=state.probability(s1,s2)
                        p=state.points;receiver=1-server;tb=state.is_tiebreak()
                        break_point=not tb and p[receiver]>=3 and p[receiver]>p[server]
                        set_points=[]
                        for side in (0,1):
                            can_end=p[side]>p[1-side] and p[side]>=(state.target()-1 if tb else 3)
                            set_points.append(can_end and (tb or(state.games[side]>=5 and state.games[side]>state.games[1-side])))
                        results.append(dict(match_id=qualified,point=point,probability=probability,server=server+1,score=state.label(),break_point=break_point,set_point=any(set_points),match_point=any(set_points[i] and state.sets[i]==rules.best_of//2 for i in (0,1)),large_change=previous is not None and abs(probability-previous)>=.08,model_version="score-beta-v2-"+version,source_file=r["source_file"],source_row=r["source_row"]))
                        previous=probability;state.advance(winner)
                        if not chart and str(r.get("SetWinner","0")) not in ("1","2") and [int(r["P1GamesWon"]),int(r["P2GamesWon"])]!=state.games:raise ValueError("post_point_game_score_mismatch")
                        service_counts[server]+=1;service_wins[server]+=int(winner==server)
                    if not state.finished:raise ValueError("incomplete_or_retired_match")
                    entry=dict(match_id=qualified,canonical_match_id=canonical_id,tour=tour,season=year,event=event,player1=p1,player2=p2,points=len(results),rules=rules.source,prior=prior_text,date_precision="verified_charted_date" if chart else "event_year",source_file=meta["source_file"],source_row=meta["source_row"])
                    with gzip.open(cache,"wt") as f:json.dump(dict(points=results,match=entry),f,default=str)
                catalog.append(entry);point_batch.extend(results);point_count+=len(results)
                if len(point_batch)>=10000:flush()
                if len(catalog)%100==0:print(f"Replay: {len(catalog):,} eligible matches, {point_count:,} point predictions",flush=True)
                if limit and len(catalog)>=limit:break
            except (ValueError,TypeError,KeyError,RecursionError) as error:
                exclusion=dict(match_id=("charting:" if chart else "slam:")+str(mid),reason=str(error));excluded.append(exclusion)
                # Exclusions are checkpointed too; malformed records are not retried.
                if cache is not None:
                    with gzip.open(cache,"wt") as f:json.dump({"exclusion":exclusion},f)
                continue
        del groups,points
        if limit and len(catalog)>=limit:break
    flush()
    columns=["match_id","canonical_match_id","tour","season","event","player1","player2","points","rules","prior","date_precision","source_file","source_row"]
    con.register("catalog_frame",pd.DataFrame(catalog,columns=columns));con.execute("CREATE OR REPLACE TABLE main.replay_matches AS SELECT * FROM catalog_frame")
    con.close();write_json(ARTIFACTS/"replay-coverage.json",dict(eligible_matches=len(catalog),point_predictions=point_count,cache_version=version,exclusions=excluded,limitations=["Unknown scoring formats, incomplete matches, missing points and score inconsistencies are excluded.","As-of serve/return priors shrink to a population backoff when history is unavailable.","Slam date precision remains event/year unless uniquely linked; source point timing is not a verified match-day timestamp."]))
    return len(catalog)
