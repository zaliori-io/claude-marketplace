#!/usr/bin/env python3
"""
Saxo OpenAPI authentication manager — PKCE flow with macOS Keychain storage.

Usage:
  python saxo_auth.py login    [--force]   Authenticate via browser
  python saxo_auth.py refresh              Force token refresh now
  python saxo_auth.py status               Show token validity and expiry times
  python saxo_auth.py logout               Delete stored tokens from Keychain
  python saxo_auth.py token                Print current access token (debug)
"""

import argparse
import base64
import hashlib
import json
import os
import pathlib
import platform
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

# ---------------------------------------------------------------------------
# 1a — platform guard
# ---------------------------------------------------------------------------

if platform.system() != "Darwin":
    raise NotImplementedError(
        "saxo_auth requires macOS (Keychain). Linux/Windows support deferred."
    )

# ---------------------------------------------------------------------------
# 1b — custom exceptions
# ---------------------------------------------------------------------------


class SaxoAuthError(Exception):
    pass


class SaxoLoginRequired(SaxoAuthError):
    pass


# ---------------------------------------------------------------------------
# 1c — constants
# ---------------------------------------------------------------------------

AUTH_URLS = {
    "sim": {
        "authorize": "https://sim.logonvalidation.net/authorize",
        "token":     "https://sim.logonvalidation.net/token",
    },
    "live": {
        "authorize": "https://live.logonvalidation.net/authorize",
        "token":     "https://live.logonvalidation.net/token",
    },
}

CONFIG_PATH   = pathlib.Path.home() / ".config" / "saxo" / "config.json"
KC_PREFIX     = "saxotrader"   # suffixed with "-live" or "-sim"
KC_ACCOUNT    = "tokens"
EXPIRY_BUFFER = 60               # treat access token as expired 60 s early

# ---------------------------------------------------------------------------
# 1d — load_config
# ---------------------------------------------------------------------------


def load_config(path=None) -> dict:
    """Load and validate ~/.config/saxo/config.json (or override path)."""
    cfg_path = pathlib.Path(path) if path else CONFIG_PATH
    try:
        raw = cfg_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        sys.exit(
            f"Config file not found: {cfg_path}\n"
            f"Copy skills/saxo/config.example.json to {cfg_path} and fill in your client_id."
        )
    except OSError as e:
        sys.exit(f"Cannot read config file {cfg_path}: {e}")

    try:
        cfg = json.loads(raw)
    except json.JSONDecodeError as e:
        sys.exit(f"Config file {cfg_path} is not valid JSON: {e}")

    required = ("client_id", "redirect_uri", "callback_port", "environment")
    missing  = [k for k in required if k not in cfg]
    if missing:
        sys.exit(f"Config file {cfg_path} is missing required keys: {', '.join(missing)}")

    if cfg["environment"] not in AUTH_URLS:
        sys.exit(
            f"Config 'environment' must be 'live' or 'sim', got: {cfg['environment']!r}"
        )

    return cfg


# ---------------------------------------------------------------------------
# 1e — Keychain helpers
# ---------------------------------------------------------------------------


def _kc_service(env: str) -> str:
    return f"{KC_PREFIX}-{env}"


def _kc_read(env: str) -> dict | None:
    result = subprocess.run(
        ["security", "find-generic-password",
         "-s", _kc_service(env), "-a", KC_ACCOUNT, "-w"],
        capture_output=True, text=True,
    )
    if result.returncode == 44:   # "item not found" — normal on first run
        return None
    if result.returncode != 0:
        raise SaxoAuthError(f"Keychain read failed: {result.stderr.strip()}")
    try:
        return json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        raise SaxoAuthError(
            "Corrupted token in Keychain. Run: python saxo_auth.py logout"
        )


