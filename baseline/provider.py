"""Pinned free-tier provider transport; bounded retries, no model fallback."""
import asyncio
import os
import httpx
from fastapi import HTTPException

MODEL='gemini-3.8-flash'


async def generate_content(payload):
    key=os.environ.get('GEMINI_API_KEY')
    if not key or os.environ.get('GEMINI_FREE_TIER_CONFIRMED')!='true':
        raise HTTPException(503,detail={'code':'provider_unavailable','message':'A confirmed free-tier key with billing disabled is required.'})
    async with httpx.AsyncClient(timeout=30) as client:
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
