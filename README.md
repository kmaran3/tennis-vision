# Baseline

A historical ATP/WTA singles analytics platform: explore players, compare historical matchups, inspect archived results, and replay eligible point records. Python/FastAPI serves a React application from one service. This is a local implementation in progress, **not a completed public release**.

See the [accepted specification](tennis-analytics-project-plan.md) and [measured implementation status](docs/implementation-status.md). No computer vision, live scores, future schedules, doubles, lower-tour product, betting recommendations, or paid services are included.

## Run locally

Requires Python 3.11, uv, Node 22+, and the existing cached sources (about 1.36 GB).

```sh
uv sync --locked
npm --prefix frontend ci
uv run baseline build --sample
uv run baseline openapi
npm --prefix frontend run types
npm --prefix frontend run build
make dev
```

Open http://localhost:8000, matching the default OAuth origin. The sample includes 2022–2024 core matches, current-decade rankings, 2024 odds/Slam points and selected charting shards. It labels itself SAMPLE BUILD. It intentionally has fewer model windows and no earlier rating warm-up. Full historical builds use:

```sh
uv run baseline build
uv run baseline verify
```

A build **never refreshes tennis snapshots**. Missing caches fail with an actionable error. Source locks and original data remain unchanged. See the [acquisition/build guide](docs/data-setup.md).

## Commands

| Operation | Command |
|---|---|
| Profile cached files | `uv run baseline inspect` |
| Raw load | `uv run baseline load` |
| dbt models/tests and generated semantics | `uv run baseline dbt` |
| dbt documentation | `uv run dbt docs generate --project-dir dbt --profiles-dir dbt` |
| Frozen features/Elo | `uv run baseline features` |
| Validate warehouse | `uv run baseline validate` |
| Identity/odds joins | `uv run baseline bridges` |
| Venue coverage/cached weather | `uv run baseline enrich` |
| Explicit initial weather acquisition | `uv run baseline enrich --acquire` |
| Chronological training/market benchmark | `uv run baseline train` |
| Charted points/shots | `uv run baseline charting` |
| Archived scoring replay | `uv run baseline replay` |
| Resumable analyst evaluation | `uv run baseline agent-eval` |
| Serving artifact/atomic activation | `uv run baseline package` |
| Restore previous tested release | `uv run baseline rollback` |
| Offline tests | `uv run pytest -q` |
| Frontend with API proxy | `npm --prefix frontend run dev` |
| Full local verification | `uv run baseline verify` |

Run commands from repository root. Outputs live under ignored `artifacts/`, `data/cache/`, and `data/releases/`. Only compact serving marts/models/metric definitions ship. dbt/DuckDB use two threads and a 2 GB memory cap; training uses one job. Builds enforce 5 GiB free-space reserve beyond operation working space. Keep enough space for raw caches, normalized CSVs, the warehouse, and current/previous serving artifacts.

## Analytical contract

Statistics begin in 2000. Earlier matches initialize history. Source cutoffs and incomplete latest seasons are explicit. Sackmann dates are tournament proxies: features freeze at tournament start and outcomes become available after 28 days. Ratings update in same-date batches, never by assumed match-number chronology. This conservative rule does not establish an unconditional leak-free guarantee.

Rates use ratios of summed pairwise-valid counts, with sample sizes and denominators. Null differs from zero. Elo is as-of. Models and market reports use chronological windows; ATP and WTA identities/models remain separate. Model/market/coverage results are generated from actual data under `artifacts/`, never invented. Historical scenarios require a model trained before their date. Realized weather and odds never enter pre-match features.

Current scope gaps are documented in the status file: broader enrichment verification and operational fixtures, measured live analyst evaluation, actual OAuth/provider behavior, container verification and deployment still have release gates.

## Chat and deployment

Public browsing needs no credentials. Set configuration through local environment variables or Railway's secret interface; never commit keys. `.env.example` lists required names. `make dev` and `make agent-eval` load the saved local `.env` with priority over inherited shell values. Other configured commands can use `uv run --no-env-file python scripts/with_env.py baseline <command>`. GitHub OAuth uses `/api/v1/auth/callback` at `BASELINE_ORIGIN`, a server-side username allowlist, signed HTTP-only cookies and origin validation. A session secret of at least 32 characters is required.

Live chat is disabled unless `GEMINI_API_KEY` exists and `GEMINI_FREE_TIER_CONFIRMED=true` confirms billing is disabled on that project. The pinned provider identifier is `gemini-3.8-flash`; [official pricing](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.8-flash) lists a free tier and [model capabilities](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash) include function calling. The earlier 2.5 pin was rejected for new accounts; the replacement is a reviewed static pin. Exact project limits must be recorded from AI Studio; published quotas are not a guarantee. No paid fallback or automatic model upgrade exists. Temporary provider failures have at most three attempts on the same model; exhausted quota is not retried. Application caps: 5 tools, 20 user turns/day, 100 app turns/day, one active request/user, 2,000 output tokens. Quotas use a separate writable SQLite file, not the immutable serving database. Live evaluation pauses on provider or quota failure and makes no accuracy claim until reviewed.

`Dockerfile` and `railway.toml` target one service and one worker; no training on startup. Deployment is gated on measured memory and verified remaining Hobby allowance. No deploy or spending change is automatic. See [release operations](docs/release.md).

## Attribution

Matches, rankings, players and Slam points: Jeff Sackmann / Tennis Abstract, preserved in the [archival mirror](https://github.com/Aneeshers/tennis-sackmann-archive). Shot/point charting: [Match Charting Project](https://github.com/JeffSackmann/tennis_MatchChartingProject) volunteers. Both retain **CC BY-NC-SA 4.0** and original upstream notices. [Valuebetennis](https://www.valuebetennis.com/en/donnees.htm), Tennis results and odds since 2021: **CC BY 4.0**. Open-Meteo estimates retain their provider attribution when acquired. No blanket license is assigned to third-party data.

Browser QA uses the full cached serving build and a fresh local Chromium-compatible browser profile. On this Mac it uses Brave. Run `npm --prefix frontend run test:browser`; set `BASELINE_BROWSER` to a compatible executable path on another machine. No live AI calls are made. A clean Docker context is generated by `uv run python scripts/export_deploy.py`; container deployment remains subject to the cost and runtime checks above.

## Measured local build

Current source cutoff: **2026-05-25** (both tours; tournament dates). The full build contains **359,120 canonical matches**, **17,925 eligible source-qualified replays**, and **3,062,694 before-point probabilities**. There are **10,203 linked charted matches** and **44 chronological model windows**. Venue verification is limited to **2 of 8,377 editions**; all remaining editions have explicit unavailable reasons.

Local verification: 49 offline tests, 16 dbt tasks, three browser checks, HTTP smoke, MetricFlow parity, readiness and rollback. These are implementation checks, not an analyst accuracy claim or a completed production release. See [the measured status and model results](docs/implementation-status.md).
