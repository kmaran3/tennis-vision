"""GitHub allowlist authentication and durable, atomic daily analyst caps."""
from __future__ import annotations
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlencode
import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from itsdangerous import URLSafeTimedSerializer, BadSignature
from .config import DATA

router=APIRouter(prefix="/api/v1/auth")

def origin():return os.environ.get("BASELINE_ORIGIN","http://localhost:8000").rstrip("/")
def secure():return origin().startswith("https://")
def serializer(salt):
    secret=os.environ.get("BASELINE_SESSION_SECRET","")
    if len(secret)<32:raise HTTPException(503,detail={"code":"auth_unavailable","message":"Set a session secret of at least 32 characters."})
    return URLSafeTimedSerializer(secret,salt=salt)
def allowlist():return {u.strip().lower() for u in os.environ.get("GITHUB_ALLOWED_USERS","").split(",") if u.strip()}

def user(request:Request):
    try:
        value=serializer("session").loads(request.cookies.get("baseline_session",""),max_age=86400)
        login=value["login"].lower()
    except (BadSignature,KeyError):raise HTTPException(401,detail={"code":"unauthorized","message":"Sign in with an approved GitHub account."})
    if login not in allowlist():raise HTTPException(403,detail={"code":"unauthorized","message":"This GitHub account is not approved for chat."})
    return login

def check_origin(request):
    if request.headers.get("origin")!=origin():raise HTTPException(403,detail={"code":"invalid_origin","message":"Request origin is not allowed."})

@router.get("/login")
def login():
    client=os.environ.get("GITHUB_CLIENT_ID")
    if not client:raise HTTPException(503,detail={"code":"auth_unavailable","message":"GitHub OAuth is not configured."})
    state=secrets.token_urlsafe(32)
    response=RedirectResponse("https://github.com/login/oauth/authorize?"+urlencode(dict(client_id=client,redirect_uri=origin()+"/api/v1/auth/callback",state=state)))
    response.set_cookie("baseline_oauth",serializer("oauth").dumps(state),httponly=True,secure=secure(),samesite="lax",max_age=600)
    return response

@router.get("/callback")
async def callback(request:Request,code:str,state:str):
    try:expected=serializer("oauth").loads(request.cookies.get("baseline_oauth",""),max_age=600)
    except BadSignature:raise HTTPException(403,detail={"code":"oauth_state","message":"OAuth state is invalid or expired."})
    if not secrets.compare_digest(expected,state):raise HTTPException(403,detail={"code":"oauth_state","message":"OAuth state did not match."})
    async with httpx.AsyncClient(timeout=10) as client:
        token_response=await client.post("https://github.com/login/oauth/access_token",headers={"Accept":"application/json"},json=dict(client_id=os.environ.get("GITHUB_CLIENT_ID"),client_secret=os.environ.get("GITHUB_CLIENT_SECRET"),code=code,redirect_uri=origin()+"/api/v1/auth/callback"))
        token=token_response.json().get("access_token")
        if not token:raise HTTPException(401,detail={"code":"oauth_failed","message":"GitHub authentication failed."})
        identity=await client.get("https://api.github.com/user",headers={"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json"})
        del token
    login=identity.json().get("login","").lower()
    if login not in allowlist():raise HTTPException(403,detail={"code":"unauthorized","message":"This GitHub account is not approved for chat."})
    response=RedirectResponse("/ask")
    response.set_cookie("baseline_session",serializer("session").dumps({"login":login}),httponly=True,secure=secure(),samesite="lax",max_age=86400)
    response.delete_cookie("baseline_oauth")
    return response

@router.get("/me")
def me(request:Request):
    try:return {"login":user(request),"approved":True}
    except HTTPException:return {"login":None,"approved":False}

@router.post("/logout")
def logout(request:Request):
    check_origin(request);response=RedirectResponse("/ask",status_code=303);response.delete_cookie("baseline_session");return response

@contextmanager
def analyst_slot(login,path=None):
    path=Path(path or os.environ.get("BASELINE_QUOTA_DB",str(DATA/"cache/analyst-quota.sqlite")))
    path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path,timeout=5,isolation_level=None)
    db.execute("CREATE TABLE IF NOT EXISTS turns(day TEXT, login TEXT, started REAL, lease TEXT PRIMARY KEY, active INT)")
    lease=secrets.token_hex(16);day=time.strftime("%Y-%m-%d",time.gmtime());now=time.time()
    try:
        db.execute("BEGIN IMMEDIATE")
        counts=db.execute("SELECT count(*),sum(login=?) FROM turns WHERE day=?",(login,day)).fetchone()
        active=db.execute("SELECT count(*) FROM turns WHERE login=? AND active=1 AND started>?",(login,now-180)).fetchone()[0]
        if active:raise HTTPException(429,detail={"code":"request_active","message":"An analyst request is already running for this user."})
        if counts[0]>=100 or (counts[1] or 0)>=20:raise HTTPException(429,detail={"code":"quota_exhausted","message":"Daily analyst quota exhausted. Browsing and predictions remain available."})
        db.execute("INSERT INTO turns VALUES(?,?,?,?,1)",(day,login,now,lease));db.execute("COMMIT")
        yield
    finally:
        if db.in_transaction:db.execute("ROLLBACK")
        db.execute("UPDATE turns SET active=0 WHERE lease=?",(lease,));db.close()
