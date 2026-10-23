# Database
- PostgreSQL in production (psycopg 3). `postgres://` / `postgresql://` URLs are converted automatically. SQLite is for local dev/tests only.
- Models are unchanged from the previous version: no column or table changes.
- Alembic `0001_baseline` creates a table only if it does not exist, so it is safe on the existing database; its downgrade is intentionally empty (never drops data). `alembic upgrade head` also creates the `alembic_version` table.
- The app never calls `drop_all` and does not use `create_all` as a migration strategy.
- Future schema changes: add a new Alembic revision, test on a copy of a backup, then deploy.
- Audit hash chain writes are serialized with a PostgreSQL advisory lock; bids use row locks.
