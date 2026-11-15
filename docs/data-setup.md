# Baseline cached-source and build guide

Baseline uses ATP/WTA main-tour singles, source-qualified point/charting data, Valuebetennis odds and verified venue/weather enrichment. Vision assets are outside this product. Existing unrelated files are preserved. The former acquisition guide, including its local working changes, is preserved in `docs/archive/data-setup-before-baseline.md` for historical context.

## Existing caches

Expected layout:

```text
data/raw/sackmann_archive/{atp,wta,slam_pointbypoint}/
data/raw/match_charting/
data/raw/odds/valuebetennis/
data/raw/weather/
data/source-lock.json
```

The archive/Match Charting commit locks already in the repository are authoritative. Keep original READMEs/licenses and `.download.json` receipts. Do not redownload, replace or refresh cached snapshots during a normal build. Do not fetch tennis-data.co.uk. Data presence is distinct from analytical validation and latest-season completeness.

A new contributor without caches may explicitly acquire the core group:

```sh
python3 ingest/download.py fetch --group core
python3 ingest/download.py inventory --check-core
```

Alternatively download the [archive](https://github.com/Aneeshers/tennis-sackmann-archive) and [charting](https://github.com/JeffSackmann/tennis_MatchChartingProject) ZIPs and import them into empty destinations:

```sh
python3 ingest/download.py import-zip --source sackmann_archive --zip /path/to/archive.zip
python3 ingest/download.py import-zip --source match_charting --zip /path/to/charting.zip
```

Browser ZIP imports retain unverified revision status and do not inherit a lock's commit claim. Odds season CSVs from [Valuebetennis](https://www.valuebetennis.com/en/donnees.htm) belong under `data/raw/odds/valuebetennis/` with original filenames. Existing receipts include original acquisition times and hashes. No lower-tour product is published even when source files contain lower tours.

## Reproduce

Install Python 3.11, uv and Node 22+, then run:

```sh
uv sync --locked
npm --prefix frontend ci
uv run baseline inspect
uv run baseline build --sample
uv run baseline openapi
npm --prefix frontend run types
npm --prefix frontend run build
uv run baseline verify
```

Use `uv run baseline build` for all cached history. It profiles, loads raw records, builds/tests dbt marts, generates frozen features, accounts for venue coverage, resolves exact odds identities/matches, trains chronological models, benchmarks their common odds subset, computes eligible replay probabilities, and packages an immutable serving release.

`artifacts/source-profile.json` records per-file hashes, schema fingerprints, byte sizes, acquisition/revision evidence, run IDs, row counts, observed raw date ranges, and malformed-width records. Normalization records original CSV record ordinals, not physical line numbers. It never edits original sources. Source-family raw tables preserve strings for identifiers and source dates; typed dates/IDs are explicit in marts. Re-importing an identical snapshot does not append records. A changed snapshot rebuilds source tables; `meta.source_revisions` records the snapshot history.

Raw row reconciliation means imported plus quarantined CSV records equals the original logical records. dbt tests enforce canonical keys and relationships; `artifacts/validation.json` reports counts/exclusions. Weather, odds and replay coverage are separate reports. Source age does not cause archived data to fail freshness checks.

## Venue seeds and acquisition

`data/venue-history.csv` is an authored, versioned seed with fields:

```text
tour,edition_id,venue,city,country,latitude,longitude,timezone,elevation_m,effective_from,effective_to,event_start,event_end,verification_source,confidence,indoor
```

Each edition requires a verified assignment and documented historical event bounds. Use IANA timezones. Confidence must be `verified` with a verification source. Do not fill coordinates from a guessed city or event name; multiple assignments remain unavailable pending multi-venue review. An empty seed leaves each edition explicitly unavailable. Verified altitude is optional; gridded model elevation must not be mislabeled as an independently verified venue measurement.

`uv run baseline enrich` reuses caches. `uv run baseline enrich --acquire` explicitly obtains missing Open-Meteo ERA5 responses for verified seeds. Requests cache by parameter hash so retries skip completed requests. Stored responses include request parameters, URL and acquisition time. Hourly local times aggregate into daily temperature/humidity/precipitation/wind; they describe gridded outdoor event-period estimates, including for indoor tournaments. They never enter pre-match models.

## Identity overrides

Optional `data/identity-overrides.csv` columns: `source,tour,source_id,player_id,reason,verified_by,verified_at`. Use Git history for override history. Source and tour are mandatory namespaces. Automatic matching accepts only unique normalized full name and activity evidence. Ambiguous/no-match records remain excluded. Approximate names require reviewed overrides; no fuzzy candidate is silently accepted. Odds matching requires unique event/player-pair/date-range candidates and rejects duplicate canonical matches.

## Disk and checkpoints

The raw snapshot is about 1.36 GB. Allow roughly 5 GiB additional working space for normalization, DuckDB/transformation work and model/replay artifacts, plus a 5 GiB free-space reserve. The exact warehouse/serving sizes depend on scope; check `df -h .` first. Normalization and warehouse files stay ignored. One current and one previous serving artifact remain for rollback. Source caches are never deleted by retention.

Live analyst evaluation checkpoints `artifacts/agent-evaluation.json` after each completed analyst, SQL-baseline and grading stage; retries reuse finished stages. Run `make agent-eval` to load private local configuration, including the saved key in preference to inherited shell values. The frozen dataset checksum prevents silently changing questions. Provider/analyst revisions identify the run; old results are archived if those revisions change. Structured metric cases include governed reference data for grading. A missing key records `blocked_credentials`; quota exhaustion and provider unavailability record resumable states. It does not invent evaluation results.
