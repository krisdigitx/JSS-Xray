import json
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
path = Path("client_secret.json")
if not path.exists():
    raise SystemExit("Put Google OAuth Desktop credentials at ./client_secret.json and run again.")

flow = InstalledAppFlow.from_client_secrets_file(str(path), SCOPES)
creds = flow.run_local_server(port=0)

print("\nStore these in Vault / your local .env. Do NOT commit them:\n")
print(f"GMAIL_CLIENT_ID={creds.client_id}")
print(f"GMAIL_CLIENT_SECRET={creds.client_secret}")
print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}")
