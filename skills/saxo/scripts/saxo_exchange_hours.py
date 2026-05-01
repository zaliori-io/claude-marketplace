#!/usr/bin/env python3
"""
Saxo exchange hours cache.

Fetches trading session data from /ref/v1/exchanges (all exchanges in one call)
and caches it to ~/.config/saxo/exchange-hours.json with a 12-hour TTL.
Sessions are returned as absolute UTC timestamps, so no timezone conversion
is needed — just compare datetime.utcnow() against the session windows.

Usage as CLI:
    python saxo_exchange_hours.py [AMS|FSE|NASDAQ|...] [sim|live]  # show status
    python saxo_exchange_hours.py --refresh [sim|live]              # force refresh

Usage as library:
    from saxo_exchange_hours import get_market_status
    status = get_market_status("AMS", token, config)
    # {"exchange_id", "name", "state", "label", "is_open", "session_ends"}
"""
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from saxo_auth import get_valid_token, load_config, SaxoLoginRequired, SaxoAuthError
from saxo_common import BASE_URLS, warn_rate_limits as _warn_rate_limits, validate_env, raise_for_auth as _raise_for_auth

CACHE_PATH = pathlib.Path.home() / ".config" / "saxo" / "exchange-hours.json"
CACHE_TTL_HOURS = 12  # sessions span 2-3 days; refresh twice daily

# States considered "open for regular trading"
OPEN_STATES = {
    "AutomatedTrading",
    "CallAuctionTrading",
    "TradingAtLast",
    "OpeningAuction",
    "ClosingAuction",
}
# States considered "near open" (exchange active but not full regular hours)
EXTENDED_STATES = {
    "PreMarket",
    "PreTrading",
    "PostMarket",
    "AfterHoursTrading",
}
# Explicit mapping → canonical label (avoids brittle string transforms)
_EXTENDED_LABEL = {
    "PreMarket":         "pre-market",
    "PreTrading":        "pre-market",
    "PostMarket":        "post-market",
    "AfterHoursTrading": "post-market",
}


def _fetch_all_exchanges(token, base):
    """Fetch all exchange session data from Saxo. Returns raw Data list."""
    # Note: ExchangeId= filter is silently ignored by Saxo (gotcha #15) —
    # the endpoint always returns all exchanges. We fetch everything and
    # index by ExchangeId in the cache.
    url = f"{base}/ref/v1/exchanges"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            _warn_rate_limits(r.headers)
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        _raise_for_auth(e)
        correlation = e.headers.get("X-Correlation", "n/a")
        body = e.read().decode(errors="replace")
        raise SaxoAuthError(
            f"Exchange hours fetch failed ({e.code}) | X-Correlation: {correlation} | {body}"
        ) from None
    except urllib.error.URLError as e:
        raise SaxoAuthError(
            f"Network error reaching Saxo API: {e.reason}"
        ) from None
    return data.get("Data", [])


def _build_cache(raw_exchanges):
    """Index raw exchange list by ExchangeId, keeping only sessions."""
    index = {}
    for ex in raw_exchanges:
        eid = ex.get("ExchangeId")
        if not eid:
            continue
        sessions = []
        for s in ex.get("ExchangeSessions", []):
            sessions.append({
                "start": s["StartTime"],
                "end":   s["EndTime"],
                "state": s["State"],
            })
        index[eid] = {
            "name":     ex.get("Name", eid),
            "sessions": sessions,
        }
    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "exchanges":  index,
    }


def _load_cache():
    """Load cache from disk. Returns None if missing or stale."""
    if not CACHE_PATH.exists():
        return None
    try:
        with open(CACHE_PATH) as f:
            cache = json.load(f)
        fetched = datetime.fromisoformat(cache.get("fetched_at", "2000-01-01T00:00:00+00:00"))
    except (json.JSONDecodeError, OSError, ValueError):
        return None
    age_hours = (datetime.now(timezone.utc) - fetched).total_seconds() / 3600
    if age_hours > CACHE_TTL_HOURS:
        return None
    return cache