def _kc_write(env: str, tokens: dict) -> None:
    result = subprocess.run(
        ["security", "add-generic-password",
         "-s", _kc_service(env), "-a", KC_ACCOUNT,
         "-w", json.dumps(tokens), "-U"],   # -U = upsert (update if exists)
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise SaxoAuthError(f"Keychain write failed: {result.stderr.strip()}")


def _kc_delete(env: str) -> None:
    result = subprocess.run(
        ["security", "delete-generic-password",
         "-s", _kc_service(env), "-a", KC_ACCOUNT],
        capture_output=True,
    )
    # exit code 44 = not found — silently OK on logout of fresh install
    if result.returncode not in (0, 44):
        raise SaxoAuthError(
            f"Keychain delete failed: {result.stderr.strip() if result.stderr else '(no message)'}"
        )


# ---------------------------------------------------------------------------
# 1f — token state helpers
# ---------------------------------------------------------------------------


def _access_valid(tokens: dict) -> bool:
    return time.time() < tokens["expires_at"] - EXPIRY_BUFFER


def _refresh_valid(tokens: dict) -> bool:
    return time.time() < tokens["refresh_expires_at"] - EXPIRY_BUFFER


# ---------------------------------------------------------------------------
# 1g — PKCE pair generation
# ---------------------------------------------------------------------------


def _pkce_pair() -> tuple[str, str]:
    verifier  = base64.urlsafe_b64encode(os.urandom(64)).rstrip(b"=").decode()
    # verifier: 86 chars (64 bytes → base64url, no padding) — RFC 7636 compliant
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    # challenge: 43 chars (32-byte SHA-256 → base64url, no padding)
    return verifier, challenge


# ---------------------------------------------------------------------------
# 1h — token refresh
# ---------------------------------------------------------------------------


def _validate_token_response(resp, stage):
    """Raise SaxoAuthError if the token response is missing required fields."""
    if not resp:
        raise SaxoAuthError(f"Token {stage} returned empty response.")
    missing = [f for f in ("access_token", "expires_in") if f not in resp]
    if missing:
        raise SaxoAuthError(
            f"Token {stage} response missing required field(s): "
            f"{', '.join(missing)}. Full response: {resp!r}"
        )


def _request_with_retry(req, timeout=15, max_attempts=3):
    """Execute a urllib request, retrying up to max_attempts times on 5xx errors.

    Pattern matches the official Saxo JS samples (exponential backoff, 5xx only).
    4xx errors are not retried — they indicate a client-side problem.
    """
    for attempt in range(max_attempts):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read()), None
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == max_attempts - 1:
                return None, e
            wait = (2 ** attempt) * 0.1   # 100 ms, 200 ms, 400 ms
            time.sleep(wait)
    # Loop always returns in every branch — this line is never reached.


