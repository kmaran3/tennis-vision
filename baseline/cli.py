"""Offline build commands. Refreshing cached source snapshots is never implicit."""
import argparse
import json
import os
import subprocess
from .config import ROOT, WAREHOUSE, ARTIFACTS, write_json

def dbt(command):
    env={**os.environ,"BASELINE_WAREHOUSE":str(WAREHOUSE),"DBT_SEND_ANONYMOUS_USAGE_STATS":"false"}
    subprocess.run([str(ROOT/".venv/bin/dbt"),*command,"--project-dir",str(ROOT/"dbt"),"--profiles-dir",str(ROOT/"dbt")],cwd=ROOT,env=env,check=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=["inspect","load","dbt","features","validate","enrich","train","bridges","charting","replay","package","rollback","build","openapi","agent-eval","verify"])
    parser.add_argument("--sample",action="store_true")
    parser.add_argument("--acquire",action="store_true",help="Explicitly acquire Open-Meteo data only for verified venue seeds")
    args=parser.parse_args()
    from . import warehouse, temporal, modeling, identity, enrichment, replay, release, semantic, charting
    command=args.command
    if command=="inspect":print(json.dumps({k:v for k,v in warehouse.inspect(args.sample).items() if k!="files"},indent=2))
    elif command=="load":warehouse.load(args.sample)
    elif command=="dbt":semantic.generate();dbt(["build"])
    elif command=="features":
        print(temporal.build_features())
        from .feature_marts import build
        build()
    elif command=="validate":print(json.dumps(warehouse.validate(),indent=2))
    elif command=="enrich":print(enrichment.enrich(args.acquire))
    elif command=="bridges":print(identity.build_bridges())
    elif command=="charting":charting.build_charting();charting.attach_metric_columns()
    elif command=="train":modeling.train();identity.market_evaluation()
    elif command=="replay":print("Eligible replays:",replay.build_replays(limit=10 if args.sample else None))
    elif command=="package":print(release.package())
    elif command=="rollback":release.rollback()
    elif command=="openapi":
        from .api import app
        write_json(ARTIFACTS/"openapi.json",app.openapi())
    elif command=="agent-eval":
        from .evaluation import evaluate
        __import__("asyncio").run(evaluate())
    elif command=="verify":
        subprocess.run([str(ROOT/".venv/bin/python"),"-m","pytest","-q"],cwd=ROOT,check=True)
        subprocess.run(["npm","--prefix","frontend","run","build"],cwd=ROOT,check=True)
        warehouse.validate();release.check_release(__import__("baseline.config",fromlist=["serving_path"]).serving_path().parent)
    elif command=="build":
        warehouse.load(args.sample);print("M0: cached snapshot inspected and loaded",flush=True)
        semantic.generate();dbt(["build"]);print("M1: core warehouse built and dbt tests passed",flush=True)
        temporal.build_features()
        from .feature_marts import build
        build()
        warehouse.validate();print("M3: conservative features generated; remaining acceptance tests documented",flush=True)
        enrichment.enrich(args.acquire);identity.build_bridges();print("M4: all supported editions accounted for; venue verification remains incomplete",flush=True)
        charting.build_charting();charting.attach_metric_columns()
        modeling.train();identity.market_evaluation();print("M5: chronological model report generated",flush=True)
        replay.build_replays(limit=10 if args.sample else None);print("M6: source-qualified charting/Slam replays and shot analysis built; exclusions documented",flush=True)
        print(release.package())

if __name__=="__main__":main()
