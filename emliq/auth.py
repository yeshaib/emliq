import json
import os
import urllib.parse
import urllib.request

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow, InstalledAppFlow
from googleapiclient.discovery import build

from .config import CREDENTIALS, SCOPES, TOKEN, ensure_home


class NotAuthenticated(Exception):
    pass


def login(open_browser=True, port=0, bind_addr=None):
    """Run Google's OAuth flow. In Docker, pass a fixed port that's published to the
    host and bind_addr="0.0.0.0" so the browser's redirect to localhost reaches us."""
    ensure_home()
    if not CREDENTIALS.exists():
        raise SystemExit(
            f"Missing {CREDENTIALS}.\n"
            "Create a 'Desktop app' OAuth client in Google Cloud Console and save its JSON there "
            "(see README.md)."
        )
    # Google's consent screen lets people untick individual scopes; check for that
    # ourselves instead of letting oauthlib raise a cryptic "Scope has changed" warning.
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS), SCOPES)
    creds = flow.run_local_server(port=port, bind_addr=bind_addr, open_browser=open_browser)
    try:
        _check_scopes(creds)
    except ValueError as e:
        raise SystemExit(str(e))
    _save(creds)
    return creds


def _check_scopes(creds):
    granted = set(creds.granted_scopes or creds.scopes or [])
    missing = [s for s in SCOPES if s not in granted]
    if missing:
        raise ValueError(
            "Not all permissions were granted. Sign in again and tick every checkbox on Google's "
            "consent screen. Missing: " + ", ".join(missing)
        )


# ---- sign in / out from the web UI -------------------------------------------------

_pending = {}  # OAuth state -> Flow, for sign-ins started from the UI


def has_client():
    return CREDENTIALS.exists()


def save_client(text):
    """Store an uploaded Google OAuth client file (Desktop app type)."""
    try:
        data = json.loads(text)
    except ValueError:
        raise ValueError("That file isn't valid JSON.")
    info = data.get("installed") if isinstance(data, dict) else None
    if not info:
        raise ValueError('That isn\'t a "Desktop app" OAuth client file. Create one of type Desktop app in Google Cloud Console.')
    if not info.get("client_id") or not info.get("client_secret"):
        raise ValueError("The file is missing client_id or client_secret.")
    ensure_home()
    CREDENTIALS.write_text(json.dumps(data), encoding="utf-8")
    os.chmod(CREDENTIALS, 0o600)


def start_web_login(redirect_uri):
    """Return Google's consent URL; Google sends the browser back to redirect_uri."""
    if not has_client():
        raise ValueError("Add your Google OAuth client file first.")
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
    flow = Flow.from_client_secrets_file(
        str(CREDENTIALS), SCOPES, redirect_uri=redirect_uri, autogenerate_code_verifier=True
    )
    url, state = flow.authorization_url(access_type="offline", prompt="select_account consent", include_granted_scopes="true")
    _pending.clear()  # only the latest attempt is valid
    _pending[state] = flow
    return url


def finish_web_login(state, code):
    flow = _pending.pop(state, None)
    if flow is None:
        raise ValueError("That sign-in link expired. Start again from emliq.")
    flow.fetch_token(code=code)
    creds = flow.credentials
    _check_scopes(creds)
    _save(creds)
    return creds


def status():
    if not TOKEN.exists():
        return {"signed_in": False, "has_client": has_client()}
    try:
        load_credentials()
        return {"signed_in": True, "has_client": True}
    except Exception:
        return {"signed_in": False, "has_client": has_client(), "expired": True}


def sign_out(revoke=True):
    """Forget the Gmail sign-in, and by default revoke emliq's access at Google too."""
    if TOKEN.exists() and revoke:
        try:
            data = json.loads(TOKEN.read_text(encoding="utf-8"))
            token = data.get("refresh_token") or data.get("token")
            if token:
                req = urllib.request.Request(
                    "https://oauth2.googleapis.com/revoke",
                    data=urllib.parse.urlencode({"token": token}).encode(),
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                urllib.request.urlopen(req, timeout=10).close()
        except Exception:
            pass  # already revoked or offline; forgetting it locally still signs out
    TOKEN.unlink(missing_ok=True)


def _save(creds):
    TOKEN.write_text(creds.to_json(), encoding="utf-8")
    os.chmod(TOKEN, 0o600)


def load_credentials():
    if not TOKEN.exists():
        raise NotAuthenticated("Not signed in. Sign in with Google in Settings.")
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                raise NotAuthenticated("Your Google sign-in expired. Sign in again in Settings.")
            _save(creds)
        else:
            raise NotAuthenticated("Your Google sign-in expired. Sign in again in Settings.")
    return creds


def gmail():
    """Build a Gmail client. Clients aren't thread-safe, so build one per thread/request."""
    return build("gmail", "v1", credentials=load_credentials(), cache_discovery=False)
