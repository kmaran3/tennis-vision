# Railway deployment

The historical browsing preview is live at **https://tennis-vision-production.up.railway.app**.

Target: **wonderful-truth / production / tennis-vision**. Main receives the tested application through GitHub; the Docker build downloads the public serving archive pinned by exact URL, SHA-256, byte size, snapshot and metric version in `deployment/serving-release.json`. No training or full warehouse build runs on startup.

## Runtime configuration

One service and worker, one replica in us-west2, auto-sleep, 0.5 CPU and 512 MiB memory. `/health/ready` checks database/model/metric agreement. The public domain targets port 8000, matching `PORT=8000`.

The persistent volume is attached at `/app/state`; `BASELINE_QUOTA_DB=/app/state/analyst-quota.sqlite`. A marker survived replacement of the running container. The volume's 5 GB capacity is not a forecast of used storage; the quota ledger is small.

Runtime secrets are installed through Railway variables. Production uses a separate session secret from local development. GitHub OAuth uses this homepage and callback:

- Homepage: `https://tennis-vision-production.up.railway.app`
- Callback: `https://tennis-vision-production.up.railway.app/api/v1/auth/callback`

No credentials are stored in Git, public assets, frontend bundles or this document. Actual GitHub browser consent must still be completed by the owner.

## Infrastructure changes

New Railway services no longer read legacy `railway.toml` settings. This repository uses `.railway/railway.ts`, TypeScript SDK 3.17.0 and CLI 5.74.0. Install the locked development SDK and inspect changes:

```sh
npm ci
npm run infra:check
npm run infra:plan
```

The named partial owns only this service and its quota volume. Secrets are unmanaged: the plan never reads or changes their values. Review the plan before applying:

```sh
npm run infra:apply -- --yes
```

Apply only expected changes. A normal settings update must not delete variables, detach/delete the volume, or change unrelated resources. The migration was applied from a pinned plan containing only two safe service updates. Afterward, the plan had no drift and cgroups confirmed the running limits. Code pushes deploy automatically; infrastructure-file edits require the explicit plan/apply step. Watch patterns avoid application rebuilds for documentation-only changes.

## Approved budget

The owner approved a **$10 shared workspace compute hard limit** and **$5 email alert**, which were set and read back. The Hobby subscription was not upgraded. This can allow usage above the included $5; reaching the shared limit can stop other workspace projects. Do not change these limits without authorization.

## Verification and remaining gates

49 offline tests and production-image checks passed. The public host passed 24 API checks and desktop/mobile browser flows. OAuth redirect/state/cookie and rejected-access checks passed using operator test sessions. The persistent ledger and mount were checked on the actual service.

Google's free-tier analyst requests currently time out or return service errors. Browsing, predictions, replay and saved examples remain available. The fixed 60-question analyst evaluation is resumable and has not passed. Most venue assignments remain explicitly unavailable. Deployment of this preview does not mark the complete first release accepted.
