#!/usr/bin/env python3
"""
Saxo account info.

Fetches account metadata from the authenticated Saxo account. Useful for
diagnostics: surfaces IsTrialAccount, account currency, ClientId, and
AccountId for each account key (a single client may have multiple accounts).

Usage:
    python saxo_account.py [sim|live]
"""
import json
import pathlib
import sys
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from saxo_auth import get_valid_token, load_config, SaxoLoginRequired, SaxoAuthError
from saxo_common import BASE_URLS, warn_rate_limits as _warn_rate_limits, validate_env


def get_accounts(token, base):
    """Fetch all accounts, following Saxo cursor pagination via __next."""
    headers  = {"Authorization": f"Bearer {token}"}
    url      = f"{base}/port/v1/accounts/me"
    all_data = []
    while url:
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                _warn_rate_limits(r.headers)
                page = json.loads(r.read())
        except urllib.error.HTTPError as e:
            correlation = e.headers.get("X-Correlation", "n/a")
            body = e.read().decode(errors="replace")
            raise SaxoAuthError(
                f"Account fetch failed ({e.code}): {body} | X-Correlation: {correlation}"
            ) from None
        except urllib.error.URLError as e:
            raise SaxoAuthError(
                f"Network error reaching Saxo API: {e.reason}"
            ) from None
        all_data.extend(page.get("Data", []))
        url = page.get("__next")    # None when last page
    return {"Data": all_data, "__count": len(all_data)}


def main():
    env_arg = sys.argv[1] if len(sys.argv) > 1 else None
    validate_env(env_arg)

    try:
        config = load_config()
        if env_arg:
            config["environment"] = env_arg
        token = get_valid_token(config)
        env   = config["environment"]
    except SaxoLoginRequired as e:
        sys.exit(f"[saxo] {e}")

    base = BASE_URLS.get(env, BASE_URLS["sim"])

    try:
        data = get_accounts(token, base)
    except SaxoAuthError as e:
        sys.exit(f"[saxo] {e}")

    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
