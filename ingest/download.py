#!/usr/bin/env python3
"""Download source snapshots or inventory manually supplied files (stdlib only)."""

import argparse
import csv
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
from datetime import datetime, timezone
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data/sources.json"
LOCK = ROOT / "data/source-lock.json"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def request(url):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "Tennis-Vision-data-setup/1.0"}),
        timeout=30,
    )


def download(url, destination):
    """Stream to disk; never treat a partial transfer as the final file."""
    temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        with request(url) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def extract_snapshot(archive, destination):
    """Strip GitHub's wrapper directory; reject unsafe paths and links."""
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        roots = set()
        for item in entries:
            path = PurePosixPath(item.filename)
            if (path.is_absolute() or ".." in path.parts or "\\" in item.filename
                    or not path.parts or stat.S_ISLNK(item.external_attr >> 16)):
                raise ValueError("Unsafe ZIP member: " + item.filename)
            roots.add(path.parts[0])
        if len(roots) != 1:
            raise ValueError("Expected one GitHub wrapper directory in ZIP")
        for item in entries:
            parts = PurePosixPath(item.filename).parts[1:]
            if not parts:
                continue
            target = destination.joinpath(*parts)
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(item) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)


def receipt(directory, url, revision=None):
    files = {
        str(path.relative_to(directory)): {"bytes": path.stat().st_size, "sha256": digest(path)}
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path.name != ".download.json"
    }
    if not files:
        raise ValueError("No files were acquired")
    write_json(directory / ".download.json", {
        "acquired_at": timestamp(), "url": url, "revision": revision, "files": files,
    })


