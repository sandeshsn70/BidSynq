# Deployment (Render + PostgreSQL)

Targets: backend https://bidsynq.onrender.com, frontend https://bidsynq-frontend.onrender.com.
**This guide was written but not executed against your Render account.** Follow the checklist at the end to verify.

## 0. Before anything: back up your database
Render dashboard -> your PostgreSQL -> Backups (or run `pg_dump "<External Database URL>" -f backup.sql`).
Do this before every deploy. **Never delete or recreate the database.** This release makes no schema changes;
the migration only creates tables that are missing and leaves existing data untouched.

## 1. Replace the GitHub repo contents (PowerShell)
```
cd C:\path\to\your\BidSynq-clone      # git clone https://github.com/sandeshsn70/BidSynq if needed
git pull
# delete old files EXCEPT the .git folder, then copy in the contents of the new ZIP (not the folder itself)
git status
git add -A
git commit -m "BidSynq V5.1 rebuild"
git push
```
Check `git status` shows no `.env`, `node_modules`, or `.db` files before committing.

## 2. Backend web service (Render)
- Runtime: Python 3.12 (set env `PYTHON_VERSION=3.12.7`); Root directory: repository root
- Build command: `pip install -r requirements.txt`
- Start command: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health check path: `/health`
- Environment variables:

| Name | Value |
|---|---|
| SECRET_KEY | random string, 32+ chars (keep your existing one so current logins stay valid; it must be >=32 chars or the app refuses to start) |
| DATABASE_URL | Internal Database URL of your existing Render PostgreSQL |
| CORS_ORIGINS | `https://bidsynq-frontend.onrender.com` |
| BIDSYNQ_ALLOW_ADMIN_REGISTRATION | `false` |
| GROQ_API_KEY | optional; leave empty for extractive answers |
| GROQ_MODEL, GROQ_TIMEOUT_SECONDS, MAX_DOCUMENT_MB, ACCESS_TOKEN_MINUTES | optional (defaults ok) |
| DOCUMENT_STORAGE_DIR | optional; point at a persistent disk path if you attach one |

On Render the app refuses to start if SECRET_KEY is weak/default, the DB is not PostgreSQL, admin registration is on, or CORS has `*`.
Uploaded files live on local disk: on Render without a persistent disk they are lost on redeploy (see SECURITY.md).

## 3. Frontend web service
- Root directory: `frontend`; Build: `npm ci && npm run build`; Start: `npm start`; Node 20+
- Env var (needed at **build** time): `NEXT_PUBLIC_API_URL=https://bidsynq.onrender.com`. Redeploy after changing it. Put no secrets in `NEXT_PUBLIC_*`.

## 4. Create the first admin
Admin self-registration is disabled. Register normally, then in the Render backend Shell:
`python -m app.scripts.promote_admin you@example.com`

## 5. Post-deployment checklist
1. `https://bidsynq.onrender.com/health` -> status ok, database ok, `migration_revision` = `0001`.
2. Log in with an existing account: old tenders/bids still present.
3. Register a new buyer and supplier; create a tender; submit a bid; view ranking.
4. Upload a PDF; ask the assistant a question.
5. As admin: Audit page -> Verify chain returns valid.
6. Browser console shows no CORS errors.

## 6. Rollback
Redeploy the previous commit from Render (Deploys -> Rollback). Schema is unchanged, so no DB rollback is needed.
If data is ever damaged, restore from the backup taken in step 0 into a **new** database and repoint DATABASE_URL.
