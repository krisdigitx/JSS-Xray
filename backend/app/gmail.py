import json
import random
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from functools import lru_cache

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .config import settings

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
BASE_QUERY = (
    '(from:auto-confirm@amazon.co.uk OR '
    'from:shipment-tracking@amazon.co.uk OR '
    'from:order-update@amazon.co.uk) -in:spam -in:trash'
)


@lru_cache(maxsize=1)
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


def _retry_delay(exc: HttpError, attempt: int) -> float:
    """Respect Gmail Retry-After when present, otherwise exponential backoff."""
    now = datetime.now(timezone.utc)
    retry_after = None

    try:
        retry_after = exc.resp.get("retry-after")
    except Exception:
        retry_after = None

    if retry_after:
        try:
            return max(1.0, min(float(retry_after), 300.0))
        except ValueError:
            try:
                retry_dt = parsedate_to_datetime(retry_after)
                if retry_dt.tzinfo is None:
                    retry_dt = retry_dt.replace(tzinfo=timezone.utc)
                return max(1.0, min((retry_dt - now).total_seconds(), 300.0))
            except Exception:
                pass

    # Google sometimes puts an absolute retry timestamp in the JSON message.
    try:
        payload = json.loads(exc.content.decode("utf-8", errors="replace"))
        message = payload.get("error", {}).get("message", "")
        match = re.search(r"Retry after ([0-9T:\-\.]+Z)", message, re.I)
        if match:
            retry_dt = datetime.fromisoformat(match.group(1).replace("Z", "+00:00"))
            return max(1.0, min((retry_dt - now).total_seconds(), 300.0))
    except Exception:
        pass

    # 5, 10, 20, 40, 80 seconds + jitter.
    return min(5 * (2 ** attempt) + random.uniform(0, 2), 120.0)


def execute_with_retry(request, retries: int = 5):
    for attempt in range(retries):
        try:
            return request.execute()
        except HttpError as exc:
            status = getattr(exc.resp, "status", None)
            if status not in (429, 500, 502, 503, 504) or attempt == retries - 1:
                raise
            delay = _retry_delay(exc, attempt)
            print(f"Gmail API returned HTTP {status}; retrying in {delay:.1f}s "
                  f"(attempt {attempt + 1}/{retries})", flush=True)
            time.sleep(delay)


def list_message_ids(max_results: int = 50, after=None):
    """
    List only recent Amazon messages.

    `after` is a datetime. Gmail accepts a Unix timestamp in its search syntax,
    and the sync intentionally overlaps the previous window so DB dedupe can
    safely absorb delayed/reordered messages.
    """
    query = BASE_QUERY
    if after is not None:
        if after.tzinfo is None:
            after = after.replace(tzinfo=timezone.utc)
        query += f" after:{int(after.timestamp())}"

    result = execute_with_retry(
        service().users().messages().list(
            userId="me",
            q=query,
            maxResults=max(1, min(max_results, 100)),
        )
    )
    return [m["id"] for m in result.get("messages", [])]


def read_message(message_id: str):
    return execute_with_retry(
        service().users().messages().get(
            userId="me",
            id=message_id,
            format="full",
        )
    )
