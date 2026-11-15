"""Snapshot ingestion: fail closed on parse errors; never redownload sources."""
from __future__ import annotations
import csv
import hashlib
import json
import re
import uuid
from pathlib import Path
from .config import ROOT, DATA, WAREHOUSE, ARTIFACTS, connect, digest, records, reserve, utcnow, write_json


def source_files(sample=False):
    raw = DATA / "raw"
    for tour in ("atp", "wta"):
        base = raw / "sackmann_archive" / tour
        for p in sorted(base.glob("*.csv")):
            if re.fullmatch(tour + r"_matches_\d{4}\.csv", p.name):
                year = int(p.stem[-4:])
                if sample and not 2022 <= year <= 2024:
                    continue
                yield "sackmann_archive", tour + "_matches", p
            elif p.name == tour + "_players.csv":
                yield "sackmann_archive", tour + "_players", p
            elif "rankings" in p.name:
                if sample and not any(x in p.name for x in ("20s", "current")):
                    continue
                yield "sackmann_archive", tour + "_rankings", p
    for p in sorted((raw / "odds/valuebetennis").glob("*.csv")):
        if not sample or "2024" in p.name:
            yield "valuebetennis", "odds", p
    for p in sorted((raw / "match_charting").glob("*.csv")):
        if "-matches" in p.name or "-points" in p.name or "-stats-" in p.name:
            gender = "atp" if "-m-" in p.name else "wta"
            family = "chart_" + gender + ("_matches" if "-matches" in p.name else "_points" if "-points" in p.name else "_" + p.stem.split("-stats-")[1].lower())
            if sample and "-points" in p.name and "2020s" not in p.name:
                continue
            yield "match_charting", family, p
    for p in sorted((raw / "sackmann_archive/slam_pointbypoint").glob("*.csv")):
        if re.fullmatch(r"\d{4}-[a-z]+-(points|matches)\.csv", p.name):
            if not sample or p.name.startswith("2024-"):
                yield "sackmann_archive", "slam_" + p.stem.rsplit("-", 1)[1], p


def inspect(sample=False):
    lock = json.loads((DATA / "source-lock.json").read_text())
    items = []
    for source, family, path in source_files(sample):
        base = DATA / "raw" / ("odds/valuebetennis" if source == "valuebetennis" else source)
        receipt_path = base / ".download.json"
        receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
        with path.open(encoding="utf-8-sig", newline="") as f:
            header = next(csv.reader(f, delimiter=";" if family == "odds" else ","))
        checksum = digest(path)
        expected = receipt.get("files", {}).get(str(path.relative_to(base)), {}).get("sha256")
        items.append(dict(source=source, family=family, path=str(path.relative_to(ROOT)),
                          sha256=checksum, bytes=path.stat().st_size,
                          acquired_at=receipt.get("acquired_at"), revision=receipt.get("revision"),
                          locked_revision=lock.get(source, {}).get("revision"),
                          changed_since_acquisition=bool(expected and expected != checksum),
                          schema_sha256=hashlib.sha256(json.dumps(header).encode()).hexdigest(),
                          columns=header, parsing_errors=[]))
    if not items:
        raise RuntimeError("No cached sources found. See docs/data-setup.md.")
    required={"atp_matches","wta_matches","atp_players","wta_players","atp_rankings","wta_rankings","odds","chart_atp_matches","chart_wta_matches","chart_atp_points","chart_wta_points","slam_matches","slam_points"}
    missing=required-{i["family"] for i in items}
    if missing:raise RuntimeError("Incomplete cached snapshot: "+", ".join(sorted(missing))+". Existing warehouse left unchanged; restore the missing cached sources.")
    snapshot = hashlib.sha256(json.dumps([(i["path"], i["sha256"]) for i in items]).encode()).hexdigest()
    report = dict(snapshot=snapshot, sample=sample, generated_at=utcnow(), files=items,
                  bytes=sum(i["bytes"] for i in items))
    write_json(ARTIFACTS / "source-inspection.json", report)
    return report