def _do_refresh(tokens: dict, config: dict) -> dict:
    env  = config["environment"]
    body = urllib.parse.urlencode({
        "grant_type":    "refresh_token",
        "refresh_token": tokens["refresh_token"],
        "client_id":     config["client_id"],
        # code_verifier is intentionally omitted: it is ephemeral (generated
        # per login session, not stored) and refresh token grants do not use
        # PKCE per RFC 6749. The official Saxo JS sample includes it only
        # because it retains it in memory from the same session.
    }).encode()
    req = urllib.request.Request(
        AUTH_URLS[env]["token"], data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    resp, err = _request_with_retry(req, timeout=15)
    if err is not None:
        body_text = err.read().decode(errors="replace")
        raise SaxoAuthError(f"Token refresh failed ({err.code}): {body_text}") from None
    _validate_token_response(resp, "refresh")

    now = int(time.time())
    new_tokens = {
        "access_token":       resp["access_token"],
        "expires_at":         now + resp["expires_in"],
        # Rolling vs absolute: if Saxo returns a new refresh_token, update it
        # and reset the refresh expiry. If absent, preserve the original.
        "refresh_token":      resp.get("refresh_token", tokens["refresh_token"]),
        "refresh_expires_at": (
            now + resp["refresh_token_expires_in"]
            if "refresh_token_expires_in" in resp
            else tokens["refresh_expires_at"]  # preserve original if absent
        ),
    }
    if "refresh_token_expires_in" not in resp:
        print(
            "WARNING: Saxo did not return refresh_token_expires_in. "
            "Preserving original expiry. Check if behaviour has changed.",
            file=sys.stderr,
        )
    return new_tokens


# ---------------------------------------------------------------------------
# 1i — PKCE flow + local HTTP callback server
# ---------------------------------------------------------------------------


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        code   = params.get("code",  [None])[0]
        state  = params.get("state", [None])[0]
        error  = params.get("error", [None])[0]

        if error:
            self.server._auth_error = error
            body = f"Authentication failed: {error}".encode()
        elif state != self.server._expected_state:
            self.server._auth_error = "state mismatch"
            body = b"Authentication failed: state mismatch."
        else:
            self.server._auth_code = code
            body = "Authentication successful \u2014 you can close this tab.".encode()

        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        # Daemon thread: handler returns → serve_forever unblocks → shutdown completes
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def log_message(self, *args):
        pass    # suppress access log noise


def _run_pkce_flow(config: dict) -> dict:
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)
    env   = config["environment"]

    # Port: try configured port, fall back to OS-assigned
    # Saxo allows any port to be appended to the registered (port-less) URI at runtime
    try:
        server = HTTPServer(("localhost", config["callback_port"]), _CallbackHandler)
    except OSError:
        server = HTTPServer(("localhost", 0), _CallbackHandler)
    port = server.server_address[1]

    # Insert the actual port into the registered redirect_uri
    # e.g. "http://localhost/saxo-callback" → "http://localhost:53682/saxo-callback"
    parsed      = urllib.parse.urlparse(config["redirect_uri"])
    runtime_uri = urllib.parse.urlunparse(
        parsed._replace(netloc=f"{parsed.hostname}:{port}")
    )

    auth_url = AUTH_URLS[env]["authorize"] + "?" + urllib.parse.urlencode({
        "response_type":         "code",
        "client_id":             config["client_id"],
        "state":                 state,
        "redirect_uri":          runtime_uri,
        "code_challenge":        challenge,
        "code_challenge_method": "S256",
    })

    server._expected_state = state
    server._auth_code      = None
    server._auth_error     = None

    print(f"Opening browser for Saxo login ({env})...")
    webbrowser.open(auth_url)

    try:
        server.serve_forever()    # blocks until handler calls server.shutdown()
    except KeyboardInterrupt:
        raise SaxoAuthError("Login cancelled")

    if server._auth_error:
        raise SaxoAuthError(f"Auth callback error: {server._auth_error}")

    code = server._auth_code

    # Exchange code for tokens
    body = urllib.parse.urlencode({
        "grant_type":    "authorization_code",
        "client_id":     config["client_id"],
        "code":          code,
        "redirect_uri":  runtime_uri,
        "code_verifier": verifier,
    }).encode()
    req = urllib.request.Request(
        AUTH_URLS[env]["token"], data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    resp, err = _request_with_retry(req, timeout=15)
    if err is not None:
        body_text = err.read().decode(errors="replace")
        raise SaxoAuthError(f"Token exchange failed ({err.code}): {body_text}") from None
    _validate_token_response(resp, "exchange")

    now = int(time.time())
    if "refresh_token_expires_in" not in resp:
        print(
            "WARNING: Saxo did not return refresh_token_expires_in. Defaulting to 2400s.",
            file=sys.stderr,
        )
    return {
        "access_token":       resp["access_token"],
        "refresh_token":      resp["refresh_token"],
        "expires_at":         now + resp["expires_in"],
        "refresh_expires_at": now + resp.get("refresh_token_expires_in", 2400),
    }


# ---------------------------------------------------------------------------
# 1j — public API
# ---------------------------------------------------------------------------


def get_valid_token(config: dict | None = None) -> str:
    """Return a valid access token, refreshing if necessary.

    Raises SaxoLoginRequired if no valid session exists (never calls sys.exit).
    """
    if config is None:
        config = load_config()
    env    = config["environment"]
    tokens = _kc_read(env)

    if tokens is not None and _access_valid(tokens):
        return tokens["access_token"]

    if tokens is not None and _refresh_valid(tokens):
        tokens = _do_refresh(tokens, config)
        _kc_write(env, tokens)
        return tokens["access_token"]

    raise SaxoLoginRequired(
        f"Saxo session expired ({env}). Run: python saxo_auth.py login"
    )


# ---------------------------------------------------------------------------
# 1j2 — API schema check (L11.1 compliance)
# ---------------------------------------------------------------------------

# Fields that must be present in a /ref/v1/instruments response item.
# If Saxo removes or renames these, the plugin will break — detect early.
_API_CHECK_PATH = pathlib.Path.home() / ".config" / "saxo" / "api-check.json"
_API_EXPECTED_FIELDS = {"Identifier", "AssetType", "Symbol", "ExchangeId", "Description"}
_BASE_URLS = {
    "sim":  "https://gateway.saxobank.com/sim/openapi",
    "live": "https://gateway.saxobank.com/openapi",
}


def check_api_schema(token, env):
    """
    Probe /ref/v1/instruments with a known query and verify expected fields exist.
    Writes result to ~/.config/saxo/api-check.json.
    Returns (ok: bool, message: str).
    """
    base = _BASE_URLS.get(env, _BASE_URLS["sim"])
    url  = (f"{base}/ref/v1/instruments?"
            "Keywords=ASML&AssetTypes=Stock&%24top=1")
    req  = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
    except Exception as e:
        msg = f"API check failed — could not reach /ref/v1/instruments: {e}"
        _write_api_check(env, ok=False, message=msg)
        return False, msg

    ok, msg = _check_schema_fields(data.get("Data", []))
    _write_api_check(env, ok=ok, message=msg)
    return ok, msg


def _check_schema_fields(items):
    """Pure validation: check that expected fields are present in the response.

    Extracted so it can be unit-tested without a live API call.
    Returns (ok: bool, message: str).
    """
    if not items:
        return False, "API check warning — /ref/v1/instruments returned empty Data for ASML"
    missing = _API_EXPECTED_FIELDS - set(items[0].keys())
    if missing:
        return False, (
            f"API schema change detected — expected fields missing: "
            f"{', '.join(sorted(missing))}. Plugin may need updating."
        )
    return True, "API responding normally — schema as expected."


def _write_api_check(env, ok, message):
    result = {"env": env, "ok": ok, "message": message,
              "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    try:
        _API_CHECK_PATH.parent.mkdir(parents=True, exist_ok=True)
        _API_CHECK_PATH.write_text(json.dumps(result, indent=2))
    except OSError as e:
        import sys as _sys
        print(f"WARNING: could not write {_API_CHECK_PATH}: {e}", file=_sys.stderr)


def _load_api_check():
    try:
        return json.loads(_API_CHECK_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# 1k — _cmd_status (stub — finalize after rolling/absolute measured at step 6)
# ---------------------------------------------------------------------------


def _cmd_status(config, env):
    tokens = _kc_read(env)
    if tokens is None:
        print(f"Not logged in ({env}). Run: python saxo_auth.py login")
        return
    now          = time.time()
    access_left  = max(0, tokens["expires_at"] - now)
    refresh_left = max(0, tokens["refresh_expires_at"] - now)

    def fmt(secs):
        m, s = int(secs // 60), int(secs % 60)
        return f"{m}m {s:02d}s"

    print(f"Environment  : {env}")
    if _access_valid(tokens):
        print(f"Access token : valid — expires in {fmt(access_left)}")
    else:
        print(f"Access token : EXPIRED")
    if _refresh_valid(tokens):
        print(f"Refresh token: valid — expires in {fmt(refresh_left)} "
              f"(rolling: resets on each use)")
    else:
        print(f"Refresh token: EXPIRED — run: python saxo_auth.py login")

    # L11.1 — show last API schema check result
    last = _load_api_check()
    if last:
        status_icon = "✓" if last.get("ok") else "✗"
        print(f"API check    : {status_icon} {last.get('message', '')} "
              f"(last checked: {last.get('checked_at', 'unknown')})")
    else:
        print("API check    : not yet run — use: python saxo_auth.py check-api")


# ---------------------------------------------------------------------------
# 1k — CLI entry point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Saxo OpenAPI auth manager")
    sub    = parser.add_subparsers(dest="command")

    login_p = sub.add_parser("login",     help="Authenticate via browser (PKCE)")
    login_p.add_argument("--force", action="store_true",
                         help="Re-authenticate even if a valid token exists")
    sub.add_parser("refresh",   help="Force token refresh now")
    sub.add_parser("status",    help="Show token validity, expiry, and API check result")
    sub.add_parser("logout",    help="Delete stored tokens from Keychain")
    token_p = sub.add_parser("token", help="Print current access token (debug)")
    token_p.add_argument("--full", action="store_true",
                         help="Print the full token instead of a masked preview")
    sub.add_parser("check-api", help="Probe Saxo API schema and record result (L11.1)")

    args   = parser.parse_args()
    config = load_config()
    env    = config["environment"]

    if args.command == "login":
        if not args.force:
            try:
                get_valid_token(config)
                print(f"Already logged in ({env}). Use --force to re-authenticate.")
                return
            except (SaxoLoginRequired, SaxoAuthError):
                pass
        try:
            tokens = _run_pkce_flow(config)
        except SaxoAuthError as e:
            sys.exit(f"[saxo] {e}")
        _kc_write(env, tokens)
        print(f"Logged in ({env}). Access token valid for ~20 minutes.")

    elif args.command == "refresh":
        tokens = _kc_read(env)
        if tokens is None:
            sys.exit("[saxo] No stored tokens. Run: python saxo_auth.py login")
        if not _refresh_valid(tokens):
            sys.exit("[saxo] Refresh token expired. Run: python saxo_auth.py login")
        try:
            tokens = _do_refresh(tokens, config)
        except SaxoAuthError as e:
            sys.exit(f"[saxo] {e}")
        _kc_write(env, tokens)
        print("Token refreshed.")

    elif args.command == "status":
        _cmd_status(config, env)

    elif args.command == "logout":
        try:
            _kc_delete(env)
        except SaxoAuthError as e:
            sys.exit(f"[saxo] {e}")
        print(f"Tokens deleted ({env}).")

    elif args.command == "token":
        try:
            tok = get_valid_token(config)
        except SaxoLoginRequired as e:
            sys.exit(f"[saxo] {e}")
        if getattr(args, "full", False):
            print("WARNING: Full token printed — clear terminal after use.", file=sys.stderr)
            print(tok)
        else:
            # Show only a safe preview to avoid terminal-history leakage
            preview = f"{tok[:8]}...{tok[-8:]}" if len(tok) > 20 else "***"
            print(f"{preview}  (use --full to print complete token)")

    elif args.command == "check-api":
        try:
            token = get_valid_token(config)
        except SaxoLoginRequired as e:
            sys.exit(f"[saxo] {e}")
        ok, msg = check_api_schema(token, env)
        print(f"{'✓' if ok else '✗'} {msg}")
        if not ok:
            sys.exit(1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
