# JSS XRay database migration/locking fix

This release prevents the PostgreSQL lock condition that previously left backend
pods stuck at `Waiting for application startup`.

## Architecture change

Before:

- FastAPI startup called `ensure_schema()`
- every Gmail CronJob called `ensure_schema()`
- rolling deployments and CronJobs could issue `ALTER TABLE` concurrently
- long-lived read transactions could block DDL and create a lock chain

After:

- API pods perform no DDL
- Gmail CronJobs perform no DDL
- one ArgoCD `PreSync` Job runs `python -m app.migrate`
- PostgreSQL advisory locking serializes migration attempts
- versioned `schema_migrations` prevents the same migration running repeatedly
- the migration checks the catalog before issuing `ALTER TABLE`
- `lock_timeout=10s` makes a blocked migration fail instead of hanging forever
- normal app DB connections use a 60-second `idle_in_transaction_session_timeout`
- `get_db()` explicitly rolls back implicit read transactions before returning the connection to the pool

## ArgoCD flow

GitHub Actions -> immutable Docker image -> Helm values commit -> ArgoCD

ArgoCD then runs:

1. `jss-xray-db-migrate` PreSync Job
2. only after migration success, normal resources sync/roll out
3. backend starts without executing schema changes

## One-time recovery

Before deploying this version, clear the currently stuck PostgreSQL
`idle in transaction` sessions and allow the active migration to finish or fail.
After this version is deployed, future backend/CronJob pods will no longer run DDL.
