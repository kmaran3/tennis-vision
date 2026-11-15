# Baseline implementation status

A historical browsing preview is deployed at https://tennis-vision-production.up.railway.app. The full first-release acceptance gates remain open: live analyst quality has not passed evaluation and most venue enrichment remains explicitly unavailable.

## Measured snapshot

Source snapshot: `a7eb168cddb5655943bbb3f91ee6d965ab7cec5d3db3a1f1a6352f14e3430c95`. Original archive/charting locks and raw files were preserved. Cutoffs are maximum observed tournament-start dates, not verified last match timestamps.

- ATP: **2026-05-25**; latest 2026 season incomplete.
- WTA: **2026-05-25**; latest 2026 season incomplete.

- 359,120 canonical main-tour match records, including earlier rating warm-up history.
- 698,866 completed player-match rows; 349,433 paired feature records, plus two player-side records per feature cutoff.
- 5,573,852 ranking observations; identifiers remain tour qualified.
- 10,203 uniquely linked charted matches; 1,581,808 parsed charted points and 7,456,878 coded shot attempts.
- 17,925 eligible source-qualified replays; 3,062,694 before-point probability observations.
- 4,508 uniquely matched odds records. Market evaluation uses a smaller, explicitly common eligible subset with both opening and closing prices.
- 8,377 tournament editions accounted for: 2 verified venue assignments, 8,375 unavailable. 15 unique venue/local-date weather summaries. Both verified assignments are 2024 Roland-Garros; they share one venue weather cache. No independently verified altitude is currently supplied.

Replay source/tour slices:

| Source | Tour | Eligible matches |
|---|---|---:|
| charting | ATP | 6,383 |
| charting | WTA | 3,543 |
| slam | ATP | 4,019 |
| slam | WTA | 3,980 |

Unknown notation/rules, missing points, duplicate records, ambiguous joins, and unfinished matches have versioned exclusion reports under `artifacts/`. Source-qualified Slam and MCP replays of the same match are separate observations, not extra canonical matches.

## Measured model results

44 expanding chronological tour/year windows, 2005–2026 where sufficient history exists. Candidate preprocessing is fit only to the training partition. Mirrored rows remain within the same partition. Model IDs include the raw snapshot and training recipe hash.

2024 out-of-sample results (all model-eligible matches):

| Tour | Matches | Log loss | Brier | Accuracy | Selected candidate |
|---|---:|---:|---:|---:|---|
| ATP | 2,464 | 0.6142 | 0.2142 | 64.5% | logistic |
| WTA | 2,276 | 0.6151 | 0.2144 | 65.1% | logistic |

2024 common market subset, log loss (these are **not** the same populations as the table above):

| Tour | Common matches | Model | Opening market | Closing market |
|---|---:|---:|---:|---:|
| ATP | 229 | 0.5062 | 0.4850 | 0.4815 |
| WTA | 288 | 0.5736 | 0.5512 | 0.5458 |

The full reports include tour/year/surface/level slices, calibration bins and 100 tournament-group bootstrap replicates. Closing prices are the provider's last recorded pre-match odds, not independently timestamp-verified exchange prices. Probability calibration is measured; no calibrated uncertainty interval is claimed. Evaluation year uses the proxy feature-cutoff calendar year; an event edition ID can carry the following year for events starting in late December.

Features include overall/surface Elo, strictly earlier rankings, serve/return form, results, age/height/handedness, experience and format/event-context interactions. No realized weather, odds, final score, duration or current-match statistics enter prediction inputs. Tournament-only results have a conservative 28-day inferred availability lag. Model eligibility excludes known date contradictions from joined evidence. These safeguards do not establish an unconditional leak-free claim.

## Verification actually run

- Locked Python compatibility: dbt Core 1.11.17, dbt-duckdb 1.11.1, dbt-metricflow 0.12.0, MetricFlow 0.210.0, DuckDB 1.5.6.
- 49 offline tests passed, including the original acquisition tests, weighted/null metric behavior, future-data perturbation, strict as-of Elo, scoring rules, auth/origin failures, quota persistence and tool allowlists.
- 16 dbt model/test tasks passed on the full snapshot; final warehouse validation checks keys, relationships, tour separation, player-side feature grain and maximum contributing times.
- Actual MetricFlow semantic validation and first-serve-points-won parity against independent SQL passed for both tours.
- Three local Playwright browser checks passed using a fresh Brave profile: both tours, profiles, historical matchup, point stepping/keyboard controls, anonymous examples, mobile overflow/empty state and shareable filters. Screenshots are in `artifacts/`.
- HTTP serving smoke passed, including both tours, replay, historical scenarios, player-side symmetry, optional verified venue, and a 2026 WTA model window. Measured process maximum RSS: 362.4 MiB; serving database: 315.3 MiB. This is a local test-process peak, not a Railway billing forecast.
- Immutable artifact checksums/readiness and actual local rollback/restoration passed. Migration restored 16 older WTA records whose source match numbers repeat across rounds; keys now include round and unordered source player pair. Replay input equivalence was checked before retaining existing curves.

## Remaining release gates

1. Production GitHub OAuth redirect, signed state, secure HTTP-only cookie, rejected invalid states/origins, anonymous access and unapproved-user rejection passed. Approved-session checks used operator-signed test fixtures; actual GitHub browser consent still needs the owner to sign in.
2. The user confirmed free-tier AI Studio setup and supplied the project key. The current manually pinned provider is `gemini-3.8-flash`; its free text tier and tool support were checked in official documentation. The earlier 2.5 model returned 404 for new users. Live evaluation status: `provider_unavailable`, 0/60 completed cases. The evaluation saves completed stages and pauses on quota or provider failures. Results require review; no aggregate analyst accuracy claim is made. Project-specific active quotas remain to be recorded. Independent billing inspection remains unavailable; local enablement relies on the user's confirmation. Evidence: `artifacts/provider-compatibility.json`, `artifacts/local-configuration-verification.json`, and `artifacts/agent-evaluation.json`.
3. Venue/weather accounting is complete, but verification is mostly unavailable, not complete enrichment. Expand reviewed historical venue/elevation assignments and relocation/timezone/gap fixtures. Do not interpret an unavailable status as a guessed city or zero weather.
4. The user approved a $10 shared workspace compute hard limit and a $5 email alert on the existing Hobby tier. Both limits were set and read back. One application service is deployed with auto-sleep, 0.5 CPU, 512 MiB memory and durable quota storage. The $10 cap can allow charges above the plan's included $5 and can stop other workspace projects. No plan upgrade was made.
5. Public-host verification passed 24 API requests across both tours, metrics, replay and matchup symmetry, in addition to the production-container CI checks. Running-container cgroups confirmed the intended limits; a storage marker survived a new deployment. Legacy railway.toml was replaced by a reviewed service-scoped .railway/railway.ts plan, with secrets unmanaged and the existing volume retained. Actual host evidence is in artifacts/railway-production-verification.json and artifacts/production-resources-storage.json. Browser consent and live analyst evaluation remain outstanding.

Do not label M7 or M8 complete until their measured acceptance gates pass. Working local slices of M0–M6 are implemented; source coverage and the explicit limitations above remain part of the product contract.
