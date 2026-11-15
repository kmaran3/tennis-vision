"""Exercise actual serving artifacts through HTTP without external account calls."""
import json
import resource
from fastapi.testclient import TestClient
from baseline.api import app
from baseline.config import ARTIFACTS,write_json,serving_path

client=TestClient(app)
checks=[]
def get(path):
    r=client.get(path);assert r.status_code==200,(path,r.status_code,r.text[:500]);checks.append(dict(path=path,status=r.status_code));return r.json() if r.headers.get("content-type","").startswith("application/json") else r.text

def main():
    get("/health/ready");get("/")
    status=get("/api/v1/status")["data"]
    for tour in ("ATP","WTA"):
        people=get("/api/v1/players?tour="+tour)["data"]
        assert people
        get("/api/v1/players/"+people[0]["player_id"])
        get("/api/v1/coverage?tour="+tour+"&season=2024")
        matches=get("/api/v1/matches?tour="+tour+"&season=2024")["data"]
        assert matches;get("/api/v1/matches/"+matches[0]["match_id"])
        r=client.post("/api/v1/metrics/query",json=dict(tour=tour,metrics=["first_serve_won","average_rally_length","charted_match_coverage"],group_by=["surface"]))
        assert r.status_code==200,r.text
        checks.append(dict(path="metrics/"+tour,status=200))
        replay=get("/api/v1/replays?tour="+tour)["data"]
        assert replay
        d=get("/api/v1/replays/"+replay[0]["match_id"])["data"]
        assert len(d["points"])==d["match"]["points"]
    for payload in (dict(player_a="atp:104745",player_b="atp:104925",as_of="2024-06-01",surface="Clay",best_of=3,venue_edition_id="2024-520"),dict(player_a=get("/api/v1/players?tour=WTA&q=Swiatek")["data"][0]["player_id"],player_b=get("/api/v1/players?tour=WTA&q=Sabalenka")["data"][0]["player_id"],as_of="2024-06-01",surface="Hard",best_of=3)):
        response=client.post("/api/v1/matchups",json=payload)
        assert response.status_code==200,response.text
        value=response.json()["data"]
        swapped={**payload,"player_a":payload["player_b"],"player_b":payload["player_a"]}
        inverse=client.post("/api/v1/matchups",json=swapped)
        assert inverse.status_code==200,inverse.text
        assert abs(value["probability_a"]+inverse.json()["data"]["probability_a"]-1)<1e-9
        checks.append(dict(path="matchup/"+payload["player_a"].split(":")[0],status=200))
        if payload["player_a"].startswith("wta:"):
            recent={**payload,"as_of":"2026-05-01"}
            xgb=client.post("/api/v1/matchups",json=recent);assert xgb.status_code==200,xgb.text
            checks.append(dict(path="matchup/wta-2026",status=200))
    old_a=get("/api/v1/players?tour=WTA&q=Halep")["data"][0]["player_id"]
    old_b=get("/api/v1/players?tour=WTA&q=Kerber")["data"][0]["player_id"]
    xgb=client.post("/api/v1/matchups",json=dict(player_a=old_a,player_b=old_b,as_of="2018-06-01",surface="Hard",best_of=3))
    assert xgb.status_code==200,xgb.text
    assert 0<xgb.json()["data"]["probability_a"]<1
    checks.append(dict(path="matchup/wta-2018-challenger",status=200))
    write_json(ARTIFACTS/"http-smoke.json",dict(checks=checks,status="passed",snapshot=status["snapshot"],max_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,serving_bytes=serving_path().stat().st_size,browser_qa="Desktop/mobile Playwright checks run separately with a fresh local Brave profile"))
    print("HTTP smoke passed",len(checks),"requests")

if __name__=="__main__":main()
