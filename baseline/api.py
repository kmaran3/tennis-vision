"""Versioned API and one-service frontend serving."""
from __future__ import annotations
import os
import asyncio
import json
from contextlib import suppress
import threading
import httpx
import duckdb
from datetime import date
from pathlib import Path
from typing import Any, Literal
from fastapi import FastAPI, Depends, HTTPException, Request, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.background import BackgroundTask
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, ConfigDict, model_validator
from .config import serving_path, connect, records, ROOT, METRIC_VERSION
from .metrics import MetricQuery, query_metrics, METRICS, ASOF_METRICS
from . import services
from .auth import router, user, check_origin, analyst_slot

app=FastAPI(title="Baseline",version="1.0.0",description="Historical ATP/WTA analytics. Latest source season is incomplete.")
app.include_router(router)

class AnalyticalResponse(BaseModel):
    data:Any
    source_snapshot:str
    metric_version:str
    cutoffs:list[dict]
    warnings:list[str]=Field(default_factory=list)
    filters:dict=Field(default_factory=dict)

class ChatMessage(BaseModel):
    model_config=ConfigDict(extra="forbid")
    role:Literal["user","assistant"]
    content:str=Field(min_length=1,max_length=8000)

class AnalystRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    question:str=Field(min_length=1,max_length=4000)
    history:list[ChatMessage]=Field(default_factory=list,max_length=10)
    tour:Literal["ATP","WTA"]="ATP"
    surface:Literal["Hard","Clay","Grass","Carpet"]|None=None
    end:date|None=None

    @model_validator(mode="after")
    def bounded_history(self):
        if not self.question.strip():raise ValueError("Enter a tennis question.")
        if sum(len(m.content) for m in self.history)>16000:raise ValueError("Conversation context is too long. Start a new chat.")
        if any(m.role!=("user" if i%2==0 else "assistant") for i,m in enumerate(self.history)) or len(self.history)%2:
            raise ValueError("History must contain completed user/assistant pairs.")
        return self

def analyst_options(body):
    return dict(history=[m.model_dump() for m in body.history],context={"tour":body.tour,"surface":body.surface,"end":str(body.end) if body.end else None})


def database():
    path=serving_path()
    if not path.exists():raise HTTPException(503,detail={"code":"data_unavailable","message":"Build and package the serving artifact first: uv run baseline build"})
    con=connect(path,read_only=True)
    timer=threading.Timer(10,con.interrupt);timer.daemon=True;timer.start()
    try:yield con
    finally:timer.cancel();con.close()


def envelope(con,data,warnings=None,filters=None):
    build=con.execute("SELECT snapshot,metric_version FROM meta.build").fetchone()
    cutoffs=records(con,"SELECT tour,max(observed_date) AS cutoff FROM main.matches GROUP BY 1")
    effective_filters=filters if filters is not None else data.get("filters",data.get("metrics",{}).get("filters",{})) if isinstance(data,dict) else {}
    return AnalyticalResponse(data=data,filters=effective_filters,source_snapshot=build[0],metric_version=build[1],cutoffs=cutoffs,warnings=warnings or ["Historical archive; latest season incomplete. Tournament dates are approximate."])

@app.exception_handler(TimeoutError)
@app.exception_handler(httpx.TimeoutException)
async def provider_timeout(request,error):
    return JSONResponse(status_code=503,content={"detail":{"code":"provider_unavailable","message":"The analyst request timed out. Browsing, examples and predictions remain available."}})

@app.exception_handler(duckdb.InterruptException)
async def query_timeout(request,error):
    return JSONResponse(status_code=504,content={"detail":{"code":"query_timeout","message":"Query exceeded the 10-second limit. Narrow the filters and retry."}})

@app.exception_handler(RequestValidationError)
async def invalid_filters(request,error):
    return JSONResponse(status_code=422,content={"detail":{"code":"invalid_filters","message":"Invalid request fields or filters.","fields":[{"location":list(e["loc"]),"message":e["msg"]} for e in error.errors()]}})

