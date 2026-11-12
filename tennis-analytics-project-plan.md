# Baseline: Tennis Analytics Engineering Platform

> **Data acquisition update — November 11, 2026:** The original Sackmann ATP,
> WTA, and Slam point-by-point repositories currently return 404. Use the
> [archival mirror](https://github.com/Aneeshers/tennis-sackmann-archive), which
> reports ATP/WTA snapshots from June 2026 and Slam coverage through 2024.
> Match Charting remains accessible. The original odds provider returns 403
> through the web tool and its indexed homepage restricts automated/AI use.
> [Valuebetennis](https://www.valuebetennis.com/en/donnees.htm) provides a CC BY 4.0
> alternative from 2021 onward with a different schema; odds models, joins, and
> benchmark periods below must be adjusted accordingly. Use
> [the acquisition guide](docs/data-setup.md) and [source catalog](data/sources.json)
> for current download instructions. Source freshness and full current-season
> coverage have not been established.

**Working title:** Baseline (rename anything you like)
**One-line pitch:** A dbt-powered tennis analytics warehouse with governed metrics, an AI analyst on top of those metrics, a rigorously validated win-probability model, and a scouting app. A computer-vision "SwingVision-style" phase feeds the same warehouse afterward.
**Target roles:** Analytics Engineer (primary), Data Scientist, Forward Deployed Engineer (the agent and the CV phase)
**Planned timeline:** about 5 weeks for the core at 10-15 hrs/week, then SwingVision as Phase 8.

---

## 0. How the pieces fit together

```
 RAW SOURCES                      WAREHOUSE (DuckDB + dbt)                         CONSUMERS
 ───────────                      ────────────────────────                         ─────────
 Sackmann ATP/WTA matches ─┐
 Sackmann rankings/players ─┤      staging ──► intermediate ──► marts ──┬──► (1) Semantic layer (MetricFlow)
 Match Charting Project ────┼──►   (clean,     (point-in-time    (facts,  │         └──► AI analyst agent (LangGraph)
 Slam point-by-point ───────┤       typed)      features, Elo,    dims,   ├──► (2) Win-probability models
 tennis-data.co.uk odds ────┘                   joins)            wide)   │         (pre-match + live in-match)
                                                                          └──► (3) Scouting app (Streamlit)
 [Phase 8] Your own match video ──► CV pipeline ──► raw_video_events ──► same staging/marts ──► same consumers
```

**Design principle:** every consumer reads from the marts and the semantic layer. Nothing reads raw tables. This is what makes the project read as analytics engineering rather than a collection of notebooks.

**Licensing note:** Jeff Sackmann's datasets are CC BY-NC-SA 4.0 (attribution required, non-commercial only, share-alike). A free portfolio project is fine. Put an attribution block in the README and the app footer, and don't monetize.

---

## 1. Data sources (everything you need, in one place)

### 1.1 Core match results and stats: Jeff Sackmann `tennis_atp` / `tennis_wta`
- **URL:** https://github.com/JeffSackmann/tennis_atp (men) and https://github.com/JeffSackmann/tennis_wta (women)
- **What's in it (confirmed from the repo README):**
  - Tour-level main-draw matches in `atp_matches_YYYY.csv`, with a data dictionary in `matches_data_dictionary.txt`.
  - Match stats (aces, serve points, break points, etc.) from 1991 onward for tour-level; Challenger stats from 2008; qualifying stats from 2011.
  - Player file: `player_id, first_name, last_name, hand, birth_date, country_code, height`.
  - Ranking files: `ranking_date, ranking, player_id, ranking_points`. Mostly complete 1985 to present.
- **Key match columns to model** (verify against the data dictionary): `tourney_id, tourney_name, surface, draw_size, tourney_level, tourney_date, match_num, winner_id, loser_id, winner_rank, loser_rank, winner_age, loser_age, winner_ht, loser_ht, score, best_of, round, minutes`, plus per-player serve stats prefixed `w_` and `l_` (`ace, df, svpt, 1stIn, 1stWon, 2ndWon, SvGms, bpSaved, bpFaced`).
- **Scope recommendation:** start with ATP tour-level singles, 2000-present. Add WTA after the ATP pipeline works (it's a nice test of reusable macros).
- **Gotchas:** the repo mixes file types (main tour, qualifying/challenger, futures) with different naming. Check the repo file listing for exact names before writing your ingestion script. `tourney_date` is the tournament start date, not the match date, so within-tournament ordering needs `round` and `match_num`.

### 1.2 Shot-level and point-level data: Match Charting Project (your "SwingVision-style" data)
- **URL:** https://github.com/JeffSackmann/tennis_MatchChartingProject
- **What's in it (confirmed):** 40 CSV files, 20 men's (`m`) and 20 women's (`w`):
  - `charting-[m|w]-matches.csv`: match metadata (players, tournament, date, surface)
  - `charting-[m|w]-points-to-2009.csv`, `-points-2010s.csv`, `-points-2020s.csv`: point-by-point data
  - 16 aggregate stat files per gender, `charting-[m|w]-stats-[Name].csv`, with names such as `ServeDirection`, `ReturnOutcomes`, `Rally`, `ShotDirection`, `ShotTypes`, `NetPoints`, `KeyPointsServe`, `KeyPointsReturn`, `SnV`, `SvBreakSplit`
- **Key challenge (this is the interesting part):** the `1st` and `2nd` columns contain a compact shot-string code (serve direction, shot types, directions, outcomes). You'll write a parser (Python or DuckDB regex/UDF) to explode each point into one row per shot. Coding instructions are linked from the repo README and the Match Charting Project site (https://www.tennisabstract.com/charting/). Treat the README as your source of truth for the syntax.
- **Caveat:** charted matches are a biased sample (volunteers chart famous matches). Use charting for style and tendency analysis, and use the full Sackmann match data for the win-probability model.
- **Use for:** serve direction, rally length, shot-type profiles, and the shot-event schema your computer-vision phase will later emulate.

### 1.3 Grand Slam point-by-point: `tennis_slam_pointbypoint`
- **URL:** https://github.com/JeffSackmann/tennis_slam_pointbypoint
- **What's in it (confirmed):** per tournament, `*-matches.csv` and `*-points.csv`. Covers most main-draw singles matches at the four Slams from 2011 onward. Fields include serve speed, 1st/2nd serve indicators, rally length, distance run, serve and return depth, and ace/double fault/winner/unforced error flags.
- **Gotchas:** columns vary by event and year; some 2018-19 AO/FO matches record serve speed as 0 and rally length as 0 or 3. Check the CSV headers per file and build a column-harmonization macro in staging. Treat the zeros as nulls with a flag.
- **Use for:** the live in-match win-probability model (point-level serve and return win rates) and serve-speed analysis.

### 1.4 Betting odds (benchmark only): tennis-data.co.uk
- **URL:** http://www.tennis-data.co.uk/alldata.php (notes on fields: http://www.tennis-data.co.uk/notes.txt)
- **What's in it (confirmed via secondary sources; I couldn't load the site directly while writing this, so check the page yourself):** ATP results back to 2000 with betting odds, WTA from 2007, in CSV/Excel. Odds columns include Bet365 (`B365W`, `B365L`), Pinnacle (`PSW`, `PSL`), and averages (`AvgW`, `AvgL`), updated after each tournament.
- **Gotchas:** player names are in a "Last F." format with no player ID, so you'll build a **player name bridge** (seed table plus fuzzy matching, with a manual-override CSV) to join to Sackmann IDs. This is realistic AE work: treat the match-rate as a metric and test it.
- **Use for:** evaluating your model against the market (convert odds to de-vigged implied probabilities). Do **not** use odds as a model input. The benchmark is more honest if the market is a competitor, not a feature.
- **Note:** respect the site's terms; download the yearly files manually or with a polite script, and cache them in `data/raw/`.

### 1.5 Optional enrichment
- **Elo sanity check:** Tennis Abstract publishes Elo ratings (https://www.tennisabstract.com). Compare your computed Elo against theirs for the top players as a validation step. Don't scrape; just eyeball a few players.
- **Weather and altitude by tournament** (optional): Open-Meteo historical API (https://open-meteo.com), free, no key. Needs a small tournament-to-location seed table you create by hand.

### 1.6 Phase 8 (SwingVision-style) data and models
| Need | Resource |
|---|---|
| Ball tracking research and dataset | TrackNet paper (https://arxiv.org/abs/1907.03698); dataset link is in the paper. TrackNetV4 and V5 papers: https://arxiv.org/abs/2409.14543 and https://arxiv.org/abs/2512.02789 |
| Court keypoint detection (14 keypoints, 8,841 images) | https://github.com/yastrebksv/TennisCourtDetector; HuggingFace mirror: https://huggingface.co/datasets/oweng/tennis_court_keypoints_dataset |
| Reference end-to-end project (YOLOv8 + court keypoints) | https://github.com/abdullahtarek/tennis_analysis |
| Ball + racket pose benchmark | RacketVision: https://arxiv.org/abs/2511.17045 |
| Tennis stroke action dataset | THETIS (Kinect, 8,374 sequences). Search "THETIS tennis dataset" for the current host |
| Extra labeled images | Roboflow Universe, search "tennis court detection" and "tennis ball detection" (check each dataset's license; some are CC BY 4.0) |
| Detection / pose models | Ultralytics YOLO (https://github.com/ultralytics/ultralytics), MediaPipe Pose, or RTMPose |
| **Your own footage** | Record with a phone on a tripod behind the baseline. This is the best data. |

**Video licensing warning:** don't download broadcast footage from YouTube for a public project. It raises ToS and copyright issues. Use your own recordings and the research datasets above.

---

## 2. Tech stack and repo structure

**Stack**
- Warehouse: **DuckDB** (free, local, fast, ships as a single file). Add **BigQuery** as a second dbt target later to show portability. Your resume already mentions BigQuery.
- Transformation: **dbt Core** with the `dbt-duckdb` adapter. dbt Python models are supported by `dbt-duckdb`, which is useful for Elo. If you hit problems, run Elo as a Python step before dbt and load the result as a source.
- Semantic layer: **MetricFlow** (open source, Apache 2.0 since v0.209.0, Oct 2025). Install with `pip install dbt-metricflow` and query with the local `mf` CLI. **Important:** the hosted Semantic Layer APIs and the dbt MCP `query_metrics` tool need a paid dbt platform plan. For a free project, your agent should call the local `mf` CLI, or you can wrap it in a small MCP server of your own.
- Orchestration: Makefile or `just` for local, GitHub Actions for CI. Dagster is optional if you want an orchestrator on your resume.
- Modeling: Python, scikit-learn, XGBoost/LightGBM, `statsmodels` for calibration.
- Agent: **LangGraph** (you already use it at NTT), Claude via API.
- App: **Streamlit** (Community Cloud is free), or Evidence.dev if you want a different look.
- Docs: `dbt docs generate`, hosted as a static site (Cloudflare Pages, where your portfolio already lives, or GitHub Pages).

**Repo layout**
```
baseline/
├── README.md                    # architecture diagram, how to run, attribution
├── Makefile
├── data/raw/                    # downloaded CSVs (gitignored; script re-creates)
├── ingest/                      # download + load scripts, shot-string parser
├── dbt/
│   ├── dbt_project.yml
│   ├── models/
│   │   ├── staging/             # stg_atp_matches, stg_players, stg_rankings, stg_charting_*, stg_slam_points, stg_odds
│   │   ├── intermediate/        # int_player_match_long, int_elo_history, int_rolling_form, int_shot_events, int_player_bridge
│   │   ├── marts/
│   │   │   ├── core/            # dim_player, dim_tournament, dim_date, fct_match, fct_player_match
│   │   │   ├── charting/        # fct_point, fct_shot, mart_serve_profile, mart_rally_profile
│   │   │   └── ml/              # mart_match_features (one row per match, point-in-time safe)
│   │   └── semantic/            # semantic_models.yml, metrics.yml, saved_queries.yml
│   ├── seeds/                   # tournament_locations.csv, player_name_overrides.csv
│   ├── snapshots/               # snap_player_profile (SCD2)
│   ├── macros/
│   └── tests/                   # singular tests, unit tests
├── ml/                          # training, evaluation, calibration notebooks + scripts
├── agent/                       # LangGraph analyst, eval set, eval runner
├── app/                         # Streamlit scouting app
├── vision/                      # Phase 8
└── .github/workflows/           # CI: dbt build on sample data, lint, docs deploy
```

---

## 3. Phase plan

> Each phase has a **Definition of Done** (DoD). Don't move on until it's met. Every phase should end with a commit and a short note in `docs/devlog.md` (feeds your write-up).

### Phase 0: Setup (Days 1-2)
- Create the repo, Python env, `dbt-duckdb`, `dbt-metricflow`, pre-commit (sqlfluff, ruff).
- Write `ingest/download.py` that pulls the Sackmann repos (git clone or raw GitHub URLs) and the tennis-data.co.uk yearly files into `data/raw/`, recording file hash and download date.
- Write the README skeleton with the architecture diagram and the attribution block.
- **DoD:** `make ingest` produces raw files; `dbt debug` passes.

### Phase 1: Sources and staging (Days 3-6)
- Load raw CSVs into a `raw` schema in DuckDB (use `read_csv_auto` with explicit types where needed).
- Declare dbt **sources** with `loaded_at_field` and **freshness** checks.
- Build staging models, one per source: rename to snake_case, cast types, parse dates (`tourney_date` as `YYYYMMDD`), standardize surface and round codes, and add `_loaded_at`.
- Build `stg_slam_points` with the column-harmonization macro and the zero-to-null serve-speed fix.
- **Tests:** `unique` and `not_null` on keys, `accepted_values` for surface, round and best_of, relationship tests (match -> player).
- **DoD:** `dbt build --select staging` is green; the row counts match the raw files (write a singular test that proves it).

### Phase 2: Player bridge, intermediate layer, and marts (Days 7-13)
1. **`int_player_bridge`**: map odds-file names ("Federer R.") to Sackmann `player_id`. Use a deterministic rule first (last name plus first initial plus year-of-activity), then `player_name_overrides.csv` for exceptions. Report the match rate and fail the build if it drops below a threshold you set.
2. **`int_player_match_long`**: unpivot winner/loser into one row per player per match (the foundation for every rolling feature).
3. **`int_elo_history`**: overall Elo and surface-specific Elo, with the K-factor decaying by matches played. Elo is sequential, so implement it as a dbt Python model or a pre-dbt Python step. Sanity-check the top 10 against Tennis Abstract.
4. **`int_rolling_form`**: point-in-time rolling features. Use window frames that **exclude the current match** (`rows between N preceding and 1 preceding`) over a stable ordering of (`tourney_date`, `round_order`, `match_num`). Features: last-10 and last-52-week win %, surface win %, 1st-serve-in %, 1st/2nd-serve points won %, return points won %, break-point conversion, aces per service game, days since last match, matches in last 14 days.
5. **`int_shot_events`**: explode the Match Charting shot strings into one row per shot (this feeds `fct_shot`).
6. **Marts:** `dim_player`, `dim_tournament`, `dim_date`, `fct_match`, `fct_player_match`, `fct_point`, `fct_shot`, `mart_serve_profile`, `mart_rally_profile`, and `mart_match_features` (one row per match, label = player A won, with randomized A/B assignment so the label isn't always 1).
7. **Snapshot:** `snap_player_profile` (SCD Type 2) tracking hand, height, and ranking-band changes.
8. **Incremental models:** make `fct_player_match` and `int_rolling_form` incremental by season, with a documented full-refresh path.
- **Tests (target 40+ total):** generic, `dbt_utils`/`dbt_expectations` (recency, ranges, row-count equality), singular tests (no match has a feature computed from future data: see the leakage test below), and dbt **unit tests** for the Elo update and the shot-string parser using small hand-built fixtures.
- **The leakage test (important):** a singular test that recomputes one rolling feature in a deliberately naive way for a sample of matches and asserts equality, plus a test that no feature row references a match date later than the label match.
- **DoD:** `dbt build` is green end to end; `dbt docs generate` produces lineage you're proud of; a model-by-model description is in the YAML.

### Phase 3: CI, docs, and the semantic layer (Days 14-17)
- **CI (GitHub Actions):** on every PR, run `sqlfluff lint`, then `dbt build` against a **small committed sample dataset** (e.g. 2 seasons) so CI finishes in minutes. Publish `dbt docs` on merge to main.
- **Semantic models** (YAML): `fct_player_match` (entity: player; dimensions: surface, tournament level, round, opponent hand, year), `fct_point` (serve/return), `fct_shot` (shot type, direction).
- **Metrics** (define each once, in `metrics.yml`): `win_rate`, `first_serve_in_pct`, `first_serve_points_won_pct`, `second_serve_points_won_pct`, `return_points_won_pct`, `break_point_conversion_pct`, `ace_rate`, `double_fault_rate`, `avg_rally_length`, `serve_direction_share` (wide/body/T), `elo_rating`. Use ratio and derived metric types where appropriate.
- **Saved queries** for common questions (surface splits, last-52-week form).
- **Validate:** `mf validate-configs`, then spot-check three metrics against hand-written SQL (put these checks in tests).
- **DoD:** `mf query --metrics win_rate --group-by player__name,surface` returns correct numbers; CI is green on a PR; docs site is live.

### Phase 4: Win-probability models (Days 18-24)
**4a. Pre-match model**
- Data: `mart_match_features`, 2005-present (use earlier years only to warm up Elo/rolling features).
- Features: Elo difference (overall and surface), rank and rank-points difference, rolling form differences, serve/return differentials, height, age, handedness matchup, rest days, best-of-3 vs best-of-5, tournament level.
- **Validation (this is what separates it from a toy):** walk-forward by season, for example train through 2018, validate 2019, test 2020 onward, then roll forward. Never shuffle.
- **Baselines to beat:** (1) higher-ranked player wins, (2) pure Elo probability, (3) logistic regression on Elo diff. Then try XGBoost/LightGBM.
- **Metrics:** log loss, Brier score, accuracy, and a **calibration curve with reliability diagram** (calibrate with isotonic or Platt, fit only on validation data).
- **Market benchmark:** de-vig the odds (e.g. proportional method) from `tennis-data.co.uk` and compare log loss. Expect the market to be hard to beat. Report the gap honestly. "Within X of the closing line, using only public data" is a strong, defensible claim; "beats Vegas" is not.
- **Explainability:** SHAP summary plot, and a few case studies of confident misses.
- Track runs with MLflow (local) or a simple results CSV.

**4b. Live in-match model**
- Use a hierarchical Markov model: estimate each player's probability of winning a point on serve, then compute game, set and match win probabilities by recursion. Update point by point as the score changes.
- Estimate serve-point probabilities from `mart_match_features` rolling serve/return rates (pre-match prior) and blend in-match observations (Bayesian shrinkage).
- Backtest on Slam point-by-point data (`tennis_slam_pointbypoint`): at each point, compare the live probability to the eventual outcome and report calibration across score states.
- Output: a win-probability-over-time chart per match, which becomes a showpiece in the app.
- **DoD:** a notebook plus a script that write predictions back into the warehouse as `fct_match_prediction` and `fct_live_win_prob` (so the app and agent can read them through dbt too); a results table with baselines, model and market; calibration plots saved in `docs/`.

### Phase 5: AI analyst agent on the semantic layer (Days 25-30)
- **Architecture:** LangGraph agent with tools:
  - `list_metrics`, `get_dimensions`, `query_metrics` (each wrapping the local `mf` CLI or Python API and returning a small dataframe)
  - `lookup_player` (resolves "Carlos Alcaraz" or "Sinner" to `player_id` using `dim_player`)
  - `explain_metric` (returns the metric's definition from `metrics.yml`)
  - optional `get_win_probability` (reads `fct_match_prediction`)
- **Guardrails:** no raw SQL tool in the main agent. All numbers come from governed metrics. The agent must state which metric, filters and time range it used.
- **Baseline for comparison:** build a second agent that does text-to-SQL directly against the marts. This is the key experiment.
- **Evaluation set:** write 40-60 questions with gold answers computed by hand-written SQL, split into easy (single metric), medium (grouping and filters), and hard (comparisons, multi-metric, ambiguous names). Score exact/numeric-tolerance correctness, and also track refusal/clarification behavior and latency.
- **Report:** semantic-layer agent vs raw text-to-SQL, with accuracy by difficulty. dbt Labs published its own replication result on this topic (https://www.getdbt.com/blog/open-source-metricflow-governed-metrics); yours is a small-scale version on tennis data. Report your own numbers, whatever they are.
- **Optional:** expose the tools as an MCP server so Claude Desktop can query the tennis metrics. This is a strong FDE-style demo.
- **DoD:** `python -m agent.eval` runs the full eval set and prints a results table; 3-4 example conversations saved in `docs/`.

### Phase 6: Scouting app (Days 31-35)
- **Streamlit pages:**
  1. **Player profile:** serve/return metrics, surface splits, Elo history chart.
  2. **Matchup:** pick two players and surface, then show pre-match win probability (with calibration note), head-to-head, style comparison (serve direction heat map, rally length distribution), and "what to watch" bullets generated from metric gaps.
  3. **Match replay:** pick a charted or Slam match and show the live win-probability chart with key points highlighted.
  4. **Ask the analyst:** embeds the Phase 5 agent.
- **Data access:** the app reads a small prebuilt `app.duckdb` containing only the marts it needs (keeps deploy light and fast). A `make app-data` target builds it from the dbt output.
- **Hosting:** Streamlit Community Cloud (free), or Railway as in your previous projects. Add attribution in the footer.
- **DoD:** public URL; loads in a few seconds; every number on screen traces to a mart or metric.

### Phase 7: Packaging and portfolio (Days 36-38)
- README: problem, architecture diagram, results (model vs baselines vs market; agent eval), how to run, attribution, limitations.
- Hosted dbt docs link and a short Loom/GIF demo of the app and agent.
- Add the project to your portfolio site (Cloudflare Pages) as the lead dbt/AE project, with a "what I'd do next" section.
- **Resume bullets (fill in your real numbers; don't publish placeholders):**
  - "Built a dbt (DuckDB/BigQuery) tennis analytics warehouse over [N]M matches/points with [N] models, [N] tests and CI; point-in-time feature layer verified leak-free."
  - "Defined [N] governed metrics in MetricFlow; built a LangGraph analyst agent reaching [X]% accuracy on a [N]-question eval vs [Y]% for raw text-to-SQL."
  - "Trained a calibrated win-probability model (log loss [X] vs Elo baseline [Y], within [Z] of the market closing line) plus a live Markov in-match model backtested on [N] Slam points."
- **DoD:** a stranger can clone the repo, run `make all`, and reproduce the headline results.

### Phase 8: SwingVision-style video phase (after the core ships; about 3-6 weeks, optional scope)
**Goal:** turn phone video of a rally into the same shot-event schema as the Match Charting data, load it as a new source, and have the existing marts, metrics, agent and app work on your own footage.

**Scope the first version tightly:** fixed phone camera behind the baseline, hard court, singles, one clear rally per clip, 10-20 clips. Do not promise Hawk-Eye accuracy.

**Pipeline**
1. **Capture:** record your own sessions at 1080p/60fps from a tripod behind the baseline, at about 3-4 m height if possible. Keep the full court in frame.
2. **Court detection:** use the 14-keypoint model from TennisCourtDetector, then compute a **homography** to map pixels to real court coordinates (the court's dimensions are known). Re-estimate periodically in case the camera shifts.
3. **Player detection and pose:** YOLO for player boxes, then MediaPipe or RTMPose for keypoints. Use court-space foot position for movement/coverage metrics.
4. **Ball tracking:** start with a pretrained TrackNet-family model; fine-tune on frames from your own footage if recall is poor. Ball tracking is the hardest component, so budget the most time here.
5. **Event detection:** detect **bounces** from vertical trajectory inflections, **hits** from direction changes with the nearest player in proximity, then **in/out** by mapping the bounce point into court coordinates.
6. **Shot classification:** forehand/backhand/serve/volley from pose sequences (train a small classifier on your own labeled clips; THETIS can help bootstrap).
7. **Metrics:** shot speed (estimate from court-space displacement over time; note the uncertainty), rally length, bounce depth and direction, player court coverage.
8. **Output:** write `raw_video_events` (clip_id, frame, timestamp, event_type, player, court_x, court_y, shot_type, speed_est, confidence). Add `stg_video_events` and `fct_video_shot` in dbt, conformed to `fct_shot`.

**Validation (non-negotiable; this is what makes it credible)**
- Hand-label 3-5 rallies (bounce frames, hits, in/out).
- Report bounce-detection precision/recall/F1, in/out accuracy, and ball-detection recall. Report error bars on speed estimates.
- Show failure cases honestly in the README.

**DoD:** one command takes a video file to rows in the warehouse; the app's "Match replay" page works on your own clip; a validation table is in the README.

---

## 4. Risks and how to handle them

| Risk | Mitigation |
|---|---|
| Scope creep: five consumers is a lot | Phases are independent. If time runs out, ship Phases 0-3 plus 4a. That alone is a strong AE project. |
| Data leakage in features | Windowed features exclude the current match; leakage test in CI; walk-forward validation only. |
| Name matching between odds and Sackmann data | Deterministic rules plus an overrides seed; match rate is a tested metric. |
| Elo in SQL is awkward | Python model or pre-dbt step; unit-test the update function. |
| Charting data is a biased sample | State it in the README; use full match data for the win-probability model. |
| Hosted Semantic Layer / MCP needs a paid dbt plan | Use local `mf` CLI and your own tool wrappers. |
| CV accuracy disappoints | Keep scope narrow, report metrics honestly, and treat the CV phase as an extension. |
| Licensing | Attribution everywhere; no monetization; don't redistribute broadcast video. |

---

## 5. Suggested weekly schedule (assumes ~10-15 hrs/week)

| Week | Focus | Ship |
|---|---|---|
| 1 | Phases 0-1, start Phase 2 | Staging green, sources and freshness, first tests |
| 2 | Phase 2 | Marts, Elo, rolling features, leakage test, docs |
| 3 | Phase 3 + 4a | CI, semantic layer, pre-match model with baselines |
| 4 | Phase 4b + 5 | Live win probability, agent plus eval |
| 5 | Phases 6-7 | App deployed, README, portfolio page, resume bullets |
| 6+ | Phase 8 | Video pipeline v1 |

---

## 6. Checklist: what to look up before each phase
- **Phase 1:** Sackmann `matches_data_dictionary.txt`; `dbt-duckdb` docs for sources and external files.
- **Phase 2:** window-function frames in DuckDB; dbt unit tests; `dbt_utils` and `dbt_expectations` packages; Match Charting coding instructions for the shot-string syntax.
- **Phase 3:** MetricFlow docs (https://docs.getdbt.com/docs/build/metricflow-commands) for semantic model and metric YAML, plus `mf` CLI usage.
- **Phase 4:** literature on hierarchical Markov models of tennis scoring (Klaassen and Magnus; Newton and Keller; O'Malley) for the live model recursion.
- **Phase 5:** LangGraph docs for tool-calling agents; MCP SDK if you build the MCP server.
- **Phase 8:** TrackNet papers, TennisCourtDetector README (training and inference), OpenCV `findHomography`.

---

## 7. Sources and attribution
- Jeff Sackmann / Tennis Abstract: `tennis_atp`, `tennis_wta`, `tennis_slam_pointbypoint`, `tennis_MatchChartingProject` (CC BY-NC-SA 4.0). Match Charting Project data is contributed by volunteer charters.
- tennis-data.co.uk: historical results and odds.
- dbt Labs: dbt Core, MetricFlow (Apache 2.0).
- TrackNet (Huang et al.) and successors; TennisCourtDetector (yastrebksv); RacketVision benchmark; THETIS dataset.
