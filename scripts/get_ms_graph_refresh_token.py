#!/usr/bin/env python3
"""
Get a Microsoft Graph refresh token for a personal Outlook/Hotmail account.

Before running, create an app registration that supports personal Microsoft
accounts and add this exact redirect URI:

    http://localhost:8765/callback

Then run from CRM_BACKEND:

    # Case Activity / Outlook email fetching mailbox
    python scripts/get_ms_graph_refresh_token.py --purpose read --write-env

    # Outgoing no-reply sender mailbox
    python scripts/get_ms_graph_refresh_token.py --purpose send --write-env
"""

import argparse
import base64
import hashlib
import html
import os
import secrets
import sys
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Dict, Optional

import requests
from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = BACKEND_ROOT / ".env"
DEFAULT_PORT = 8765
DEFAULT_SCOPES = "offline_access User.Read Mail.Read Mail.Send"


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def _authorization_url(
    *,
    tenant: str,
    client_id: str,
    redirect_uri: str,
    scopes: str,
    state: str,
    code_challenge: str,
) -> str:
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": scopes,
        "state": state,
        "prompt": "select_account",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return (
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?"
        f"{urllib.parse.urlencode(params)}"
    )


def _make_callback_handler(expected_state: str):
    class CallbackHandler(BaseHTTPRequestHandler):
        auth_code: Optional[str] = None
        error: Optional[str] = None

        def log_message(self, format: str, *args) -> None:
            return

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)

            state = query.get("state", [""])[0]
            error = query.get("error_description", query.get("error", [""]))[0]
            code = query.get("code", [""])[0]

            if state != expected_state:
                self.__class__.error = "State mismatch. Please retry the login flow."
                body = "State mismatch. You can close this tab and retry."
                status = 400
            elif error:
                self.__class__.error = error
                body = f"Microsoft returned an error: {html.escape(error)}"
                status = 400
            elif not code:
                self.__class__.error = "No authorization code was returned."
                body = "No authorization code was returned. Please retry."
                status = 400
            else:
                self.__class__.auth_code = code
                body = "Authorization received. You can close this tab and return to the terminal."
                status = 200

            payload = (
                "<!doctype html><html><body>"
                f"<h2>{body}</h2>"
                "</body></html>"
            ).encode("utf-8")

            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return CallbackHandler


