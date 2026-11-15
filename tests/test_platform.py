"""Deterministic checks for data semantics, temporal behavior, scoring, and auth."""
import json
from datetime import date,timedelta
import duckdb
import pandas as pd
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from baseline.metrics import MetricQuery,query_metrics
from baseline.scoring import State,Rules,game_win,tiebreak_win,slam_rules
from baseline.temporal import build_features
from baseline.config import connect
from baseline.auth import analyst_slot,serializer
from baseline.api import app


def test_rates_use_summed_pairwise_valid_denominators():
    con=duckdb.connect()
    con.execute("CREATE TABLE matches(tour VARCHAR, observed_date DATE)")
    con.execute("INSERT INTO matches VALUES('ATP','2024-12-01')")
    con.execute("CREATE TABLE player_matches(player_id VARCHAR,tour VARCHAR,surface VARCHAR,observed_date DATE,won INT,first_won INT,first_in INT)")
    con.execute("INSERT INTO player_matches VALUES('atp:a','ATP','Hard','2024-06-01',1,1,1),('atp:a','ATP','Hard','2024-07-01',0,9,99),('atp:a','ATP','Hard','2024-08-01',1,NULL,100),('atp:b','ATP','Hard','2024-06-01',0,0,0)")
    result=query_metrics(con,MetricQuery(metrics=["first_serve_won"],player_ids=["atp:a"],start=date(2024,1,1),end=date(2024,12,1)))
    row=result["rows"][0]
    assert row["first_serve_won"]==pytest.approx(.1)
    assert row["first_serve_won_coverage_matches"]==2
    assert row["first_serve_won_denominator"]==100
    zero=query_metrics(con,MetricQuery(metrics=["first_serve_won"],player_ids=["atp:b"],end=date(2024,12,1)))
    assert zero["rows"][0]["first_serve_won"] is None
    con.close()

@pytest.mark.parametrize("payload",[{"metrics":["DROP TABLE"]},{"group_by":["surface; select"]},{"limit":501},{"player_ids":["wta:1"],"tour":"ATP"},{"filters":{"sql":"select"}}])
def test_metrics_reject_unbounded_or_unknown_inputs(payload):
    with pytest.raises(ValueError):MetricQuery(**payload)

@pytest.mark.parametrize("p",[.2,.5,.7,.9])
def test_game_probability_and_symmetry(p):
    assert game_win(p)+game_win(1-p)==pytest.approx(1)
    assert game_win(p,4,2)==1
    assert game_win(p,2,4)==0
    assert game_win(p,8,8)==pytest.approx(game_win(p,3,3))

def test_tiebreak_and_final_set_rules():
    assert tiebreak_win(.65,.65,0)==pytest.approx(.5)
    assert tiebreak_win(.65,.6,0,7,5)==1
    assert slam_rules("wimbledon",2018,"ATP").final_tiebreak_at is None
    assert slam_rules("wimbledon",2019,"ATP").final_tiebreak_at==12
    assert slam_rules("ausopen",2019,"WTA").final_tiebreak_target==10
    assert slam_rules("frenchopen",2022,"ATP").final_tiebreak_target==10
    with pytest.raises(ValueError):slam_rules("unknown",2024,"ATP")

@pytest.mark.parametrize("rules",[Rules(3,6,7),Rules(5,None,7),Rules(5,12,7),Rules(3,6,10)])
def test_match_probability_symmetry(rules):
    state=State(rules)
    assert state.probability(.63,.63)==pytest.approx(.5,abs=1e-10)
    assert 0<state.probability(.63,.59)<1
    assert state.probability(.63,.59)+State(rules,server=1).probability(.59,.63)==pytest.approx(1)

def test_score_progression_tiebreak_server_and_terminal():
    state=State(Rules(3,6,10));state.sets=[1,1];state.games=[6,6]
    state.advance(0);assert state.server==1
    state.advance(0);assert state.server==1
    state.advance(0);assert state.server==0
    for _ in range(7):state.advance(0)
    assert state.finished and state.sets==[2,1] and state.probability()==1
    with pytest.raises(ValueError):state.advance(0)


