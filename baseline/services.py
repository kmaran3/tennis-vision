"""Shared public-query and inference services, used locally and in production."""
from __future__ import annotations
from datetime import date, timedelta
import json
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal
from .config import records, METRIC_VERSION
from .metrics import MetricQuery, query_metrics, METRICS
from .inference import elo_probability,model_probability

class MatchupQuery(BaseModel):
    model_config=ConfigDict(extra="forbid")
    player_a: str
    player_b: str
    as_of: date
    surface: Literal["Hard","Clay","Grass"]="Hard"
    best_of: Literal[3,5]=3
    venue_edition_id: str | None = None
    level: Literal["A","I","G","M","PM","P","F","D","O","T1","T2","T3","T4","T5","W"] | None = None

    @model_validator(mode="after")
    def same_tour(self):
        if self.player_a==self.player_b:raise ValueError("Choose two different players")
        if self.player_a.split(":")[0]!=self.player_b.split(":")[0]:raise ValueError("Cross-tour scenarios are unsupported")
        return self


def status(con):
    build=records(con,"SELECT * FROM meta.build")[0]
    cutoffs=records(con,"SELECT tour,min(observed_date) FILTER(WHERE season>=2000) AS statistics_start,max(observed_date) AS cutoff,max(season) AS latest_incomplete_season,count(*) AS matches FROM main.matches GROUP BY 1")
    coverage=records(con,"SELECT tour,season,count(*) AS editions,count(*) FILTER(WHERE venue_status='verified') AS verified_venues,count(*) FILTER(WHERE weather_status='cached_event_period') AS weather_editions FROM main.venue_coverage GROUP BY 1,2 ORDER BY 1,2 DESC")
    return dict(snapshot=build["snapshot"],metric_version=build["metric_version"],sample=build["sample"],built_at=build["built_at"],tours=cutoffs,venue_coverage=coverage,limitations=["Latest season incomplete; archive is not a live feed.","Tournament dates are approximate; prediction features use inferred availability.","Weather and venue verification incomplete; unavailable editions remain visible.","Replay priors use as-of serve/return form with population shrinkage where unavailable."])


def players(con,q="",tour="ATP",limit=30,start=None,end=None,surface=None):
    if start and end and start>end:raise ValueError("start must precede end")
    clauses=["p.tour=?","p.name ILIKE ?","m.season>=2000"]
    params=[tour,"%"+q+"%"]
    if start:clauses.append("m.observed_date>=?");params.append(start)
    if end:clauses.append("m.observed_date<=?");params.append(end)
    if surface:clauses.append("m.surface=?");params.append(surface)
    params.append(limit)
    return records(con,"SELECT p.*, count(m.match_id) AS matches, max(m.observed_date) AS last_observed FROM main.players p JOIN main.player_matches m USING(player_id) WHERE "+" AND ".join(clauses)+" GROUP BY ALL ORDER BY matches DESC,p.player_id LIMIT ?",params)



def player_profile(con,player_id,surface=None,end=None):
    player=records(con,"SELECT * FROM main.players WHERE player_id=?",[player_id])
    if not player:raise ValueError("Unknown player")
    tour=player[0]["tour"]
    q=MetricQuery(tour=tour,player_ids=[player_id],surface=surface,end=end,metrics=list(METRICS))
    metrics=query_metrics(con,q);cutoff=date.fromisoformat(metrics["filters"]["end"])
    matches=records(con,"SELECT m.* FROM main.matches m WHERE (winner_id=? OR loser_id=?) AND observed_date<=? ORDER BY observed_date DESC,match_id DESC LIMIT 20",[player_id,player_id,cutoff])
    rankings=records(con,"SELECT ranking_date,rank FROM main.rankings WHERE player_id=? AND ranking_date<=? ORDER BY ranking_date DESC LIMIT 250",[player_id,cutoff])[::-1]
    elo=records(con,"SELECT feature_cutoff AS date,CASE WHEN player_a=? THEN elo_a ELSE elo_b END AS elo FROM main.features WHERE (player_a=? OR player_b=?) AND feature_cutoff<=? ORDER BY feature_cutoff DESC LIMIT 250",[player_id,player_id,player_id,cutoff])[::-1]
    shot_types=records(con,"SELECT s.type,sum(s.shots) AS shots FROM main.chart_shot_profiles s JOIN main.matches m USING(match_id) WHERE s.player_id=? AND m.observed_date BETWEEN ? AND ? AND (? IS NULL OR m.surface=?) GROUP BY 1 ORDER BY shots DESC",[player_id,metrics["filters"]["start"],cutoff,surface,surface])
    return dict(player=player[0],metrics=metrics,matches=matches,rankings=rankings,elo=elo,shot_types=shot_types)