def _exchange_code_for_token(
    *,
    tenant: str,
    client_id: str,
    client_secret: str,
    code: str,
    code_verifier: str,
    redirect_uri: str,
    scopes: str,
) -> Dict[str, object]:
    data = {
        "client_id": client_id,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "scope": scopes,
        "code_verifier": code_verifier,
    }
    if client_secret:
        data["client_secret"] = client_secret

    response = requests.post(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        data=data,
        timeout=30,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        help_text = ""
        if "AADSTS70002" in response.text:
            help_text = (
                "\n\nThis app registration is requiring a client secret. "
                "Either move the redirect URI to the 'Mobile and desktop applications' "
                "platform, or rerun this script with --client-secret using the secret VALUE."
            )
        elif "AADSTS7000215" in response.text:
            help_text = (
                "\n\nMicrosoft rejected the client secret. If you use --client-secret, "
                "pass the secret VALUE shown once after creation, not the secret ID."
            )
        raise SystemExit(
            "Token exchange failed.\n"
            f"Status: {response.status_code}\n"
            f"Response: {response.text}"
            f"{help_text}"
        ) from exc

    return response.json()


def _upsert_env_values(env_file: Path, values: Dict[str, str]) -> None:
    existing = env_file.read_text() if env_file.exists() else ""
    lines = existing.splitlines()
    seen = set()
    updated = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            updated.append(line)
            continue

        key = line.split("=", 1)[0].strip()
        if key in values:
            updated.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            updated.append(line)

    if updated and updated[-1].strip():
        updated.append("")

    for key, value in values.items():
        if key not in seen:
            updated.append(f"{key}={value}")

    env_file.write_text("\n".join(updated) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Get a delegated Microsoft Graph refresh token for a personal Microsoft account."
    )
    parser.add_argument("--client-id", default="", help="Application/client ID from the app registration.")
    parser.add_argument(
        "--client-secret",
        default="",
        help="Optional. Pass explicitly only if your app registration is a confidential web app.",
    )
    parser.add_argument("--tenant", default="consumers", help="Use consumers for personal Microsoft accounts.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--scopes", default="", help=f"Default: {DEFAULT_SCOPES}")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    parser.add_argument(
        "--purpose",
        choices=["default", "read", "send"],
        default="default",
        help=(
            "Which refresh-token env var to write. read -> MS_GRAPH_READ_REFRESH_TOKEN "
            "for Case Activity. send -> MS_GRAPH_SEND_REFRESH_TOKEN for outgoing email."
        ),
    )
    parser.add_argument(
        "--token-env-key",
        default="",
        help="Override the refresh-token env var name to write.",
    )
    parser.add_argument("--write-env", action="store_true", help="Write the refresh token settings to .env.")
    parser.add_argument("--no-open", action="store_true", help="Print the URL without opening a browser.")
    args = parser.parse_args()

    env_file = Path(args.env_file).resolve()
    load_dotenv(env_file)

    purpose_client_env = {
        "read": "MS_GRAPH_READ_CLIENT_ID",
        "send": "MS_GRAPH_SEND_CLIENT_ID",
    }.get(args.purpose, "MS_GRAPH_CLIENT_ID")
    client_id = (
        args.client_id
        or os.getenv(purpose_client_env, "").strip()
        or os.getenv("MS_GRAPH_CLIENT_ID", "").strip()
    )
    client_secret = args.client_secret.strip()
    purpose_tenant_env = {
        "read": "MS_GRAPH_READ_TENANT_ID",
        "send": "MS_GRAPH_SEND_TENANT_ID",
    }.get(args.purpose, "MS_GRAPH_TENANT_ID")
    tenant = args.tenant or os.getenv(purpose_tenant_env, os.getenv("MS_GRAPH_TENANT_ID", "consumers")).strip()
    purpose_scopes_env = {
        "read": "MS_GRAPH_READ_DELEGATED_SCOPES",
        "send": "MS_GRAPH_SEND_DELEGATED_SCOPES",
    }.get(args.purpose, "MS_GRAPH_DELEGATED_SCOPES")
    scopes = args.scopes or os.getenv(purpose_scopes_env, os.getenv("MS_GRAPH_DELEGATED_SCOPES", DEFAULT_SCOPES)).strip()
    redirect_uri = f"http://localhost:{args.port}/callback"

    if not client_id:
        print("Missing --client-id, and MS_GRAPH_CLIENT_ID was not found in .env.", file=sys.stderr)
        return 2

    code_verifier, code_challenge = _pkce_pair()
    state = secrets.token_urlsafe(24)
    auth_url = _authorization_url(
        tenant=tenant,
        client_id=client_id,
        redirect_uri=redirect_uri,
        scopes=scopes,
        state=state,
        code_challenge=code_challenge,
    )

    handler = _make_callback_handler(state)
    server = HTTPServer(("localhost", args.port), handler)
    server.timeout = 300

    print("\nMicrosoft Graph personal-account login")
    print("--------------------------------------")
    print(f"Redirect URI required in app registration: {redirect_uri}")
    print(f"Tenant endpoint: {tenant}")
    print(f"Scopes: {scopes}")
    print("\nOpen this URL and sign in with your personal Outlook/Hotmail account:\n")
    print(auth_url)
    print("\nWaiting up to 5 minutes for Microsoft to redirect back...")

    if not args.no_open:
        webbrowser.open(auth_url)

    deadline = time.time() + 300
    while time.time() < deadline and not handler.auth_code and not handler.error:
        server.handle_request()

    server.server_close()

    if handler.error:
        print(f"\nLogin failed: {handler.error}", file=sys.stderr)
        return 1

    if not handler.auth_code:
        print("\nTimed out waiting for the browser callback.", file=sys.stderr)
        return 1

    result = _exchange_code_for_token(
        tenant=tenant,
        client_id=client_id,
        client_secret=client_secret,
        code=handler.auth_code,
        code_verifier=code_verifier,
        redirect_uri=redirect_uri,
        scopes=scopes,
    )

    refresh_token = str(result.get("refresh_token") or "").strip()
    if not refresh_token:
        print(
            "Token response did not include a refresh_token. "
            "Make sure offline_access is included in the scopes.",
            file=sys.stderr,
        )
        return 1

    token_env_key = args.token_env_key.strip()
    if not token_env_key:
        token_env_key = {
            "read": "MS_GRAPH_READ_REFRESH_TOKEN",
            "send": "MS_GRAPH_SEND_REFRESH_TOKEN",
        }.get(args.purpose, "MS_GRAPH_REFRESH_TOKEN")

    values = {
        {
            "read": "MS_GRAPH_READ_TENANT_ID",
            "send": "MS_GRAPH_SEND_TENANT_ID",
        }.get(args.purpose, "MS_GRAPH_TENANT_ID"): tenant,
        {
            "read": "MS_GRAPH_READ_CLIENT_ID",
            "send": "MS_GRAPH_SEND_CLIENT_ID",
        }.get(args.purpose, "MS_GRAPH_CLIENT_ID"): client_id,
        token_env_key: refresh_token,
        {
            "read": "MS_GRAPH_READ_DELEGATED_SCOPES",
            "send": "MS_GRAPH_SEND_DELEGATED_SCOPES",
        }.get(args.purpose, "MS_GRAPH_DELEGATED_SCOPES"): scopes,
    }
    if client_secret:
        values[{
            "read": "MS_GRAPH_READ_CLIENT_SECRET",
            "send": "MS_GRAPH_SEND_CLIENT_SECRET",
        }.get(args.purpose, "MS_GRAPH_CLIENT_SECRET")] = client_secret
    if args.purpose == "default":
        values["MS_GRAPH_MAILBOX"] = ""

    if args.write_env:
        _upsert_env_values(env_file, values)
        print(f"\nUpdated {env_file}")
        print(f"Stored {token_env_key} without printing it here.")
    else:
        print("\nAdd these to your .env:")
        for key, value in values.items():
            print(f"{key}={value}")

    print("\nDone. Restart the backend before testing Microsoft Graph.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
