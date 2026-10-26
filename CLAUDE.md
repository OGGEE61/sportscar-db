# sportscar-db

## Deploy workflow (Vercel, Hobby plan)

Hobby limits Functions Storage to 10 GB per rolling 30 days, and every deployment counts, so deployments are restricted.

- Only two branches build on Vercel: `master` (production) and `preview` (preview). Every other branch is skipped by `ignoreCommand` in [vercel.json](vercel.json).
- Work happens on feature branches and is not deployed.
- To check a change on Vercel, merge or push the feature branch to `preview`: `git push origin <feature-branch>:preview`. The preview URL is `https://sportscar-db-git-preview-nexopel.vercel.app`.
- After checking, open a PR to `master`. Merging to `master` deploys production.
- Keep only one live deployment per environment. After a deploy, prune old ones with `scripts/vercel_prune.sh` (keeps the current production deployment and the newest preview, deletes the rest). It uses `--safe`, so a deployment that still carries a branch alias must be removed by hand with `npx vercel remove <url>`.
- Keep the function bundle small: see [.vercelignore](.vercelignore). Do not add large files (DBs, models, logs, dumps) to the deployed tree.

## Database migrations

- Migrations live in `init_db()` in [db.py](db.py). It does **not** run on Vercel: apply new ones to production by hand before (or right after) the deploy that needs them: `DB_BACKEND=d1 python -c "from db import init_db; init_db()"`. A deploy that queries a new column without this returns a 500.

## Performance notes

- Production reads Cloudflare D1 over HTTP (each query is a round trip). D1 runs in EEUR, so the function is pinned to `fra1` in [vercel.json](vercel.json); keep them close together.
- Keep pages as a fast shell and load data sections via `/api/...` endpoints (see the dashboard), and avoid sequential queries in a route.
