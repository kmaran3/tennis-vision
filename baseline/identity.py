"""Exact, tour-qualified bridges; ambiguous identities remain unresolved."""
import re
import unicodedata
import pandas as pd
from .config import ARTIFACTS, DATA, connect, records, write_json
from .modeling import scores

def normalize(value):
    value=unicodedata.normalize("NFKD",str(value or ""))
    return re.sub(r"[^a-z0-9]","",value.encode("ascii","ignore").decode().lower())

def event_name(value):
    text=normalize(str(value or "").split(" - ",1)[0])
    for suffix in ("atp","wta"):
        if text.endswith(suffix):text=text[:-len(suffix)]
    return {"rolandgarros":"frenchopen","internazionalibnlditalia":"rome"}.get(text,text)

def build_bridges():
    con=connect()
    names=records(con,"SELECT p.player_id,p.tour,p.name,min(m.observed_date) AS first_date,max(m.observed_date) AS last_date FROM main.players p JOIN main.player_matches m USING(player_id) GROUP BY 1,2,3")
    index={}
    for p in names:index.setdefault((p["tour"],normalize(p["name"])),[]).append(p)
    overrides={}
    path=DATA/"identity-overrides.csv"
    if path.exists():
        import csv
        for row in csv.DictReader(path.open()):overrides[(row["source"],row["tour"],row["source_id"])]=row["player_id"]
    def resolve(source,tour,sid,name,year):
        override=overrides.get((source,tour,str(sid)))
        if override and any(p["player_id"]==override and p["tour"]==tour for p in names):return override,"explicit_override"
        candidates=[p for p in index.get((tour,normalize(name)),[]) if p["first_date"].year-1<=year<=p["last_date"].year+1]
        return (candidates[0]["player_id"],"unique_normalized_name_and_activity") if len(candidates)==1 else (None,"ambiguous" if candidates else "unresolved")
    odds=records(con,"SELECT * FROM raw.odds")
    bridges=[];matched=[];exclusions=[]
    matches=records(con,"SELECT * FROM main.matches WHERE season>=2021")
    match_index={}
    for m in matches:match_index.setdefault((m["tour"],tuple(sorted((m["winner_id"],m["loser_id"])))),[]).append(m)
    for r in odds:
        tour=str(r.get("genre","")).upper()
        if tour not in ("ATP","WTA"):continue
        try:day=__import__("datetime").date.fromisoformat(r["date"][:10])
        except (ValueError,TypeError):continue
        ids=[]
        for side in ("1","2"):
            sid=r.get("joueur"+side+"_id");name=r.get("joueur"+side)
            pid,method=resolve("valuebetennis",tour,sid,name,day.year);ids.append(pid)
            bridges.append(dict(source="valuebetennis",tour=tour,source_id=sid,original_name=name,player_id=pid,resolution_method=method,season=day.year))
        reason="unresolved_players"
        candidates=[]
        if all(ids) and ids[0]!=ids[1]:
            for m in match_index.get((tour,tuple(sorted(ids))),[]):
                if -2<=(day-m["observed_date"]).days<=27 and event_name(m["event"])==event_name(r.get("tournoi")):
                    # Score is an extra check when both sources provide it. Odds orientation
                    # follows the matched provider sides, never the canonical winner order.
                    provider_winner = ids[0] if r.get("vainqueur_id")==r.get("joueur1_id") else ids[1] if r.get("vainqueur_id")==r.get("joueur2_id") else None
                    if provider_winner and provider_winner!=m["winner_id"]:continue
                    provider_sets=re.findall(r"(\d+)-(\d+)",r.get("score") or "")
                    canonical_sets=re.findall(r"(\d+)-(\d+)",m.get("score") or "")
                    if ids[0]!=m["winner_id"]:provider_sets=[(b,a) for a,b in provider_sets]
                    if provider_sets and canonical_sets and provider_sets!=canonical_sets:continue
                    candidates.append(m)
            reason="ambiguous_match" if len(candidates)>1 else "no_unique_event_pair_date_match"
        if len(candidates)==1:
            m=candidates[0]
            item=dict(match_id=m["match_id"],tour=tour,season=day.year,level=m["level"],player1=ids[0],player2=ids[1],source_id=r["match_id"],provider_observed_date=day,source_file=r["source_file"],source_row=r["source_row"])
            for label,fr in (("opening","ouverture"),("closing","cloture")):
                try:
                    a=float(r["cote1_"+fr]);b=float(r["cote2_"+fr]);assert a>1 and b>1
                    item[label+"_probability"]=(1/a)/(1/a+1/b)
                except (ValueError,TypeError,AssertionError):item[label+"_probability"]=None
            matched.append(item)
        else:exclusions.append(dict(tour=tour,season=day.year,reason=reason,source_id=r["match_id"]))
    bridge=pd.DataFrame(bridges).drop_duplicates()
    if not bridge.empty:con.register("bridge_frame",bridge);con.execute("CREATE OR REPLACE TABLE main.player_bridge AS SELECT * FROM bridge_frame")
    columns=["match_id","tour","season","level","player1","player2","source_id","provider_observed_date","source_file","source_row","opening_probability","closing_probability"]
    frame=pd.DataFrame(matched,columns=columns)
    ambiguous=frame.match_id.duplicated(keep=False) if not frame.empty else pd.Series(dtype=bool)
    if not frame.empty:frame=frame[~ambiguous]
    con.register("odds_frame",frame);con.execute("CREATE OR REPLACE TABLE main.odds_matches AS SELECT * FROM odds_frame")
    report=dict(odds_rows=len(odds),matched_main_tour_matches=len(frame),rejected_duplicate_matches=int(ambiguous.sum()),exclusions=pd.DataFrame(exclusions).groupby(["tour","season","reason"]).size().reset_index(name="rows").to_dict("records") if exclusions else [],coverage=records(con,"SELECT m.tour,m.season,m.level,count(*) AS total_matches,count(o.match_id) AS odds_matches FROM main.matches m LEFT JOIN main.odds_matches o USING(match_id) WHERE m.season>=2021 GROUP BY 1,2,3"))
    write_json(ARTIFACTS/"join-coverage.json",report);con.close()
    return report


def market_evaluation():
    con=connect(read_only=True)
    data=con.execute("SELECT p.*, o.player1, o.opening_probability,o.closing_probability FROM main.predictions p JOIN main.odds_matches o USING(match_id) WHERE opening_probability IS NOT NULL AND closing_probability IS NOT NULL").df()
    report=[]
    if not data.empty:
        for (tour,season),frame in data.groupby(["tour","season"]):
            y=frame.y.to_numpy();same=(frame.player_a==frame.player1).to_numpy()
            import numpy as np
            report.append(dict(tour=tour,season=int(season),common_subset_matches=len(frame),model=scores(y,frame.probability.to_numpy()),elo=scores(y,frame.elo_probability.to_numpy()),opening=scores(y,np.where(same,frame.opening_probability,1-frame.opening_probability)),closing=scores(y,np.where(same,frame.closing_probability,1-frame.closing_probability))))
    con.close();write_json(ARTIFACTS/"market-evaluation.json",dict(results=report,closing_definition="Provider's last recorded pre-match odds; not a verified timestamp",coverage_file="join-coverage.json"));return report