def load(sample=False):
    reserve(5)
    report = inspect(sample)
    con = connect()
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    con.execute("CREATE SCHEMA IF NOT EXISTS meta")
    con.execute("CREATE TABLE IF NOT EXISTS meta.build (snapshot VARCHAR, metric_version VARCHAR, built_at VARCHAR, sample BOOLEAN)")
    old = con.execute("SELECT snapshot FROM meta.build").fetchone()
    if old and old[0] == report["snapshot"]:
        con.close()
        print("Identical snapshot already loaded; no duplicate imports.")
        return report
    run = str(uuid.uuid4())
    con.execute("CREATE TABLE IF NOT EXISTS meta.source_revisions (snapshot VARCHAR, run_id VARCHAR, imported_at VARCHAR)")
    con.execute("BEGIN")
    try:
        families = sorted({x["family"] for x in report["files"]})
        for family in families:
            entries = [x for x in report["files"] if x["family"] == family]
            cached = []
            for entry in entries:
                path = ROOT / entry["path"]
                normalized = DATA / "cache/normalized" / (entry["sha256"] + "-" + hashlib.sha256(entry["path"].encode()).hexdigest()[:12] + ".csv")
                normalized.parent.mkdir(parents=True, exist_ok=True)
                # A canonical CSV removes inconsistent quoting in upstream free text.
                # It preserves original record ordinals and quarantines width errors.
                errors = []
                dates = []
                with path.open(encoding="utf-8-sig", newline="") as source, normalized.open("w", newline="") as target:
                    reader = csv.reader(source, delimiter=";" if family == "odds" else ",")
                    header = next(reader)
                    writer = csv.writer(target)
                    writer.writerow(header+["source_file", "source_row"])
                    count = 0
                    date_col = next((header.index(c) for c in ("tourney_date","ranking_date","Date","date") if c in header), None)
                    for ordinal, row in enumerate(reader, 1):
                        if len(row) != len(header):
                            errors.append({"source_row": ordinal, "reason": "column_count", "expected":len(header), "observed":len(row)})
                            continue
                        writer.writerow(row+[entry["path"],ordinal]); count += 1
                        if date_col is not None and row[date_col]: dates.append(row[date_col])
                entry.update(row_count=count, ingestion_run=run, parsing_errors=errors,
                             observed_date_min=min(dates) if dates else None, observed_date_max=max(dates) if dates else None)
                cached.append(str(normalized))
            con.execute(f"CREATE OR REPLACE TABLE raw.{family} AS SELECT * EXCLUDE(source_row), source_row::BIGINT AS source_row FROM read_csv(?, all_varchar=true, header=true, delim=',', quote='\"', escape='\"', union_by_name=true, parallel=false)", [cached])
            print(f"Loaded {family}: {sum(e['row_count'] for e in entries):,} rows", flush=True)
        from .config import METRIC_VERSION
        con.execute("DELETE FROM meta.build")
        con.execute("INSERT INTO meta.build VALUES (?, ?, ?, ?)", [report["snapshot"], METRIC_VERSION, utcnow(), sample])
        con.execute("INSERT INTO meta.source_revisions VALUES (?, ?, ?)", [report["snapshot"], run, utcnow()])
        write_json(ARTIFACTS / "source-profile.json", report)
        con.execute("CREATE OR REPLACE TABLE meta.source_manifest AS SELECT unnest(files) AS file FROM read_json_auto(?)", [str(ARTIFACTS / "source-profile.json")])
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()
    write_json(ARTIFACTS / "source-profile.json", report)
    return report


def validate():
    con = connect(read_only=True)
    checks = {
        "unique_matches": "SELECT count(*)-count(distinct match_id) FROM main.matches",
        "unique_players": "SELECT count(*)-count(distinct player_id) FROM main.players",
        "two_sides": "SELECT count(*) FROM (SELECT match_id FROM main.player_matches GROUP BY 1 HAVING count(*)<>2)",
        "player_relationships": "SELECT count(*) FROM main.player_matches p LEFT JOIN main.players d USING(player_id) WHERE d.player_id IS NULL",
        "tour_isolation": "SELECT count(*) FROM main.player_matches WHERE NOT starts_with(player_id, lower(tour)||':')",
        "different_players": "SELECT count(*) FROM main.matches WHERE winner_id=loser_id",
        "player_feature_grain":"SELECT count(*) FROM (SELECT match_id FROM main.player_features GROUP BY 1 HAVING count(*)<>2 OR count(distinct player_id)<>2)",
        "temporal_cutoff": "SELECT count(*) FROM main.features WHERE max_contributing_time>=feature_cutoff",
    }
    results = {key: con.execute(sql).fetchone()[0] for key, sql in checks.items()}
    results["counts"] = {name: con.execute(f"SELECT count(*) FROM main.{name}").fetchone()[0] for name in ("matches", "players", "player_matches", "rankings", "features")}
    results["exclusions"] = records(con, "SELECT tour, exclusion_reason, count(*) AS records FROM main.match_exclusions GROUP BY 1,2")
    con.close()
    write_json(ARTIFACTS / "validation.json", results)
    if any(results[k] for k in checks):
        raise RuntimeError(f"Data validation failed: {results}")
    return results
