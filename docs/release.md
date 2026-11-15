# Release operations

This is an implementation candidate. The first public release remains gated by `implementation-status.md`.

1. Build cached data/models and frontend; run all verification.
2. Review actual `artifacts/` validation/model/market/replay/enrichment/agent reports. Do not substitute unavailable reports with estimated accuracy.
3. `uv run baseline package` copies only serving marts, model files, metric definitions and reports to `data/releases/<snapshot>-<timestamp>/`. It checks every checksum and snapshot/model/metric agreement, then atomically replaces local `current` and retains `previous`.
4. `uv run baseline rollback` validates and atomically restores the previous release. Test rollback in an isolated fixture before operating on a deployed service.
5. Measure steady/peak process RSS under representative browsing and inference requests, cold-start time, and artifact size. `uv run python scripts/prepare_release_asset.py` prepares a deterministic archive and its pinned `deployment/serving-release.json`. Publish the named asset as a versioned GitHub prerelease, preserving source notices and excluding operating account reports. The Docker build downloads and checks the archive and all extracted files before startup. A clean context can also be prepared with `uv run python scripts/export_deploy.py`. GitHub's public-repository verification builds and exercises the production image with a 512 MiB container limit. Readiness verifies artifact checksums and internal versions and fails on mismatch. This currently rechecks all hashes per readiness call; avoid frequent expensive readiness polling.
6. Inspect existing Railway workspace usage, billing-cycle dates and remaining included credit. Compare projected CPU/RAM/egress/storage usage against that remainder. Record evidence. If account access or allowance cannot be verified, defer deployment. Never change shared spending limits or create a second frontend service.
7. Supply GitHub OAuth and free-tier Gemini configuration via Railway variables. Confirm billing is disabled in AI Studio and record the exact project model limits. Never paste credentials into Git, docs, logs, URLs or frontend code. Keep `BASELINE_ORIGIN` HTTPS; keep quota SQLite on writable durable service storage so restarts do not reset daily caps.
8. The Docker build materializes the verified pinned archive at `data/releases/current/` and bundles the built frontend. Use one service, worker, replica. Never publish `.env`, raw source caches or operating account reports as assets. Do not deploy until the cost condition is met.
9. Test public browsing and approved-user chat at the actual URL, unauthorized access, quota/provider failure, version mismatch and rollback. Publish measured results and actual coverage.

The `wonderful-truth / tennis-vision` service now has a reserved public domain and runtime variables staged without triggering a deployment. No spending limits were changed. See [current setup and remaining deployment work](railway-setup.md). The Hobby subscription alone does not authorize additional usage charges. See [plans](https://docs.railway.com/pricing/plans) and [cost controls](https://docs.railway.com/pricing/cost-control).

The current read-only account check is recorded in `artifacts/railway-account-inspection.json`. A 0.5 GB RAM planning budget alone consumes the $5 monthly Hobby allowance at the [published resource rate](https://docs.railway.com/pricing), before existing services, CPU, volume storage and egress. This is not a measured container forecast; deployment remains deferred under the no-additional-charge condition. No shared limits were altered.

Repeat account inspection without changing account settings:

```sh
BASELINE_RAILWAY_WORKSPACE_ID=<your-workspace-id> uv run python scripts/inspect_accounts.py
```

The script uses existing local CLI authentication, prints no credentials, and never generates model responses. The Google billing inspection API being disabled is an unresolved verification condition, not proof that model billing is disabled.
