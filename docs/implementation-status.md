# Baseline implementation status

This is a tested local implementation candidate. The first public release is **not accepted or deployed**. Live analyst quality has not passed release evaluation, and most venue enrichment is explicitly unavailable pending verification.

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

1. GitHub OAuth credentials, the owner allowlist and a generated session secret are configured in a private, Git-ignored local file. Saved values take priority over inherited shell settings. Redirect, signed state and anonymous-access rejection checks passed. Actual GitHub browser consent is still pending; production secrets remain to be installed at the host.
2. The user confirmed free-tier AI Studio setup and supplied the project key. The current manually pinned provider is `gemini-3.8-flash`; its free text tier and tool support were checked in official documentation. The earlier 2.5 model returned 404 for new users. Live evaluation status: `provider_unavailable`, 0/60 completed cases. The provider returned HTTP 503; bounded retries stay on the pinned model and save a resumable checkpoint. Results require review; no aggregate analyst accuracy claim is made. Project-specific active quotas remain to be recorded. Independent billing inspection remains unavailable; local enablement relies on the user's confirmation. Evidence: `artifacts/provider-compatibility.json`, `artifacts/local-configuration-verification.json`, and `artifacts/agent-evaluation.json`.
3. Venue/weather accounting is complete, but verification is mostly unavailable, not complete enrichment. Expand reviewed historical venue/elevation assignments and relocation/timezone/gap fixtures. Do not interpret an unavailable status as a guessed city or zero weather.
4. Railway target `wonderful-truth / tennis-vision` is linked locally. Reserved origin: `https://tennis-vision-production.up.railway.app`. Nine runtime variables were staged with deployment triggering disabled, including a separate production session secret. No application deployment, volume or spending-limit change was made by this setup. The current failed deployment uses the acquisition-only GitHub commit; application code and the serving artifact remain local. Verify allowance, durable quota storage cost, artifact delivery and container runtime before deploying. Evidence: `artifacts/railway-setup.json`; instructions: `docs/railway-setup.md`.
5. Docker is not installed in this environment, so the clean materialized context at `artifacts/deploy/` is prepared but its container build is untested. The local one-service application and browser build are tested. A public release still requires container/runtime and approved-user/provider-failure checks at the actual host.

Do not label M7 or M8 complete until their measured acceptance gates pass. Working local slices of M0–M6 are implemented; source coverage and the explicit limitations above remain part of the product contract.
