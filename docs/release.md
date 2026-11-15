# Release operations

This is an implementation candidate. The first public release remains gated by `implementation-status.md`.

1. Build cached data/models and frontend; run all verification.
2. Review actual `artifacts/` validation/model/market/replay/enrichment/agent reports. Do not substitute unavailable reports with estimated accuracy.
3. `uv run baseline package` copies only serving marts, model files, metric definitions and reports to `data/releases/<snapshot>-<timestamp>/`. It checks every checksum and snapshot/model/metric agreement, then atomically replaces local `current` and retains `previous`.
4. `uv run baseline rollback` validates and atomically restores the previous release. Test rollback in an isolated fixture before operating on a deployed service.
5. Measure steady/peak process RSS under representative browsing and inference requests, cold-start time, and artifact size. `uv run python scripts/prepare_release_asset.py` prepares a deterministic archive and its pinned `deployment/serving-release.json`. Publish the named asset as a versioned GitHub prerelease, preserving source notices and excluding operating account reports. The Docker build downloads and checks the archive and all extracted files before startup. A clean context can also be prepared with `uv run python scripts/export_deploy.py`. GitHub's public-repository verification builds and exercises the production image with a 512 MiB container limit. Readiness verifies artifact checksums and internal versions and fails on mismatch. This currently rechecks all hashes per readiness call; avoid frequent expensive readiness polling.
6. Inspect existing Railway workspace usage, billing-cycle dates and remaining included credit. Compare projected CPU/RAM/egress/storage usage against that remainder. Record evidence. If account access or allowance cannot be verified, defer deployment. Change shared spending limits only with authorization; the current approved compute cap is $10 with a $5 alert. Do not create a second frontend service.
7. Supply GitHub OAuth and free-tier Gemini configuration via Railway variables. Confirm billing is disabled in AI Studio and record the exact project model limits. Never paste credentials into Git, docs, logs, URLs or frontend code. Keep `BASELINE_ORIGIN` HTTPS; keep quota SQLite on writable durable service storage so restarts do not reset daily caps.
8. The Docker build materializes the verified pinned archive at `data/releases/current/` and bundles the built frontend. Use one service, worker, replica. Never publish `.env`, raw source caches or operating account reports as assets. Do not deploy until the cost condition is met.
9. Test public browsing and approved-user chat at the actual URL, unauthorized access, quota/provider failure, version mismatch and rollback. Publish measured results and actual coverage.

The historical browsing preview is deployed in `wonderful-truth / tennis-vision`. The owner approved the $10 workspace compute cap and $5 email alert; both were set and read back. No Hobby plan upgrade was made. See [current deployment and operations](railway-setup.md), [plans](https://docs.railway.com/pricing/plans) and [cost controls](https://docs.railway.com/pricing/cost-control).

Legacy `railway.toml` is replaced by `.railway/railway.ts`. Use the locked SDK and pinned CLI through `npm run infra:plan` and `npm run infra:apply`; inspect for unwanted volume/variable changes before applying. The running container was checked for 0.5 CPU, 512 MiB memory, persistent quota storage and readiness. Live analyst evaluation, actual owner browser consent and broad venue verification remain release gates.

Repeat account inspection without changing account settings:

```sh
BASELINE_RAILWAY_WORKSPACE_ID=<your-workspace-id> uv run python scripts/inspect_accounts.py
```

The script uses existing local CLI authentication, prints no credentials, and never generates model responses. The Google billing inspection API being disabled is an unresolved verification condition, not proof that model billing is disabled.
