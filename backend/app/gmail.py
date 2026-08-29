from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from .config import settings

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
QUERY = (
    '(from:auto-confirm@amazon.co.uk OR '
    'from:shipment-tracking@amazon.co.uk OR '
    'from:order-update@amazon.co.uk) -in:spam -in:trash'
)

def service():
    creds = Credentials(
        token=None,
        refresh_token=settings.gmail_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.gmail_client_id,
        client_secret=settings.gmail_client_secret,
        scopes=SCOPES,
    )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)

def list_message_ids(max_results=500):
    svc = service()
    ids, page_token = [], None
    while True:
        result = svc.users().messages().list(
            userId="me", q=QUERY, maxResults=min(max_results - len(ids), 500), pageToken=page_token
        ).execute()
        ids.extend(m["id"] for m in result.get("messages", []))
        page_token = result.get("nextPageToken")
        if not page_token or len(ids) >= max_results:
            return ids[:max_results]

def read_message(message_id: str):
    svc = service()
    return svc.users().messages().get(userId="me", id=message_id, format="full").execute()
