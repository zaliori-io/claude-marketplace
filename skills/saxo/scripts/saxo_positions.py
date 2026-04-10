#!/usr/bin/env python3
"""
Saxo live positions.

Fetches all open positions from the authenticated Saxo account.

Usage:
    python saxo_positions.py [sim|live]
"""
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from saxo_auth import get_valid_token, load_config, SaxoLoginRequired, SaxoAuthError
from saxo_common import BASE_URLS, warn_rate_limits as _warn_rate_limits, validate_env, to_decimal


def get_positions(token, base):
    """Fetch all positions, following Saxo cursor pagination via __next."""
    headers  = {"Authorization": f"Bearer {token}"}
    url      = (f"{base}/port/v1/positions/me"
                "?FieldGroups=PositionBase,PositionView,DisplayAndFormat")
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
                f"Positions fetch failed ({e.code}): {body} | X-Correlation: {correlation}"
            ) from None
        except urllib.error.URLError as e:
            raise SaxoAuthError(
                f"Network error reaching Saxo API: {e.reason}"
            ) from None
        all_data.extend(page.get("Data", []))
        url = page.get("__next")    # None when last page
    return {"Data": all_data, "__count": len(all_data)}


HOLDINGS_CACHE_TTL = 300  # 5 minutes


def _holdings_cache_path(env):
    return pathlib.Path.home() / ".config" / "saxo" / f"holdings-cache.{env}.json"


def get_holdings_map(token, config):
    """
    Return a dict mapping normalised description → {"uic": int, "asset_type": str, "description": str}.

    Results are cached for 5 minutes so repeated price lookups in a session
    don't re-fetch the full positions list each time.
    Returns {} on error (positions unavailable, sim trial account, etc.).
    """
    env        = config.get("environment", "sim")
    cache_path = _holdings_cache_path(env)

    # Serve from cache if fresh
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text())
            if time.time() - cached.get("_fetched_at", 0) < HOLDINGS_CACHE_TTL:
                return cached.get("holdings", {})
        except (json.JSONDecodeError, KeyError):
            pass

    # Fetch fresh from API
    base = BASE_URLS.get(env, BASE_URLS["sim"])
    try:
        data = get_positions(token, base)
    except SaxoAuthError:
        return {}

    holdings = {}
    for pos in data.get("Data", []):
        pb          = pos.get("PositionBase", {})
        uic         = pb.get("Uic")
        asset_type  = pb.get("AssetType")
        description = pos.get("DisplayAndFormat", {}).get("Description", "")
        if uic and asset_type and description:
            holdings[description.lower()] = {
                "uic":         uic,
                "asset_type":  asset_type,
                "description": description,
            }

    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({"_fetched_at": time.time(), "holdings": holdings}))
    except OSError:
        pass

    return holdings


def format_positions(data, env):
    """Format positions as a human-readable table (L8.6 compliance).

    Fields used (all from PositionBase / PositionView / DisplayAndFormat):
      Description, Amount, OpenPrice, CurrentPrice, ProfitLossOnTrade, Currency, Decimals
    """
    from datetime import datetime, timezone
    positions = data.get("Data", [])
    count     = data.get("__count", len(positions))
    now_utc   = datetime.now(timezone.utc).strftime("%H:%M UTC")

    print(f"Open Positions — {env} — {count} position(s)  [{now_utc}]\n")

    if not positions:
        print("  (no open positions)")
        return

    # Header
    print(f"{'#':>3}  {'Instrument':<38} {'Qty':>12}  {'Open':>10}  "
          f"{'Current':>10}  {'P&L':>10}  {'P&L%':>7}  CCY")
    print("-" * 110)

    for i, pos in enumerate(positions, 1):
        pb  = pos.get("PositionBase", {})
        pv  = pos.get("PositionView", {})
        fmt = pos.get("DisplayAndFormat", {})

        name        = (fmt.get("Description") or "")[:38]
        ccy         = fmt.get("Currency", "")
        dec         = fmt.get("Decimals", 2)
        price_fmt   = f"{{:.{dec}f}}"

        qty         = pb.get("Amount")
        open_price  = to_decimal(pb.get("OpenPrice"),       dec)
        cur_price   = to_decimal(pv.get("CurrentPrice"),    dec)
        pnl         = to_decimal(pv.get("ProfitLossOnTrade"), 2)

        qty_str     = f"{qty:,.0f}"               if qty        is not None else "—"
        open_str    = price_fmt.format(open_price) if open_price is not None else "—"
        cur_str     = price_fmt.format(cur_price)  if cur_price  is not None else "—"
        pnl_str     = f"{pnl:+,.2f}"              if pnl        is not None else "—"

        if open_price and cur_price and open_price != 0:
            pct     = (cur_price - open_price) / open_price * 100
            pct_str = f"{float(pct):+.1f}%"
        else:
            pct_str = "—"

        print(f"{i:>3}.  {name:<38} {qty_str:>12}  {open_str:>10}  "
              f"{cur_str:>10}  {pnl_str:>10}  {pct_str:>7}  {ccy}")

    print()
    print("P&L = ProfitLossOnTrade (unrealised, in position currency). "
          "Open/Current prices use instrument decimal precision from Saxo.")


def main():
    args    = sys.argv[1:]
    raw_out = "--raw" in args
    args    = [a for a in args if a != "--raw"]
    env_arg = args[0] if args else None
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
        data = get_positions(token, base)
    except SaxoAuthError as e:
        sys.exit(f"[saxo] {e}")

    if raw_out:
        print(json.dumps(data, indent=2))
    else:
        format_positions(data, env)


if __name__ == "__main__":
    main()