def matchup(con,q:MatchupQuery,model_dir):
    tour=q.player_a.split(":")[0].upper()
    cutoff=con.execute("SELECT max(observed_date) FROM main.matches WHERE tour=?",[tour]).fetchone()[0]
    if not cutoff or q.as_of>cutoff or q.as_of<date(2005,1,1):raise ValueError(f"Unsupported scenario date. Source cutoff: {cutoff}")
    registry_file=Path(model_dir)/"registry.json"
    if not registry_file.exists():raise ValueError("No trained models available")
    eligible=[m for m in json.loads(registry_file.read_text()) if m["tour"]==tour and m["trained_before"]<str(q.as_of) and m["valid_from"]<=str(q.as_of)<=m["valid_until"]]
    if not eligible:raise ValueError("No model with a valid historical training window for this date")
    model=eligible[-1]
    venue_context=None
    if q.venue_edition_id:
        venues=records(con,"SELECT * FROM main.venue_coverage WHERE tour=? AND edition_id=? AND venue_status='verified'",[tour,q.venue_edition_id])
        if len(venues)!=1:raise ValueError("No unique verified venue assignment for this scenario")
        venue_context=venues[0]
        if venue_context["surface"]!=q.surface:raise ValueError("Scenario surface differs from the verified venue edition")
        start=venue_context.get("weather_period_start");end=venue_context.get("weather_period_end")
        if not start or not end or not str(start)<=str(q.as_of)<=str(end):raise ValueError("This verified venue is available only within its documented event period")
    info=[]
    for pid in (q.player_a,q.player_b):
        player=records(con,"SELECT * FROM main.players WHERE player_id=? AND tour=?",[pid,tour])
        if not player:raise ValueError("Unknown player")
        hist=records(con,"SELECT * FROM main.player_matches WHERE player_id=? AND available_at<? ORDER BY observed_date DESC",[pid,q.as_of])
        if len(hist)<10:raise ValueError("Insufficient history: at least ten available completed matches per player required")
        rating=records(con,"SELECT elo,surface_elo FROM main.rating_history WHERE player_id=? AND surface=? AND available_at<? ORDER BY available_at DESC LIMIT 1",[pid,q.surface,q.as_of])
        if not rating:raise ValueError("Insufficient rating history for this surface")
        rank=con.execute("SELECT rank FROM main.rankings WHERE player_id=? AND ranking_date<? ORDER BY ranking_date DESC LIMIT 1",[pid,q.as_of]).fetchone()
        recent=[h for h in hist if h["observed_date"]>=q.as_of-timedelta(weeks=52)]
        def ratio(num,den):
            valid=[(num(r),den(r)) for r in recent];valid=[(n,d) for n,d in valid if n is not None and d is not None and d>0 and 0<=n<=d]
            return sum(n for n,d in valid)/sum(d for n,d in valid) if valid else float("nan")
        def add(a,b):return a+b if a is not None and b is not None else None
        serve=ratio(lambda r:add(r["first_won"],r["second_won"]),lambda r:r["service_points"])
        ret=ratio(lambda r:r["opp_service_points"]-r["opp_first_won"]-r["opp_second_won"] if all(r[k] is not None for k in ("opp_service_points","opp_first_won","opp_second_won")) else None,lambda r:r["opp_service_points"])
        p=player[0];age=(q.as_of-p["birth_date"]).days/365.25 if p["birth_date"] else float("nan")
        info.append(dict(player=p,elo=rating[0]["elo"],surface_elo=rating[0]["surface_elo"],rank=rank[0] if rank else float("nan"),serve=serve,ret=ret,form=sum(r["won"] for r in recent)/len(recent) if recent else float("nan"),history=len(hist),age=age,height=p["height"] or float("nan")))
    a,b=info
    features={name:a[k]-b[k] for name,k in (("elo_diff","elo"),("surface_elo_diff","surface_elo"),("rank_diff","rank"),("serve_diff","serve"),("return_diff","ret"),("form_diff","form"),("age_diff","age"),("height_diff","height"),("experience_diff","history"))}
    features["format_diff"]=(q.best_of-3)*features["elo_diff"]/400
    scenario_level=q.level or ("A" if tour=="ATP" else "I")
    features["slam_elo_diff"]=features["elo_diff"]/400*int(scenario_level=="G")
    features["high_tier_elo_diff"]=features["elo_diff"]/400*int(scenario_level in ("M","PM","P","F","T1","T2"))
    features["hand_diff"]=(int(a["player"]["hand"]=="L")-int(b["player"]["hand"]=="L")) if a["player"]["hand"] in ("L","R") and b["player"]["hand"] in ("L","R") else float("nan")
    probability=model_probability(model,features,model_dir)
    h2h=records(con,"SELECT match_id,event,observed_date,winner_id,winner_name,score FROM main.matches WHERE ((winner_id=? AND loser_id=?) OR(winner_id=? AND loser_id=?)) AND available_at<? ORDER BY observed_date DESC",[q.player_a,q.player_b,q.player_b,q.player_a,q.as_of])
    comparisons=query_metrics(con,MetricQuery(tour=tour,player_ids=[q.player_a,q.player_b],surface=q.surface,end=q.as_of,available_before=q.as_of,metrics=list(METRICS)))
    by_player={r["player_id"]:r for r in comparisons["rows"]}
    differences=[]
    for metric,label in (("first_serve_won","first-serve points won"),("second_serve_won","second-serve points won"),("return_points_won","return points won")):
        x=by_player.get(q.player_a,{});y=by_player.get(q.player_b,{})
        if x.get(metric) is not None and y.get(metric) is not None:
            differences.append((abs(x[metric]-y[metric]),metric,label,x,y))
    watch="Serve/return samples are unavailable for a directional comparison."
    if differences:
        _,metric,label,x,y=max(differences,key=lambda r:r[0]);delta=(x[metric]-y[metric])*100
        watch=f"{a['player']['name']} is {abs(delta):.1f} percentage points {'higher' if delta>=0 else 'lower'} on {label} on {q.surface.lower()} than {b['player']['name']}, over {comparisons['filters']['start']} to {comparisons['filters']['end']}. Covered matches: {x[metric+'_coverage_matches']} / {y[metric+'_coverage_matches']}."
    watch+=f" The as-of Elo difference is {features['elo_diff']:.0f} points. Comparisons exclude results unavailable at the scenario cutoff."
    return dict(player_a_name=a["player"]["name"],player_b_name=b["player"]["name"],venue_context=venue_context,probability_a=probability,probability_b=1-probability,elo_baseline=elo_probability(a["elo"],b["elo"]),model_version=model["version"],model_trained_before=model["trained_before"],filters={**q.model_dump(mode="json"),"level":scenario_level},history_a=a["history"],history_b=b["history"],head_to_head=h2h,comparison=comparisons,what_to_watch=watch,warnings=["Historical scenario, not a current prediction.","Unspecified tournament context defaults to the main-tour category (ATP A / WTA I); match format is a separate scenario input.","Features use tournament-start dates and a conservative 28-day outcome lag.","No realized weather or odds are used; model uncertainty has not been calibrated as an interval."])


def venue_coverage(con,tour,season):
    rows=records(con,"SELECT * FROM main.venue_coverage WHERE tour=? AND season=? ORDER BY event",[tour,season])
    for row in rows:
        row["weather_summary"]=None
        if row.get("venue_id") and row.get("weather_status")=="cached_event_period":
            summary=records(con,"SELECT avg(temperature_c) AS temperature_c,avg(humidity_pct) AS humidity_pct,sum(precipitation_mm) AS precipitation_mm,avg(wind_kmh) AS wind_kmh,count(*) AS days,min(date) AS start_date,max(date) AS end_date FROM main.weather WHERE venue_id=? AND date BETWEEN ? AND ?",[row["venue_id"],row["weather_period_start"],row["weather_period_end"]])[0]
            if summary["days"]:row["weather_summary"]={**summary,"interpretation":"Mean of daily gridded outdoor estimates; precipitation is the period sum. Event-period context, not stadium measurements or match-day conditions."}
    return rows
