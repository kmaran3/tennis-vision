"""Checksummed immutable serving artifacts and atomic local activation/rollback."""
from __future__ import annotations
import json
import os
import shutil
from pathlib import Path
from .config import DATA, ARTIFACTS, WAREHOUSE, METRIC_VERSION, connect, digest, write_json, reserve, utcnow
from .metrics import METRICS,ASOF_METRICS

TABLES=("matches","players","player_matches","rankings","editions","features","rating_history","predictions","odds_matches","venue_coverage","weather","replay_matches","replay_points","chart_matches","chart_player_metrics","chart_shot_profiles","player_features")
PUBLIC_REPORTS=('validation.json','model-evaluation.json','market-evaluation.json','charting-coverage.json','replay-coverage.json','enrichment-coverage.json','join-coverage.json','replay-prior-equivalence.json','weather-source-manifest.json')

def check_release(directory):
    directory=Path(directory)
    manifest=json.loads((directory/"manifest.json").read_text())
    if manifest["metric_version"]!=METRIC_VERSION:raise ValueError("Metric definition version mismatch")
    for name,checksum in manifest["files"].items():
        file=directory/name
        if not file.is_file() or digest(file)!=checksum:raise ValueError("Artifact checksum mismatch: "+name)
    con=connect(directory/"serving.duckdb",read_only=True)
    try:
        build=con.execute("SELECT snapshot,metric_version FROM meta.build").fetchone()
        if build!=(manifest["snapshot"],METRIC_VERSION):raise ValueError("Database snapshot/version mismatch")
        versions={r[0] for r in con.execute("SELECT DISTINCT model_version FROM main.predictions").fetchall()}
    finally:con.close()
    registry=json.loads((directory/"models/registry.json").read_text())
    if any(m["snapshot"]!=manifest["snapshot"] for m in registry):raise ValueError("Model snapshot mismatch")
    if not versions.issubset({m["version"] for m in registry}):raise ValueError("Prediction model missing from registry")
    return manifest


def activate(directory):
    root=DATA/"releases";directory=Path(directory).resolve()
    if directory.parent!=root.resolve():raise ValueError("Release must be inside data/releases")
    check_release(directory)
    current=root/"current";previous=root/"previous"
    if current.exists() and current.resolve()!=directory:
        tmp=root/".previous-next";tmp.unlink(missing_ok=True);tmp.symlink_to(current.resolve().name);tmp.replace(previous)
    tmp=root/".current-next";tmp.unlink(missing_ok=True);tmp.symlink_to(directory.name);tmp.replace(current)


def package():
    reserve(2)
    con=connect(WAREHOUSE,read_only=True);snapshot=con.execute("SELECT snapshot FROM meta.build").fetchone()[0];con.close()
    root=DATA/"releases";root.mkdir(parents=True,exist_ok=True)
    name=snapshot[:12]+"-"+__import__("time").strftime("%Y%m%d%H%M%S",__import__("time").gmtime())
    stage=root/(".stage-"+name);stage.mkdir()
    target=connect(stage/"serving.duckdb")
    escaped=str(WAREHOUSE).replace("'","''")
    target.execute(f"ATTACH '{escaped}' AS warehouse (READ_ONLY)")
    for name_ in TABLES:target.execute(f"CREATE TABLE main.{name_} AS SELECT * FROM warehouse.main.{name_}")
    target.execute("CREATE SCHEMA meta")
    target.execute("CREATE TABLE meta.build AS SELECT * FROM warehouse.meta.build")
    target.execute("CHECKPOINT");target.close()
    model_dir=stage/"models";model_dir.mkdir()
    registry=json.loads((ARTIFACTS/"model-registry.json").read_text())
    write_json(model_dir/"registry.json",registry)
    for m in registry:
        if m.get("xgboost_file"):shutil.copy2(DATA/"models/prematch"/m["xgboost_file"],model_dir/m["xgboost_file"])
    write_json(stage/"metrics.json",{k:dict(numerator=v[0],denominator=v[1],description=v[2]) for k,v in METRICS.items()})
    write_json(stage/"asof-metrics.json",ASOF_METRICS)
    notices=stage/"notices";notices.mkdir()
    originals={"sackmann-atp":DATA/"raw/sackmann_archive/atp/UPSTREAM_README.md","sackmann-wta":DATA/"raw/sackmann_archive/wta/UPSTREAM_README.md","sackmann-slam":DATA/"raw/sackmann_archive/slam_pointbypoint/UPSTREAM_README.md","match-charting":DATA/"raw/match_charting/README.md"}
    for label,path in originals.items():
        if path.exists():shutil.copy2(path,notices/(label+".md"))
    (notices/"attribution.md").write_text("Jeff Sackmann / Tennis Abstract and Match Charting Project contributors: CC BY-NC-SA 4.0. Valuebetennis tennis results and odds since 2021: CC BY 4.0, https://www.valuebetennis.com/en/donnees.htm . Historical weather: Open-Meteo ERA5 estimates, https://open-meteo.com/en/docs/historical-weather-api . Original source notices remain alongside these derived artifacts.\n")
    reports=stage/"reports";reports.mkdir()
    for name_ in PUBLIC_REPORTS:
        p=ARTIFACTS/name_
        if p.exists():shutil.copy2(p,reports/p.name)
    files={str(p.relative_to(stage)):digest(p) for p in stage.rglob("*") if p.is_file()}
    write_json(stage/"manifest.json",dict(snapshot=snapshot,metric_version=METRIC_VERSION,created_at=utcnow(),files=files))
    check_release(stage)
    release=root/name;stage.rename(release);activate(release)
    # Only generated, checksummed releases are eligible for retention cleanup.
    keep={p.resolve() for p in (root/"current",root/"previous") if p.exists()}
    for old in root.iterdir():
        if old.is_dir() and not old.is_symlink() and not old.name.startswith(".") and old.resolve() not in keep and (old/"manifest.json").exists():shutil.rmtree(old)
    return str(release)


def rollback():
    previous=DATA/"releases/previous"
    if not previous.exists():raise ValueError("No previous tested release available")
    activate(previous.resolve())