def _save_cache(cache):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)


def refresh_cache(token, base):
    """Fetch fresh data from Saxo and write cache. Returns cache dict."""
    raw = _fetch_all_exchanges(token, base)
    cache = _build_cache(raw)
    _save_cache(cache)
    return cache


def _get_cache(token, base):
    """Return cache, refreshing if stale."""
    cache = _load_cache()
    if cache is None:
        cache = refresh_cache(token, base)
    return cache


def _parse_utc(ts):
    """Parse a Saxo UTC timestamp string to a timezone-aware datetime."""
    # Saxo format: "2026-04-09T13:30:00.000000Z"
    ts = ts.rstrip("Z").split(".")[0]  # strip microseconds and Z
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)


def get_market_status(exchange_id, token, config):
    """
    Return the current market status for an exchange.

    Returns a dict:
        exchange_id  : str   — the exchange code (e.g. "AMS")
        name         : str   — human-readable name
        state        : str   — raw Saxo state (e.g. "AutomatedTrading", "Closed")
        label        : str   — "open" | "closed" | "pre-market" | "post-market" | "unknown"
        is_open      : bool  — True if regular trading is active
        session_ends : str   — UTC ISO time when current session ends (or "")
    """
    env  = config.get("environment", "sim")
    base = BASE_URLS.get(env, BASE_URLS["sim"])
    cache = _get_cache(token, base)
    exchanges = cache.get("exchanges", {})

    if exchange_id not in exchanges:
        return {
            "exchange_id":  exchange_id,
            "name":         exchange_id,
            "state":        "Unknown",
            "label":        "unknown",
            "is_open":      False,
            "session_ends": "",
        }

    ex      = exchanges[exchange_id]
    now_utc = datetime.now(timezone.utc)

    current_state = "Closed"
    session_ends  = ""
    for session in ex["sessions"]:
        start = _parse_utc(session["start"])
        end   = _parse_utc(session["end"])
        if start <= now_utc < end:
            current_state = session["state"]
            session_ends  = end.strftime("%H:%M UTC")
            break

    if current_state in OPEN_STATES:
        label   = "open"
        is_open = True
    elif current_state in EXTENDED_STATES:
        label   = _EXTENDED_LABEL.get(current_state, "pre-market")
        is_open = False
    else:
        label   = "closed"
        is_open = False

    return {
        "exchange_id":  exchange_id,
        "name":         ex["name"],
        "state":        current_state,
        "label":        label,
        "is_open":      is_open,
        "session_ends": session_ends,
    }


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force_refresh = "--refresh" in sys.argv

    env_arg      = args[-1] if args and args[-1] in ("sim", "live") else None
    exchange_ids = [a for a in args if a not in ("sim", "live")]
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

    if force_refresh:
        print(f"Refreshing exchange hours cache ({env})...")
        cache = refresh_cache(token, base)
        print(f"Cached {len(cache['exchanges'])} exchanges → {CACHE_PATH}")
        return

    if not exchange_ids:
        # Default: show status for the preference-list exchanges
        exchange_ids = [
            "AMS", "PAR", "FSE", "MIL", "LSE_SETS",
            "SWX", "TSE", "NASDAQ", "NYSE",
        ]

    print(f"\nExchange market status ({env}, UTC {datetime.now(timezone.utc).strftime('%H:%M')})\n")
    print(f"{'Exchange':<12} {'Name':<36} {'State':<22} {'Label':<12} {'Ends'}")
    print("-" * 100)
    for eid in exchange_ids:
        s = get_market_status(eid, token, config)
        flag = "●" if s["is_open"] else "○"
        print(f"{flag} {s['exchange_id']:<10} {s['name']:<36} {s['state']:<22} {s['label']:<12} {s['session_ends']}")


if __name__ == "__main__":
    main()