def fetch_github(source, local_zip=None):
    destination = ROOT / source["destination"]
    if destination.exists() and any(destination.iterdir()):
        record = destination / ".download.json"
        if local_zip is None and record.exists():
            info = json.loads(record.read_text())
            if not info.get("files"):
                raise ValueError("Empty download receipt: " + str(record))
            for name, expected in info["files"].items():
                path = destination / name
                if not path.is_file() or digest(path) != expected["sha256"]:
                    raise ValueError("Cached file changed or missing: " + str(path))
            print("Verified cached snapshot: " + source["destination"])
            return
        raise ValueError("Destination already contains files; leaving it unchanged: " + str(destination))
    lock = json.loads(LOCK.read_text())
    revision = lock.get(source["id"], {}).get("revision")
    if local_zip is None and not revision:
        with request("https://api.github.com/repos/" + source["repo"] + "/commits/HEAD") as response:
            revision = json.load(response)["sha"]
    if revision and not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Expected a full GitHub commit SHA in source lock")
    url = ("https://codeload.github.com/" + source["repo"] + "/zip/" + revision
           if local_zip is None else source["url"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        workspace = Path(temporary)
        archive = Path(local_zip).expanduser() if local_zip else workspace / "download.zip"
        if local_zip is None:
            print("Downloading " + url, flush=True)
            download(url, archive)
        staged = workspace / "extracted"
        staged.mkdir()
        extract_snapshot(archive, staged)
        missing = [p for p in source.get("required_patterns", []) if not any(staged.glob(p))]
        if missing:
            raise ValueError("Snapshot missing required files: " + ", ".join(missing))
        receipt(staged, url, revision if local_zip is None else None)
        if local_zip:
            info = json.loads((staged / ".download.json").read_text())
            info["imported_archive_sha256"] = digest(archive)
            info["provenance_note"] = "Browser ZIP import; commit revision not verified"
            write_json(staged / ".download.json", info)
        if destination.exists():
            destination.rmdir()  # Only an empty destination is allowed above.
        staged.rename(destination)
    if local_zip is None:
        lock[source["id"]] = {"repo": source["repo"], "revision": revision}
        write_json(LOCK, lock)
    print("Saved " + source["destination"])


def validate_odds(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(16384)
        if "<html" in sample.lower() or "<!doctype" in sample.lower():
            raise ValueError("Received HTML instead of odds CSV")
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        handle.seek(0)
        rows = csv.reader(handle, dialect)
        header = next(rows)
        required = {"date", "joueur1", "joueur2", "cote1_cloture", "cote2_cloture"}
        if not required.issubset(header):
            raise ValueError("Unexpected Valuebetennis columns: " + repr(header))
        if next(rows, None) is None:
            raise ValueError("Odds CSV has no data rows")


def fetch_seasons(source, end_year):
    destination = ROOT / source["destination"]
    destination.mkdir(parents=True, exist_ok=True)
    failures = []
    for year in range(source["first_year"], end_year + 1):
        url = source["download_template"].format(year=year)
        path = destination / url.rsplit("/", 1)[1]
        try:
            if not path.exists():
                print("Downloading " + url, flush=True)
                with tempfile.TemporaryDirectory(dir=destination) as temporary:
                    staged = Path(temporary) / path.name
                    download(url, staged)
                    validate_odds(staged)
                    staged.rename(path)
            else:
                validate_odds(path)
        except (OSError, ValueError, csv.Error, StopIteration) as error:
            failures.append(str(year))
            print("FAILED " + str(year) + ": " + str(error), file=sys.stderr)
    if any(destination.glob("*.csv")):
        receipt(destination, source["url"])
    if failures:
        raise ValueError("Missing/invalid seasons: " + ", ".join(failures))


def inventory(sources, check_core=False, end_year=None):
    report = {"generated_at": timestamp(), "sources": []}
    core_missing = False
    for source in sources:
        directory = ROOT / source["destination"]
        files = [p for p in directory.rglob("*") if p.is_file()
                 and p.name not in {".gitkeep", ".download.json"}]
        missing = [p for p in source.get("required_patterns", []) if not any(directory.glob(p))]
        if source["method"] == "season_csv":
            for year in range(source["first_year"], end_year + 1):
                name = source["download_template"].format(year=year).rsplit("/", 1)[1]
                if not (directory / name).is_file():
                    missing.append(name)
        status = "present_unvalidated" if files and not missing else "missing_or_partial"
        if source["group"] == "core" and status != "present_unvalidated":
            core_missing = True
        report["sources"].append({"id": source["id"], "status": status,
                                  "file_count": len(files), "missing_patterns": missing})
        print("{:<24} {:<22} {} files".format(source["id"], status, len(files)))
    write_json(ROOT / "data/inventory.json", report)
    return 1 if check_core and core_missing else 0


def main():
    sources = json.loads(CATALOG.read_text())["sources"]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["list", "fetch", "import-zip", "inventory"])
    parser.add_argument("--group", choices=["core", "vision", "reference", "optional", "all"], default="core")
    parser.add_argument("--source", choices=[s["id"] for s in sources])
    parser.add_argument("--zip", help="Browser-downloaded GitHub source ZIP")
    parser.add_argument("--end-year", type=int, default=datetime.now(timezone.utc).year)
    parser.add_argument("--check-core", action="store_true", help="Exit nonzero if core files are missing")
    args = parser.parse_args()
    if args.end_year < 2021 or args.end_year > datetime.now(timezone.utc).year:
        parser.error("--end-year must be between 2021 and the current year")
    if args.command == "list":
        for source in sources:
            print("{:<24} {:<10} {:<12} {}".format(source["id"], source["group"], source["method"], source["destination"]))
        return 0
    if args.command == "inventory":
        return inventory(sources, args.check_core, args.end_year)
    selected = [s for s in sources if (s["id"] == args.source if args.source
                else args.group == "all" or s["group"] == args.group)]
    if args.command == "import-zip" and (not args.source or not args.zip or selected[0]["method"] != "github"):
        parser.error("import-zip requires --source for a GitHub source and --zip PATH")
    failed = False
    for source in selected:
        try:
            if source["method"] == "github":
                fetch_github(source, args.zip if args.command == "import-zip" else None)
            elif source["method"] == "season_csv":
                fetch_seasons(source, args.end_year)
            else:
                print("MANUAL " + source["id"] + ": see docs/data-setup.md")
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            print("FAILED " + source["id"] + ": " + str(error), file=sys.stderr)
            failed = True
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
