"""Explicit venue coverage and resumable, opt-in historical weather acquisition."""
from __future__ import annotations
import csv
import json
import hashlib
from datetime import timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlencode
import httpx
import pandas as pd
from .config import ROOT,DATA, ARTIFACTS, connect, records, utcnow, write_json,digest


def enrich(acquire=False):
    con=connect()
    editions=records(con,"SELECT * FROM main.editions ORDER BY tour,season,edition_id")
    seed=DATA/"venue-history.csv";assignments=list(csv.DictReader(seed.open())) if seed.exists() else []
    output=[];weather=[];manifests={};run=__import__("uuid").uuid4().hex
    for edition in editions:
        candidates=[a for a in assignments if a["tour"]==edition["tour"] and a["edition_id"]==edition["edition_id"] and a["effective_from"]<=str(edition["start_date"])<=a["effective_to"]]
        item={**edition,"venue_status":"unavailable","unavailable_reason":"No verified venue assignment; coordinates are never guessed","venue":None,"latitude":None,"longitude":None,"timezone":None,"elevation_m":None,"verification_source":None,"weather_status":"unavailable","elevation_status":"unavailable","elevation_unavailable_reason":"Independent historical venue elevation not verified"}
        if len(candidates)>1:item["unavailable_reason"]="Multiple venue assignments require review; event may span venues"
        if len(candidates)==1:
            a=candidates[0]
            try:
                assert a["verification_source"].startswith("https://") and a["confidence"]=="verified"
                ZoneInfo(a["timezone"])
                lat,lon=float(a["latitude"]),float(a["longitude"])
                assert -90<=lat<=90 and -180<=lon<=180
                item.update(venue_status="verified",unavailable_reason=None,venue=a["venue"],latitude=lat,longitude=lon,timezone=a["timezone"],elevation_m=float(a["elevation_m"]) if a["elevation_m"] else None,verification_source=a["verification_source"],city=a["city"],country=a["country"],effective_from=a["effective_from"],effective_to=a["effective_to"],confidence=a["confidence"],indoor=a["indoor"],coordinate_source=a.get("coordinate_source"),reviewed_at=a.get("reviewed_at"),venue_id=hashlib.sha256(f"{lat},{lon},{a['timezone']}".encode()).hexdigest()[:16],weather_period_start=a["event_start"],weather_period_end=a["event_end"],elevation_status="verified" if a["elevation_m"] else "unavailable",elevation_unavailable_reason=None if a["elevation_m"] else "Independent historical venue elevation not verified")
                # Event period is explicitly bounded by the verified seed, not a guessed
                # match duration or the tournament-start proxy in Sackmann.
                params=dict(latitude=lat,longitude=lon,start_date=a["event_start"],end_date=a["event_end"],timezone=a["timezone"],hourly="temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m",models="era5")
                key=hashlib.sha256(json.dumps(params,sort_keys=True).encode()).hexdigest()
                cache=DATA/"raw/weather"/(key+".json")
                if not cache.exists() and acquire:
                    with httpx.Client(timeout=30) as client:
                        response=client.get("https://archive-api.open-meteo.com/v1/archive",params=params);response.raise_for_status()
                    value=response.json()
                    if "hourly" not in value:raise ValueError("No hourly weather data")
                    write_json(cache,dict(request=params,acquired_at=utcnow(),url=str(response.url),response=value))
                if cache.exists():
                    result=json.loads(cache.read_text())["response"]
                    hourly=pd.DataFrame(result["hourly"]);hourly["date"]=hourly.time.str[:10]
                    daily=hourly.groupby("date").agg(temperature_c=("temperature_2m","mean"),humidity_pct=("relative_humidity_2m","mean"),precipitation_mm=("precipitation",lambda x:x.sum(min_count=1)),wind_kmh=("wind_speed_10m","mean"),hours=("time","count")).reset_index()
                    for r in daily.to_dict("records"):weather.append({**r,"tour":edition["tour"],"edition_id":edition["edition_id"],"request_sha256":key,"venue_id":item["venue_id"],"indoor":a["indoor"],"interpretation":"Gridded historical outdoor estimate; event-period context, not stadium measurements"})
                    item["weather_status"]="cached_event_period"
                    receipt=json.loads(cache.read_text())
                    manifests[key]=dict(source="open_meteo_era5",path=str(cache.relative_to(ROOT)),sha256=digest(cache),bytes=cache.stat().st_size,acquired_at=receipt["acquired_at"],revision=None,schema_sha256=hashlib.sha256(json.dumps(sorted(result["hourly"])).encode()).hexdigest(),row_count=len(daily),ingestion_run=run,observed_date_min=daily.date.min(),observed_date_max=daily.date.max(),parsing_errors=[])
                else:item["weather_status"]="not_acquired"
            except (ValueError,KeyError,AssertionError,httpx.HTTPError) as error:
                item["unavailable_reason"]="Verified assignment or acquisition error: "+str(error)
        output.append(item)
    frame=pd.DataFrame(output);con.register("venue_frame",frame);con.execute("CREATE OR REPLACE TABLE main.venue_coverage AS SELECT * FROM venue_frame")
    columns=["date","temperature_c","humidity_pct","precipitation_mm","wind_kmh","hours","tour","edition_id","request_sha256","venue_id","indoor","interpretation"]
    weather_frame=pd.DataFrame(weather,columns=columns).drop_duplicates(["venue_id","date"])
    con.register("weather_frame",weather_frame);con.execute("CREATE OR REPLACE TABLE main.weather AS SELECT * FROM weather_frame")
    con.close();report=dict(editions=len(output),verified=sum(r["venue_status"]=="verified" for r in output),unavailable=sum(r["venue_status"]=="unavailable" for r in output),weather_days=len(weather_frame),scope="Every supported edition accounted for; verification is incomplete.")
    write_json(ARTIFACTS/"enrichment-coverage.json",report)
    write_json(ARTIFACTS/"weather-source-manifest.json",list(manifests.values()))
    return report
