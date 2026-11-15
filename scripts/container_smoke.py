"""Check the running production image using only Python's standard library."""
import json
import os
import time
from urllib.request import Request,urlopen
from urllib.parse import quote,urlencode

origin=os.environ.get('BASELINE_SMOKE_ORIGIN','http://127.0.0.1:8000')
checks=[]
def request(path,payload=None):
    body=json.dumps(payload).encode() if payload is not None else None
    with urlopen(Request(origin+path,data=body,headers={'Content-Type':'application/json'}),timeout=60) as response:
        assert response.status==200
        value=response.read()
        checks.append(path)
        return json.loads(value) if 'application/json' in response.headers.get('content-type','') else value


def main():
    for _ in range(40):
        try:request('/health/ready');break
        except Exception:time.sleep(2)
    else:raise RuntimeError('Container did not become ready')
    request('/');request('/ask');status=request('/api/v1/status')['data']
    for tour in ('ATP','WTA'):
        players=request('/api/v1/players?tour='+tour)['data'];assert players
        request('/api/v1/players/'+players[0]['player_id'])
        matches=request('/api/v1/matches?'+urlencode({'tour':tour,'season':2024}))['data'];assert matches
        request('/api/v1/matches/'+quote(matches[0]['match_id'],safe=''))
        replay=request('/api/v1/replays?tour='+tour)['data'];assert replay
        points=request('/api/v1/replays/'+quote(replay[0]['match_id'],safe=''))['data'];assert points['points']
        request('/api/v1/metrics/query',{'tour':tour,'metrics':['first_serve_won','return_points_won'],'group_by':['surface']})
    for a,b,day in [('atp:104745','atp:104925','2024-06-01'),('wta:200033','wta:201458','2018-06-01')]:
        # Look up the historical WTA pair instead of relying on remembered IDs.
        if a.startswith('wta:'):
            a=request('/api/v1/players?tour=WTA&q=Halep')['data'][0]['player_id']
            b=request('/api/v1/players?tour=WTA&q=Kerber')['data'][0]['player_id']
        body={'player_a':a,'player_b':b,'as_of':day,'surface':'Hard','best_of':3}
        first=request('/api/v1/matchups',body)['data']
        second=request('/api/v1/matchups',{**body,'player_a':b,'player_b':a})['data']
        assert abs(first['probability_a']+second['probability_a']-1)<1e-9
    print(json.dumps({'status':'passed','requests':len(checks),'snapshot':status['snapshot']}))


if __name__=='__main__':main()
