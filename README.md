# Baseline

A historical ATP/WTA singles analytics platform: explore players, compare historical matchups, inspect archived results, and replay eligible point records. Python/FastAPI serves a React application from one service. A browsing preview is deployed; the full first-release acceptance gates remain open.

**[Open Baseline](https://tennis-vision-production.up.railway.app)**. Public browsing needs no account. The analyst requires an approved GitHub login and an available free-tier provider; live analyst evaluation is currently paused on provider failures.

See the [accepted specification](tennis-analytics-project-plan.md) and [measured implementation status](docs/implementation-status.md). No computer vision, live scores, future schedules, doubles, lower-tour product, betting recommendations, paid data feeds or paid AI calls are included.

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

Current scope gaps are documented in the status file: broader enrichment verification, measured live analyst evaluation, actual GitHub browser consent and remaining release operations.

## Chat and deployment

Public browsing needs no credentials. Set configuration through local environment variables or Railway's secret interface; never commit keys. `.env.example` lists required names. `make dev` and `make agent-eval` load the saved local `.env` with priority over inherited shell values. Other configured commands can use `uv run --no-env-file python scripts/with_env.py baseline <command>`. GitHub OAuth uses `/api/v1/auth/callback` at `BASELINE_ORIGIN`, a server-side username allowlist, signed HTTP-only cookies and origin validation. A session secret of at least 32 characters is required.

Live chat requires `GEMINI_API_KEY` and `GEMINI_FREE_TIER_CONFIRMED=true` (billing disabled on that project). The manually pinned provider is `gemini-3.5-flash-lite`; [official model capabilities](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite) include function calling and [pricing](https://ai.google.dev/gemini-api/docs/pricing) lists free input/output. This replaces the 3.8 model that repeatedly timed out with this account. There is no paid fallback or automatic upgrade. Record project-specific quotas in AI Studio; published quotas are not a guarantee. Streaming has one retry for a 502/503/504 before any content, no midstream retries, a 15-second provider read timeout and a 45-second turn limit. Quota exhaustion is not retried. The browser stops waiting at 55 seconds and offers Stop and Retry controls. Application caps remain 5 tools, 20 user turns/day, 100 app turns/day, one active request/user, 2,000 output tokens per model response. Durable quota leases are released on disconnect or failure. Conversation context contains at most five completed user/assistant pairs and 16,000 characters, stays in browser memory, and is sent only on the next request; no chat transcript is persisted by this application. Google free-tier data handling remains subject to its terms. Live evaluation pauses on provider or quota failure and makes no accuracy claim until reviewed.

`Dockerfile` and `.railway/railway.ts` target one service and one worker; no training on startup. The service uses auto-sleep, 0.5 CPU, 512 MiB memory and a persistent quota volume. The owner approved a **$10 shared workspace compute hard limit** with a **$5 email alert**, retaining the existing Hobby tier. This permits usage above Hobby's included $5; reaching the shared cap can stop other projects. See [release operations](docs/release.md).

## Attribution

Matches, rankings, players and Slam points: Jeff Sackmann / Tennis Abstract, preserved in the [archival mirror](https://github.com/Aneeshers/tennis-sackmann-archive). Shot/point charting: [Match Charting Project](https://github.com/JeffSackmann/tennis_MatchChartingProject) volunteers. Both retain **CC BY-NC-SA 4.0** and original upstream notices. [Valuebetennis](https://www.valuebetennis.com/en/donnees.htm), Tennis results and odds since 2021: **CC BY 4.0**. Open-Meteo estimates retain their provider attribution when acquired. No blanket license is assigned to third-party data.

Browser QA uses the full cached serving build and a fresh local Chromium-compatible browser profile. On this Mac it uses Brave. Run `npm --prefix frontend run test:browser`; set `BASELINE_BROWSER` to a compatible executable path on another machine. No live AI calls are made. The Docker build downloads the serving snapshot pinned by URL and SHA-256 in `deployment/serving-release.json`. `uv run python scripts/prepare_release_asset.py` prepares a new deterministic archive; `uv run python scripts/export_deploy.py` creates a clean source context. Operating account reports and credentials are excluded from public assets. GitHub verifies the production container under a 512 MiB memory limit; Railway activation remains subject to its hosting allowance.

## Measured local build

Current source cutoff: **2026-05-25** (both tours; tournament dates). The full build contains **359,120 canonical matches**, **17,925 eligible source-qualified replays**, and **3,062,694 before-point probabilities**. There are **10,203 linked charted matches** and **44 chronological model windows**. Venue verification is limited to **2 of 8,377 editions**; all remaining editions have explicit unavailable reasons.

Local verification: 49 offline tests, 16 dbt tasks, three browser checks, HTTP smoke, MetricFlow parity, readiness and rollback. These are implementation checks, not an analyst accuracy claim or a completed production release. See [the measured status and model results](docs/implementation-status.md).

Chat uses `POST /api/v1/analyst/stream`: SSE `status`, `delta`, `reset`, `done` (the analytical envelope), and `error` events. Numerical tools accept validated objects generated from the same governed query schemas as the API. The assistant supports tennis conversation and follow-ups, clarifies ambiguous identities, and redirects unrelated questions back to tennis. The animated green Baseline mark shows activity; text appears as received from the provider. Reduced-motion preferences disable the flip and caret animations. All dropdown menus use themed Radix Select controls with keyboard navigation. See [chat implementation and verification](docs/chat-interaction.md).
