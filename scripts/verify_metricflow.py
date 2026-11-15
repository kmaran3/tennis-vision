"""Integration check: actual MetricFlow SQL results versus independent SQL."""
import csv
import json
import os
from pathlib import Path
import subprocess
from baseline.config import ROOT,ARTIFACTS,WAREHOUSE,connect,write_json

def main():
    env={**os.environ,"DBT_PROJECT_DIR":str(ROOT/"dbt"),"DBT_PROFILES_DIR":str(ROOT/"dbt"),"BASELINE_WAREHOUSE":str(WAREHOUSE),"DBT_SEND_ANONYMOUS_USAGE_STATS":"false"}
    mf=str(ROOT/".venv/bin/mf")
    subprocess.run([mf,"validate-configs","--skip-dw"],cwd=ROOT,env=env,check=True)
    output=ARTIFACTS/"metricflow-parity.csv"
    subprocess.run([mf,"query","--metrics","first_serve_won","--group-by","player_match__tour","--start-time","2000-01-01","--end-time","2027-01-01","--csv",str(output)],cwd=ROOT,env=env,check=True)
    rows=list(csv.DictReader(output.open()))
    con=connect(WAREHOUSE,True)
    expected=dict(con.execute("SELECT tour,sum(first_won)::DOUBLE/sum(first_in) FROM main.player_matches WHERE observed_date>=DATE '2000-01-01' AND first_won IS NOT NULL AND first_in IS NOT NULL AND first_won>=0 AND first_in>=first_won GROUP BY 1").fetchall())
    con.close()
    for row in rows:
        tour=row.get("player_match__tour") or row.get("tour")
        assert abs(float(row["first_serve_won"])-expected[tour])<1e-9,(row,expected)
    assert len(rows)==len(expected)
    write_json(ARTIFACTS/"metricflow-verification.json",dict(status="passed",rows=rows,independent_sql=expected,versions={"dbt_core":"1.11.17","dbt_duckdb":"1.11.1","dbt_metricflow":"0.12.0","metricflow":"0.210.0"}))
    print("MetricFlow parity passed")

if __name__=="__main__":main()