def feature_fixture(path,future_winner="atp:a"):
    rows=[]
    for i,day in enumerate((date(2004,1,1),date(2004,1,1),date(2004,1,28),date(2004,1,30),date(2004,3,1))):
        winner=future_winner if i==4 else "atp:a";loser="atp:b" if winner=="atp:a" else "atp:a"
        r=dict(match_id=f"v1:atp:{i}",tour="ATP",surface="Hard",season=day.year,level="A",best_of=3,observed_date=day,winner_id=winner,loser_id=loser,completed=True,winner_rank=10.,loser_rank=20.,winner_age=24.,loser_age=25.,winner_ht=185.,loser_ht=180.)
        for pre in ("w","l"):
            for stat,value in (("svpt",60),("1stWon",25),("2ndWon",15)):r[pre+"_"+stat]=value
        rows.append(r)
    con=connect(path);con.register("frame",pd.DataFrame(rows));con.execute("CREATE TABLE matches AS SELECT * FROM frame");con.execute("CREATE TABLE rankings(player_id VARCHAR, ranking_date DATE, rank INT)");con.close()


def test_future_results_do_not_change_earlier_features(tmp_path):
    before=tmp_path/"before.duckdb";after=tmp_path/"after.duckdb"
    feature_fixture(before);feature_fixture(after,"atp:b");build_features(before);build_features(after)
    a=connect(before,True);b=connect(after,True)
    sql="SELECT * FROM features WHERE feature_cutoff<DATE '2004-03-01' ORDER BY match_id"
    pd.testing.assert_frame_equal(a.execute(sql).df(),b.execute(sql).df())
    frame=a.execute("SELECT * FROM features ORDER BY match_id").df()
    assert frame.iloc[0].elo_a==frame.iloc[1].elo_a==frame.iloc[2].elo_a==1500
    assert frame.iloc[3].elo_a>1500
    assert all(pd.isna(r.max_contributing_time) or r.max_contributing_time<r.feature_cutoff for r in frame.itertuples())
    a.close();b.close()


def test_quota_is_durable_and_prevents_concurrent_turns(tmp_path):
    path=tmp_path/"quota.sqlite"
    with analyst_slot("owner",path):
        with pytest.raises(HTTPException) as e:
            with analyst_slot("owner",path):pass
        assert e.value.status_code==429
    for _ in range(19):
        with analyst_slot("owner",path):pass
    with pytest.raises(HTTPException) as e:
        with analyst_slot("owner",path):pass
    assert e.value.detail["code"]=="quota_exhausted"


def test_unapproved_user_cannot_invoke_analyst(monkeypatch):
    monkeypatch.setenv("BASELINE_SESSION_SECRET","x"*48);monkeypatch.setenv("GITHUB_ALLOWED_USERS","owner")
    client=TestClient(app)
    client.cookies.set("baseline_session",serializer("session").dumps({"login":"intruder"}))
    response=client.post("/api/v1/analyst",json={"question":"hello"},headers={"origin":"http://localhost:8000"})
    assert response.status_code==403
    client.cookies.set("baseline_session",serializer("session").dumps({"login":"owner"}))
    response=client.post("/api/v1/analyst",json={"question":"hello"},headers={"origin":"https://evil.example"})
    assert response.status_code==403 and response.json()["detail"]["code"]=="invalid_origin"
    monkeypatch.setenv("GITHUB_ALLOWED_USERS","")
    assert client.post("/api/v1/analyst",json={"question":"hello"}).status_code==403


def test_oauth_state_failure(monkeypatch):
    monkeypatch.setenv("BASELINE_SESSION_SECRET","x"*48)
    client=TestClient(app)
    assert client.get("/api/v1/auth/callback?code=unused&state=wrong").status_code==403


def test_tool_permissions_cannot_expand():
    from baseline.analyst import tool
    with pytest.raises(ValueError):tool("execute_sql",{"sql":"SELECT 1"})
    with pytest.raises(ValueError):tool("get_data_status",{"shell":"echo"})


def test_matchup_validation():
    from baseline.services import MatchupQuery
    with pytest.raises(ValueError):MatchupQuery(player_a="atp:1",player_b="atp:1",as_of=date(2024,1,1))
    with pytest.raises(ValueError):MatchupQuery(player_a="atp:1",player_b="wta:1",as_of=date(2024,1,1))


def test_charting_notation_preserves_known_types_and_rejects_unknown():
    from baseline.charting import parse_sequence
    tokens,length=parse_sequence("6b29f3*")
    assert [t["type"] for t in tokens]==["serve","backhand","forehand"]
    assert length==3
    tokens,length=parse_sequence("4b37y1r3n#")
    assert length==3 and tokens[-1]["type"]=="forehand_slice"
    assert parse_sequence("4n")[1]==0
    with pytest.raises(ValueError):parse_sequence("P")
    with pytest.raises(ValueError):parse_sequence("6b29C")


