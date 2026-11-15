"""Pinned free-tier provider transport; bounded retries, no model fallback."""
import asyncio
import os
import json
import httpx
from fastapi import HTTPException

MODEL='gemini-3.5-flash-lite'


async def generate_content(payload):
    key=os.environ.get('GEMINI_API_KEY')
    if not key or os.environ.get('GEMINI_FREE_TIER_CONFIRMED')!='true':
        raise HTTPException(503,detail={'code':'provider_unavailable','message':'A confirmed free-tier key with billing disabled is required.'})
    async with httpx.AsyncClient(timeout=httpx.Timeout(15,connect=5)) as client:
        for attempt in range(3):
            response=await client.post(f'https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent',headers={'x-goog-api-key':key},json=payload)
            if response.status_code in (502,503,504) and attempt<2:
                await asyncio.sleep(2**(attempt+1))
                continue
            if response.status_code==429:
                details=response.json().get('error',{}).get('details',[])
                violations=[{k:v[k] for k in ('quotaMetric','quotaId','quotaValue','quotaDimensions') if k in v} for d in details for v in d.get('violations',[])]
                raise HTTPException(429,detail={'code':'quota_exhausted','message':'Free provider quota exhausted; browsing and predictions remain available.','provider_requests':attempt+1,'quota_limits':violations})
            if response.is_error:
                raise HTTPException(503,detail={'code':'provider_unavailable','message':'The analyst provider is temporarily unavailable. Browsing and predictions remain available.','provider_http_status':response.status_code,'provider_requests':attempt+1})
            return response.json(),attempt+1


async def stream_content(payload):
    """Yield original Gemini chunks. Never retry a partially delivered response."""
    key=os.environ.get('GEMINI_API_KEY')
    if not key or os.environ.get('GEMINI_FREE_TIER_CONFIRMED')!='true':
        raise HTTPException(503,detail={'code':'provider_unavailable','message':'A confirmed free-tier key with billing disabled is required.'})
    url=f'https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:streamGenerateContent?alt=sse'
    async with httpx.AsyncClient(timeout=httpx.Timeout(15,connect=5)) as client:
        for attempt in range(2):
            async with client.stream('POST',url,headers={'x-goog-api-key':key},json=payload) as response:
                if response.status_code in (502,503,504) and attempt==0:
                    await asyncio.sleep(1)
                    continue
                if response.is_error:
                    await response.aread()
                    code='quota_exhausted' if response.status_code==429 else 'provider_unavailable'
                    message='The free AI quota is exhausted. Please try again later.' if response.status_code==429 else 'The tennis analyst is temporarily unavailable. Please try again.'
                    raise HTTPException(429 if response.status_code==429 else 503,detail={'code':code,'message':message})
                data=[]
                async for line in response.aiter_lines():
                    if line.startswith('data:'):data.append(line[5:].lstrip())
                    elif not line and data:
                        raw='\n'.join(data);data=[]
                        if raw!='[DONE]':yield json.loads(raw),attempt+1
                if data and '\n'.join(data)!='[DONE]':yield json.loads('\n'.join(data)),attempt+1
                return