@app.exception_handler(ValueError)
async def invalid(request,error):
    message=str(error)
    code="unsupported_date" if any(x in message.lower() for x in ("supported statistics","unsupported scenario date","valid historical training")) else "insufficient_data" if "insufficient" in message.lower() else "invalid_request"
    return JSONResponse(status_code=422,content={"detail":{"code":code,"message":message}})

@app.get("/api/v1/status",response_model=AnalyticalResponse)
def status(con=Depends(database)):return envelope(con,services.status(con))

@app.get("/api/v1/coverage",response_model=AnalyticalResponse)
def coverage(tour:Literal["ATP","WTA"]="ATP",season:int=2024,con=Depends(database)):
    return envelope(con,services.venue_coverage(con,tour,season),filters={"tour":tour,"season":season})

@app.get("/api/v1/players",response_model=AnalyticalResponse)
def players(q:str=Query(default="",max_length=100),tour:Literal["ATP","WTA"]="ATP",limit:int=Query(default=30,ge=1,le=100),start:date|None=None,end:date|None=None,surface:Literal["Hard","Clay","Grass","Carpet"]|None=None,con=Depends(database)):
    return envelope(con,services.players(con,q,tour,limit,start,end,surface),filters={"q":q,"tour":tour,"limit":limit,"start":start,"end":end,"surface":surface})

@app.get("/api/v1/players/{player_id}",response_model=AnalyticalResponse)
def profile(player_id:str,surface:Literal["Hard","Clay","Grass","Carpet"]|None=None,end:date|None=None,con=Depends(database)):
    return envelope(con,services.player_profile(con,player_id,surface,end))

@app.get("/api/v1/metrics",response_model=AnalyticalResponse)
def metric_definitions(con=Depends(database)):return envelope(con,{**{k:{"definition":v[2],"aggregation":"ratio_of_sums"} for k,v in METRICS.items()},**{k:{"definition":v,"aggregation":"as_of_observation"} for k,v in ASOF_METRICS.items()}})

@app.post("/api/v1/metrics/query",response_model=AnalyticalResponse)
def metrics(q:MetricQuery,con=Depends(database)):return envelope(con,query_metrics(con,q))

@app.get("/api/v1/matches",response_model=AnalyticalResponse)
def matches(tour:Literal["ATP","WTA"]="ATP",season:int=2024,q:str=Query(default="",max_length=100),limit:int=Query(default=40,ge=1,le=100),con=Depends(database)):
    return envelope(con,records(con,"SELECT match_id,tour,event,season,surface,observed_date,winner_name,loser_name,score,round FROM main.matches WHERE tour=? AND season=? AND(event ILIKE ? OR winner_name ILIKE ? OR loser_name ILIKE ?) ORDER BY observed_date DESC,match_id LIMIT ?",[tour,season,"%"+q+"%","%"+q+"%","%"+q+"%",limit]))

@app.get("/api/v1/matches/{match_id}",response_model=AnalyticalResponse)
def match_detail(match_id:str,con=Depends(database)):
    m=records(con,"SELECT * FROM main.matches WHERE match_id=?",[match_id])
    if not m:raise HTTPException(404,detail={"code":"not_found","message":"Unknown historical match"})
    prediction=records(con,"SELECT * FROM main.predictions WHERE match_id=?",[match_id])
    return envelope(con,dict(match=m[0],predictions=prediction),filters={"match_id":match_id})

@app.post("/api/v1/matchups",response_model=AnalyticalResponse)
def matchup(q:services.MatchupQuery,con=Depends(database)):
    return envelope(con,services.matchup(con,q,serving_path().parent/"models"))

