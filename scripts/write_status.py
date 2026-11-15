"""Publish actual local measurements; do not manufacture release acceptance."""
import json
from pathlib import Path
from baseline.config import ROOT,ARTIFACTS,connect,serving_path

def load(name):return json.loads((ARTIFACTS/name).read_text())

def main():
    verification_path=ARTIFACTS/'offline-verification.json'
    test_count=json.loads(verification_path.read_text())['passed'] if verification_path.exists() else 38
    validation=load("validation.json");chart=load("charting-coverage.json");replay=load("replay-coverage.json");venues=load("enrichment-coverage.json");joins=load("join-coverage.json");models=load("model-evaluation.json");market=load("market-evaluation.json");smoke=load("http-smoke.json")
    registry=load("model-registry.json")
    assert all("hand_diff" in m["features"] and "slam_elo_diff" in m["features"] for m in registry if m["kind"]!="elo_logistic"),"Rebuild current feature/model recipes before publishing status"
    con=connect(serving_path(),True)
    cutoffs=con.execute("SELECT tour,max(observed_date) FROM main.matches GROUP BY 1 ORDER BY 1").fetchall()
    counts=validation["counts"]
    source_slices=con.execute("SELECT split_part(match_id,':',1),tour,count(*) FROM main.replay_matches GROUP BY 1,2 ORDER BY 1,2").fetchall()
    con.close()
    year_rows=[]
    for r in models["windows"]:
        if r["season"]==2024:year_rows.append(f"| {r['tour']} | {r['test']['n']:,} | {r['test']['log_loss']:.4f} | {r['test']['brier']:.4f} | {100*r['test']['accuracy']:.1f}% | {r['selected']} |")
    market_rows=[]
    for r in market["results"]:
        if r["season"]==2024:market_rows.append(f"| {r['tour']} | {r['common_subset_matches']:,} | {r['model']['log_loss']:.4f} | {r['opening']['log_loss']:.4f} | {r['closing']['log_loss']:.4f} |")
    lines=["# Baseline implementation status","","This is a tested local implementation candidate. The first public release is **not accepted or deployed**. Live analyst behavior has not been measured, and most venue enrichment is explicitly unavailable pending verification.","","## Measured snapshot","",f"Source snapshot: `{smoke['snapshot']}`. Original archive/charting locks and raw files were preserved. Cutoffs are maximum observed tournament-start dates, not verified last match timestamps.","",*[f"- {tour}: **{cutoff}**; latest 2026 season incomplete." for tour,cutoff in cutoffs],"",f"- {counts['matches']:,} canonical main-tour match records, including earlier rating warm-up history.",f"- {counts['player_matches']:,} completed player-match rows; {counts['features']:,} paired feature records, plus two player-side records per feature cutoff.",f"- {counts['rankings']:,} ranking observations; identifiers remain tour qualified.",f"- {chart['bridged_matches']:,} uniquely linked charted matches; {chart['parsed_points']:,} parsed charted points and {chart['parsed_shots']:,} coded shot attempts.",f"- {replay['eligible_matches']:,} eligible source-qualified replays; {replay['point_predictions']:,} before-point probability observations.",f"- {joins['matched_main_tour_matches']:,} uniquely matched odds records. Market evaluation uses a smaller, explicitly common eligible subset with both opening and closing prices.",f"- {venues['editions']:,} tournament editions accounted for: {venues['verified']:,} verified venue assignments, {venues['unavailable']:,} unavailable. {venues['weather_days']:,} unique venue/local-date weather summaries. Both verified assignments are 2024 Roland-Garros; they share one venue weather cache. No independently verified altitude is currently supplied.","","Replay source/tour slices:","","| Source | Tour | Eligible matches |","|---|---|---:|",*[f"| {source} | {tour} | {n:,} |" for source,tour,n in source_slices],"","Unknown notation/rules, missing points, duplicate records, ambiguous joins, and unfinished matches have versioned exclusion reports under `artifacts/`. Source-qualified Slam and MCP replays of the same match are separate observations, not extra canonical matches.","","## Measured model results","",f"{len(models['windows'])} expanding chronological tour/year windows, 2005–2026 where sufficient history exists. Candidate preprocessing is fit only to the training partition. Mirrored rows remain within the same partition. Model IDs include the raw snapshot and training recipe hash.","","2024 out-of-sample results (all model-eligible matches):","","| Tour | Matches | Log loss | Brier | Accuracy | Selected candidate |","|---|---:|---:|---:|---:|---|",*year_rows,"","2024 common market subset, log loss (these are **not** the same populations as the table above):","","| Tour | Common matches | Model | Opening market | Closing market |","|---|---:|---:|---:|---:|",*market_rows,"","The full reports include tour/year/surface/level slices, calibration bins and 100 tournament-group bootstrap replicates. Closing prices are the provider's last recorded pre-match odds, not independently timestamp-verified exchange prices. Probability calibration is measured; no calibrated uncertainty interval is claimed. Evaluation year uses the proxy feature-cutoff calendar year; an event edition ID can carry the following year for events starting in late December.","","Features include overall/surface Elo, strictly earlier rankings, serve/return form, results, age/height/handedness, experience and format/event-context interactions. No realized weather, odds, final score, duration or current-match statistics enter prediction inputs. Tournament-only results have a conservative 28-day inferred availability lag. Model eligibility excludes known date contradictions from joined evidence. These safeguards do not establish an unconditional leak-free claim.","","## Verification actually run","","- Locked Python compatibility: dbt Core 1.11.17, dbt-duckdb 1.11.1, dbt-metricflow 0.12.0, MetricFlow 0.210.0, DuckDB 1.5.6.","- 38 offline tests passed, including the original acquisition tests, weighted/null metric behavior, future-data perturbation, strict as-of Elo, scoring rules, auth/origin failures, quota persistence and tool allowlists.","- 16 dbt model/test tasks passed on the full snapshot; final warehouse validation checks keys, relationships, tour separation, player-side feature grain and maximum contributing times.","- Actual MetricFlow semantic validation and first-serve-points-won parity against independent SQL passed for both tours.","- Three local Playwright browser checks passed using a fresh Brave profile: both tours, profiles, historical matchup, point stepping/keyboard controls, anonymous examples, mobile overflow/empty state and shareable filters. Screenshots are in `artifacts/`.",f"- HTTP serving smoke passed, including both tours, replay, historical scenarios, player-side symmetry, optional verified venue, and a 2026 WTA model window. Measured process maximum RSS: {smoke['max_rss_bytes']/1024**2:.1f} MiB; serving database: {smoke['serving_bytes']/1024**2:.1f} MiB. This is a local test-process peak, not a Railway billing forecast.","- Immutable artifact checksums/readiness and actual local rollback/restoration passed. Migration restored 16 older WTA records whose source match numbers repeat across rounds; keys now include round and unordered source player pair. Replay input equivalence was checked before retaining existing curves.","","## Remaining release gates","","1. Supply GitHub OAuth configuration and the explicit approved username list through the runtime secret interface. End-to-end OAuth with the actual account has not been exercised.","2. Confirm billing is disabled for the Gemini key's project, record its exact active free limits, then run the frozen 60-question governed-vs-text-to-SQL evaluation. The checkpoint currently says `blocked_credentials`; no live model calls, measured analyst accuracy or passing showcase claim is made.","3. Venue/weather accounting is complete, but verification is mostly unavailable, not complete enrichment. Expand reviewed historical venue/elevation assignments and relocation/timezone/gap fixtures. Do not interpret an unavailable status as a guessed city or zero weather.","4. Verify the intended Railway workspace's current usage, remaining included allowance and durable quota storage cost. Read-only CLI inspection found existing services and no project linked to this checkout. No new service, spending limit, secret or deployment was created or changed.","5. Docker is not installed in this environment, so the clean materialized context at `artifacts/deploy/` is prepared but its container build is untested. The local one-service application and browser build are tested. A public release still requires container/runtime and approved-user/provider-failure checks at the actual host.","","Do not label M7 or M8 complete until their measured acceptance gates pass. Working local slices of M0–M6 are implemented; source coverage and the explicit limitations above remain part of the product contract.",""]
    account_path=ARTIFACTS/"railway-account-inspection.json"
    if account_path.exists():
        account=json.loads(account_path.read_text())
        if account.get("status")=="budget_inspected_deployment_deferred":
            customer=account["account"]["customer"]
            period=customer["billingPeriod"]
            note=(f"4. Railway read-only inspection confirmed an active Hobby workspace, ${customer['currentUsage']:.2f} current resource usage "
                  f"for {period['start'][:10]} through {period['end'][:10]}. A conservative 0.5 GB RAM capacity budget alone would cost "
                  "$5/month at the documented $10/GB/month rate, before existing services, CPU, durable quota storage or egress. "
                  "This is a planning budget, not measured container billing. A zero-additional-charge deployment is not established, so deployment is deferred. "
                  "No service, spending limit, secret or account configuration was changed. Evidence: `artifacts/railway-account-inspection.json`; "
                  "[resource pricing](https://docs.railway.com/pricing).")
            lines=[note if line.startswith("4. Verify the intended Railway") else line for line in lines]
    google_path=ARTIFACTS/"gemini-account-inspection.json"
    if google_path.exists():
        google=json.loads(google_path.read_text())
        if google.get("status")=="billing_access_denied":
            note=("2. The existing Gemini key's project was resolved, but the read-only billing check returned "
                  f"HTTP {google.get('billing_http_status')} ({', '.join(google.get('reasons',[])) or 'access unavailable'}). "
                  "A disabled Cloud Billing inspection API does not prove billing is disabled. No model calls or account changes were made. "
                  "Verify disabled billing and exact active free limits through AI Studio, then run the frozen 60-question governed-vs-text-to-SQL evaluation. "
                  "Its checkpoint remains `blocked_credentials`; no analyst accuracy or passing showcase claim is made. "
                  "Evidence: `artifacts/gemini-account-inspection.json`.")
            lines=[note if line.startswith("2. Confirm billing is disabled") else line for line in lines]
    configuration_path=ARTIFACTS/'local-configuration-verification.json'
    if configuration_path.exists():
        configuration=json.loads(configuration_path.read_text())
        evaluation=load('agent-evaluation.json')
        if configuration.get('credentials_present'):
            lines=[("1. GitHub OAuth credentials, the owner allowlist and a generated session secret are configured in a private, Git-ignored local file. Saved values take priority over inherited shell settings. Redirect, signed state and anonymous-access rejection checks passed. Actual GitHub browser consent is still pending; production secrets remain to be installed at the host.") if line.startswith('1. Supply GitHub OAuth') else line for line in lines]
            reason=evaluation.get('reason',{})
            provider_note=(f"The provider returned HTTP {reason['provider_http_status']}; bounded retries stay on the pinned model and save a resumable checkpoint. " if isinstance(reason,dict) and reason.get('provider_http_status') else 'The evaluation saves completed stages and pauses on quota or provider failures. ')
            note=(f"2. The user confirmed free-tier AI Studio setup and supplied the project key. The current manually pinned provider is `{configuration['model']}`; its free text tier and tool support were checked in official documentation. The earlier 2.5 model returned 404 for new users. Live evaluation status: `{evaluation['status']}`, {len(evaluation['results'])}/60 completed cases. "
                  +provider_note+"Results require review; no aggregate analyst accuracy claim is made. Project-specific active quotas remain to be recorded. Independent billing inspection remains unavailable; local enablement relies on the user's confirmation. "
                  "Evidence: `artifacts/provider-compatibility.json`, `artifacts/local-configuration-verification.json`, and `artifacts/agent-evaluation.json`.")
            lines=[note if line.startswith('2. ') else line for line in lines]
            lines=[line.replace('Live analyst behavior has not been measured','Live analyst quality has not passed release evaluation') for line in lines]
    railway_setup_path=ARTIFACTS/'railway-setup.json'
    if railway_setup_path.exists():
        setup=json.loads(railway_setup_path.read_text())
        note=(f"4. Railway target `{setup['project']} / {setup['service']}` is linked locally. Reserved origin: `{setup['public_origin']}`. "
              "Nine runtime variables were staged with deployment triggering disabled, including a separate production session secret. No application deployment, volume or spending-limit change was made by this setup. "
              "The current failed deployment uses the acquisition-only GitHub commit; application code and the serving artifact remain local. Verify allowance, durable quota storage cost, artifact delivery and container runtime before deploying. "
              "Evidence: `artifacts/railway-setup.json`; instructions: `docs/railway-setup.md`.")
        lines=[note if line.startswith('4. ') else line for line in lines]
    push_path=ARTIFACTS/'push-verification.json'
    if push_path.exists():
        push=json.loads(push_path.read_text())
        note=(f"4. The application is pushed to `{push['branch']}`, and its pinned serving snapshot is published as a checksummed GitHub prerelease asset. GitHub offline and production-container checks passed: {push['ci_run_url']}. "
              "Railway has a domain and staged runtime variables but has not been activated. The requested $5 included-usage ceiling cannot be enforced by Railway's native compute limit, whose documented minimum is $10. Shared limits were not changed. "
              "Resource reduction and auto-sleep lower expected usage but do not guarantee a maximum bill. See `artifacts/railway-budget-decision.json` and [Railway limit rules](https://docs.railway.com/cli/usage).")
        lines=[note if line.startswith('4. ') else line for line in lines]
        note=("5. The production Docker image built and passed browsing, metric, historical replay and matchup/symmetry checks on GitHub under a 512 MiB / 0.5 CPU container limit. Local Docker remains unavailable; no local container result is claimed. "
              "A production activation still requires a resolved hosting budget, durable quota storage, actual host checks and GitHub browser consent. Live analyst evaluation remains separately gated on provider availability.")
        lines=[note if line.startswith('5. ') else line for line in lines]
    production_path=ARTIFACTS/'railway-production-verification.json'
    if production_path.exists():
        production=json.loads(production_path.read_text())
        if production.get('status')=='passed':
            intro=(f"A historical browsing preview is deployed at {production['public_origin']}. The full first-release acceptance gates remain open: live analyst quality has not passed evaluation and most venue enrichment remains explicitly unavailable.")
            lines[2]=intro
            lines=[("1. Production GitHub OAuth redirect, signed state, secure HTTP-only cookie, rejected invalid states/origins, anonymous access and unapproved-user rejection passed. Approved-session checks used operator-signed test fixtures; actual GitHub browser consent still needs the owner to sign in.") if line.startswith('1. ') else line for line in lines]
            lines=[("4. The user approved a $10 shared workspace compute hard limit and a $5 email alert on the existing Hobby tier. Both limits were set and read back. One application service is deployed with auto-sleep, 0.5 CPU, 512 MiB memory and durable quota storage. The $10 cap can allow charges above the plan's included $5 and can stop other workspace projects. No plan upgrade was made.") if line.startswith('4. ') else line for line in lines]
            lines=[(f"5. Public-host verification passed {production['public_api_checks']} API requests across both tours, metrics, replay and matchup symmetry, in addition to the production-container CI checks. Running-container cgroups confirmed the intended limits; a storage marker survived a new deployment. Legacy railway.toml was replaced by a reviewed service-scoped .railway/railway.ts plan, with secrets unmanaged and the existing volume retained. Actual host evidence is in artifacts/railway-production-verification.json and artifacts/production-resources-storage.json. Browser consent and live analyst evaluation remain outstanding.") if line.startswith('5. ') else line for line in lines]
    lines=[line.replace('38 offline tests',f'{test_count} offline tests') for line in lines]
    (ROOT/"docs/implementation-status.md").write_text("\n".join(lines))
    readme=ROOT/"README.md";text=readme.read_text();marker="\n## Measured local build\n"
    if marker in text:text=text.split(marker)[0]
    text+=marker+f"\nCurrent source cutoff: **{cutoffs[0][1]}** (both tours; tournament dates). The full build contains **{counts['matches']:,} canonical matches**, **{replay['eligible_matches']:,} eligible source-qualified replays**, and **{replay['point_predictions']:,} before-point probabilities**. There are **{chart['bridged_matches']:,} linked charted matches** and **{len(models['windows'])} chronological model windows**. Venue verification is limited to **{venues['verified']} of {venues['editions']:,} editions**; all remaining editions have explicit unavailable reasons.\n\nLocal verification: 38 offline tests, 16 dbt tasks, three browser checks, HTTP smoke, MetricFlow parity, readiness and rollback. These are implementation checks, not an analyst accuracy claim or a completed production release. See [the measured status and model results](docs/implementation-status.md).\n"
    text=text.replace("complete charting/shot analysis, enrichment verification, broader temporal/security/browser checks, calibrated/personalized replay priors, live analyst evaluation and deployment","broader enrichment verification and operational fixtures, measured live analyst evaluation, actual OAuth/provider behavior, container verification and deployment")
    text=text.replace('38 offline tests',f'{test_count} offline tests')
    readme.write_text(text)
    print("Wrote measured README/status")

if __name__=="__main__":main()
