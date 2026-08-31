# JSS XRay multi-account configuration

Configured Amazon accounts:

1. Tauri Royale (`tauri-royale`)
2. Polaris Zone (`polaris-zone`)
3. JSS Traders (`jss-traders`)

## Existing data migration

On backend startup, existing orders are automatically assigned to **Tauri Royale**.
The migration is additive and does not delete existing orders/events/items.

## Vault / Kubernetes secrets

The Helm chart expects:

- `jss-xray-secrets` — existing shared secret. It contains `POSTGRES_PASSWORD` and currently the Tauri Royale Gmail OAuth keys.
- `jss-xray-polaris-zone` — Gmail OAuth keys for Polaris Zone.
- `jss-xray-jss-traders` — Gmail OAuth keys for JSS Traders.

Each Gmail account secret needs only:

- `GMAIL_CLIENT_ID`
- `GMAIL_CLIENT_SECRET`
- `GMAIL_REFRESH_TOKEN`

Recommended Vault paths:

- `secret/home-lab/jss-xray/accounts/polaris-zone`
- `secret/home-lab/jss-xray/accounts/jss-traders`

Tauri Royale can keep using the existing `secret/home-lab/jss-xray` path for now.

## Google OAuth

You may use the same Google OAuth Client ID / Client Secret for all three Gmail accounts.
Add each Gmail address as an OAuth test user (while the app is in Testing) and generate a separate refresh token for each account.

## Sync

Helm now creates three CronJobs:

- `jss-xray-gmail-sync-tauri-royale`
- `jss-xray-gmail-sync-polaris-zone`
- `jss-xray-gmail-sync-jss-traders`

All write to the same PostgreSQL database while tagging each order with its Amazon account.

## UI

The frontend has an account selector:

- All Accounts
- Tauri Royale
- Polaris Zone
- JSS Traders

Search and pagination operate within the selected account.