@app.get("/api/v1/replays",response_model=AnalyticalResponse)
def replays(tour:Literal["ATP","WTA"]="ATP",season:int|None=None,q:str=Query(default="",max_length=100),con=Depends(database)):
    return envelope(con,records(con,"SELECT * FROM main.replay_matches WHERE tour=? AND (? IS NULL OR season=?) AND(concat(player1,' ',player2,' ',event) ILIKE ?) ORDER BY season DESC,match_id LIMIT 100",[tour,season,season,"%"+q+"%"]))

@app.get("/api/v1/replays/{match_id}",response_model=AnalyticalResponse)
def replay(match_id:str,con=Depends(database)):
    meta=records(con,"SELECT * FROM main.replay_matches WHERE match_id=?",[match_id])
    if not meta:raise HTTPException(404,detail={"code":"replay_ineligible","message":"Replay unavailable: source progression or scoring eligibility was not verified."})
    return envelope(con,dict(match=meta[0],points=records(con,"SELECT * FROM main.replay_points WHERE match_id=? ORDER BY point",[match_id])),filters={"match_id":match_id})

@app.post("/api/v1/analyst",response_model=AnalyticalResponse)
async def analyst(body:AnalystRequest,request:Request):
    login=user(request);check_origin(request)
    from .analyst import run_analyst
    with analyst_slot(login):result=await run_analyst(body.question,**analyst_options(body))
    con=connect(serving_path(),read_only=True)
    try:return envelope(con,result)
    finally:con.close()

@app.post("/api/v1/analyst/stream",response_class=StreamingResponse,responses={200:{"content":{"text/event-stream":{}},"description":"SSE status, delta, reset, done (AnalyticalResponse), or error events."}})
async def analyst_stream(body:AnalystRequest,request:Request):
    login=user(request);check_origin(request)
    from .analyst import run_analyst
    # Authentication, origin and quota errors remain ordinary HTTP errors before headers.
    slot=analyst_slot(login);slot.__enter__()
    released=False
    async def release():
        nonlocal released
        if not released:
            released=True;slot.__exit__(None,None,None)
    async def events():
        queue=asyncio.Queue(maxsize=64)
        async def emit(event,data):await queue.put((event,data))
        async def run():
            try:
                result=await run_analyst(body.question,**analyst_options(body),on_event=emit)
                con=connect(serving_path(),read_only=True)
                try:result=jsonable_encoder(envelope(con,result,filters=analyst_options(body)["context"]))
                finally:con.close()
                await emit("done",result)
            except (TimeoutError,httpx.TimeoutException):
                await emit("error",{"code":"provider_timeout","message":"The AI took too long to respond. Please retry or ask a shorter tennis question."})
            except HTTPException as error:await emit("error",error.detail)
            except Exception:
                await emit("error",{"code":"provider_unavailable","message":"The tennis analyst could not finish this response. Please try again."})
        task=asyncio.create_task(run())
        try:
            yield 'event: status\ndata: {"message":"Connecting to Baseline…"}\n\n'
            while True:
                try:event,data=await asyncio.wait_for(queue.get(),timeout=4)
                except TimeoutError:
                    yield ': keep-alive\n\n';continue
                yield f'event: {event}\ndata: {json.dumps(data,default=str)}\n\n'
                if event in ("done","error"):break
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):await task
            await release()
    return StreamingResponse(events(),media_type="text/event-stream",headers={"Cache-Control":"no-store","X-Accel-Buffering":"no"},background=BackgroundTask(release))

@app.get("/health/ready")
def ready():
    from .release import check_release
    try:check_release(serving_path().parent)
    except Exception as e:raise HTTPException(503,detail={"code":"version_mismatch","message":str(e)})
    return {"ready":True}

static=ROOT/"frontend/dist"
if (static/"assets").exists():app.mount("/assets",StaticFiles(directory=static/"assets"),name="assets")
@app.get("/{route:path}",include_in_schema=False)
def frontend(route:str):
    if route.startswith(("api/","health/")):raise HTTPException(404)
    if (static/"index.html").exists():return FileResponse(static/"index.html")
    return JSONResponse({"message":"Build the frontend: npm --prefix frontend run build"},status_code=503)
