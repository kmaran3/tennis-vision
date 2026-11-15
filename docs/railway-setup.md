# Current Railway setup

Target: **wonderful-truth / production / tennis-vision**.

Reserved public origin: `https://tennis-vision-production.up.railway.app`.

The local CLI is linked to this target. Nine runtime variables, including the GitHub and Gemini credentials, were installed through stdin with `--skip-deploys`. Production uses a separate generated session secret. Secret values are not recorded in this guide or in Git. No new application deployment was started and no spending limits were changed.

## User account step

Update the Baseline GitHub OAuth app:

- Homepage URL: `https://tennis-vision-production.up.railway.app`
- Add authorization callback URL: `https://tennis-vision-production.up.railway.app/api/v1/auth/callback`
- Retain the localhost callback for local testing if the form allows multiple callbacks.

## Deployment work still required

The existing failed Railway deployment points at `e7908e9`, the acquisition-only repository commit. The application implementation remains local, and the serving database is intentionally Git-ignored. A GitHub connection alone cannot supply the current serving artifact.

The prepared local bundle at `artifacts/deploy/` contains application sources, the Dockerfile and a materialized checksummed serving release. Regenerate it after source/artifact changes:

```sh
uv run python scripts/export_deploy.py
```

After verifying the authorized hosting allowance and container/runtime requirements, the explicit bundle upload command is:

```sh
railway up artifacts/deploy --path-as-root --no-gitignore \
  --project 34f5145c-abbd-4ffa-9a3e-f6d8283b28ce \
  --environment production --service tennis-vision
```

This command starts a real deployment and must not run before the no-additional-charge condition is satisfied. `--no-gitignore` is appropriate only for this clean exported context, which excludes credentials and raw sources. Repository-triggered deployments still need a deliberate serving-artifact delivery mechanism; they cannot build from the current GitHub tree.

Authenticated analyst quotas require durable storage mounted at `/app/state`; `BASELINE_QUOTA_DB` is staged as `/app/state/analyst-quota.sqlite`. Volume cost belongs in the hosting calculation. No volume was created.

The generated domain is reserved; it does not indicate a healthy application. Final checks require `/health/ready`, public browsing, actual OAuth consent, provider/quota failures and rollback at the host. Live analyst evaluation is currently paused on Google's HTTP 503 high-demand responses.