def test_odds_event_normalization_is_deterministic():
    from baseline.identity import event_name
    assert event_name("Australian Open - Melbourne")==event_name("Australian Open")
    assert event_name("Roland Garros - Paris")==event_name("Roland Garros")
    assert event_name("Australian Open - Melbourne")!=event_name("US Open - New York")


def test_release_mismatch_blocks_readiness(tmp_path,monkeypatch):
    from baseline.release import check_release
    from baseline.config import METRIC_VERSION
    (tmp_path/"manifest.json").write_text(json.dumps({"metric_version":"wrong","files":{},"snapshot":"x"}))
    with pytest.raises(ValueError,match="Metric definition"):check_release(tmp_path)
    (tmp_path/"manifest.json").write_text(json.dumps({"metric_version":METRIC_VERSION,"files":{"missing":"hash"},"snapshot":"x"}))
    with pytest.raises(ValueError,match="checksum"):check_release(tmp_path)


def test_elo_query_selects_the_last_available_rating_not_an_aggregate():
    con=duckdb.connect();con.execute("CREATE TABLE matches(tour VARCHAR, observed_date DATE)")
    con.execute("INSERT INTO matches VALUES('ATP','2024-12-01')")
    con.execute("CREATE TABLE rating_history(player_id VARCHAR,surface VARCHAR,available_at DATE,elo DOUBLE,surface_elo DOUBLE)")
    con.execute("INSERT INTO rating_history VALUES('atp:a','Hard','2024-01-01',1500,1550),('atp:a','Hard','2024-05-01',1700,1750),('atp:a','Hard','2024-06-01',1900,1950)")
    result=query_metrics(con,MetricQuery(metrics=['elo'],player_ids=['atp:a'],end=date(2024,6,1)))
    assert result['rows'][0]['elo']==1700
    assert result['aggregation']=='as_of_observation'
    with pytest.raises(ValueError):MetricQuery(metrics=['elo','match_win_rate'])
    with pytest.raises(ValueError):MetricQuery(metrics=['surface_elo'])
    con.close()


def test_unreturnable_serve_counts_as_one_shot_rally():
    from baseline.charting import parse_sequence
    assert parse_sequence('6#')[1]==1
    assert parse_sequence('5*')[1]==1
    assert parse_sequence('6b29n#')[1]==1


def test_availability_filter_excludes_unreleased_tournament_results():
    con=duckdb.connect();con.execute("CREATE TABLE matches(tour VARCHAR,observed_date DATE)")
    con.execute("INSERT INTO matches VALUES('ATP','2024-12-01')")
    con.execute("CREATE TABLE player_matches(player_id VARCHAR,tour VARCHAR,surface VARCHAR,observed_date DATE,available_at DATE,first_won INT,first_in INT)")
    con.execute("INSERT INTO player_matches VALUES('atp:a','ATP','Hard','2024-06-01','2024-06-29',1,1),('atp:a','ATP','Hard','2024-07-01','2024-07-29',9,99)")
    result=query_metrics(con,MetricQuery(metrics=['first_serve_won'],player_ids=['atp:a'],end=date(2024,7,1),available_before=date(2024,7,1)))
    assert result['rows'][0]['first_serve_won']==1
    assert result['rows'][0]['sample_matches']==1
    con.close()


def test_provider_timeout_is_a_clear_error_and_does_not_block_browsing(monkeypatch,tmp_path):
    import baseline.analyst as analyst_module
    monkeypatch.setenv('BASELINE_SESSION_SECRET','x'*48)
    monkeypatch.setenv('GITHUB_ALLOWED_USERS','owner')
    monkeypatch.setenv('BASELINE_QUOTA_DB',str(tmp_path/'quota.sqlite'))
    async def timeout(question,**kwargs):raise TimeoutError()
    monkeypatch.setattr(analyst_module,'run_analyst',timeout)
    client=TestClient(app);client.cookies.set('baseline_session',serializer('session').dumps({'login':'owner'}))
    response=client.post('/api/v1/analyst',json={'question':'hello'},headers={'origin':'http://localhost:8000'})
    assert response.status_code==503
    assert response.json()['detail']['code']=='provider_unavailable'
    assert client.get('/api/v1/auth/me').status_code==200
