#!/usr/bin/env python3
"""
Saxo live price lookup.
Usage: python saxo_price.py <SYMBOL_OR_ISIN> [sim|live]
"""
import json
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from saxo_auth import get_valid_token, load_config, SaxoLoginRequired
from saxo_common import BASE_URLS, warn_rate_limits as _warn_rate_limits, validate_env, to_decimal, raise_for_auth as _raise_for_auth
try:
    from saxo_exchange_hours import get_market_status as _get_market_status
    _EXCHANGE_HOURS_AVAILABLE = True
except ImportError:
    _EXCHANGE_HOURS_AVAILABLE = False
try:
    from saxo_positions import get_holdings_map as _get_holdings_map
    _HOLDINGS_AVAILABLE = True
except ImportError:
    _HOLDINGS_AVAILABLE = False
try:
    from saxo_instrument import get_siblings as _get_siblings
    _SIBLINGS_AVAILABLE = True
except ImportError:
    _SIBLINGS_AVAILABLE = False

# Saxo returns short exchange codes (NOT MIC). These are the actual values
# the API uses, ordered by routing preference for an EU-based account.
EXCHANGE_PREF = [
    "AMS",       # Euronext Amsterdam
    "PAR",       # Euronext Paris
    "FSE",       # Frankfurt / XETRA stocks
    "XETR_ETF",  # XETRA ETF segment
    "MIL",       # Borsa Italiana / Milan
    "MIL_ETF",
    "TSE",       # Toronto Stock Exchange
    "LSE_SETS",  # London Stock Exchange (stocks)
    "LSE_ETF",
    "SWX",       # SIX Swiss Exchange
    "SWX_ETF",
    "NASDAQ",
    "NYSE",
    "NYSE_ARCA",
    "SGX-ST",    # Singapore Exchange (Saxo code is SGX-ST, not SGX)
    "OOTC",      # OTC pink sheets — last resort
]

def _get(base, path, params, token):
    url = f"{base}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            _warn_rate_limits(r.headers)
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        _raise_for_auth(e)
        correlation = e.headers.get("X-Correlation", "n/a")
        body = e.read().decode(errors="replace")
        raise urllib.error.HTTPError(
            e.url, e.code,
            f"{e.reason} | X-Correlation: {correlation} | {body}",
            e.headers, None,
        ) from None
    except urllib.error.URLError as e:
        from saxo_auth import SaxoAuthError as _SAE
        raise _SAE(f"Network error reaching Saxo API: {e.reason}") from None

def _find_in_holdings(query, token, config, base):
    """
    Check if query matches a held position.
    Matching: all words of the query must appear in the instrument description.
    Returns (uic, asset_type, exchange_id) or (None, None, None).
    """
    if not _HOLDINGS_AVAILABLE:
        return None, None, None
    holdings = _get_holdings_map(token, config)
    if not holdings:
        return None, None, None
    words = query.lower().split()
    for desc_key, info in holdings.items():
        if all(w in desc_key for w in words):
            uic        = info["uic"]
            asset_type = info["asset_type"]
            # Resolve exchange_id via direct UIC lookup
            d          = _get(base, "/ref/v1/instruments",
                               {"Uics": str(uic), "AssetTypes": asset_type}, token)
            data       = d.get("Data", [])
            exchange_id = data[0].get("ExchangeId") if data else None
            return uic, asset_type, exchange_id
    return None, None, None


def find_instrument(token, query, base, config=None):
    """Resolve query to (uic, asset_type, exchange_id). Returns (None, None, None) if not found."""
    # Check holdings first — if the user holds this instrument, use the exact UIC
    # they hold rather than guessing via the exchange preference list.
    if config:
        uic, asset_type, exchange_id = _find_in_holdings(query, token, config, base)
        if uic:
            return uic, asset_type, exchange_id

    # If the query is a plain integer, treat it as a UIC and fetch directly.
    # Keywords= on a numeric string matches unrelated instruments (e.g. "211"
    # returns Best Pacific International instead of the intended UIC).
    if query.isdigit():
        d = _get(base, "/ref/v1/instruments",
                 {"Uics": query, "AssetTypes": "Stock,Etf,Etn,Etc,Bond,Fund"},
                 token)
        data = d.get("Data", [])
        if data:
            inst = data[0]
            return inst.get("Identifier"), inst.get("AssetType", "Stock"), inst.get("ExchangeId")
        return None, None, None

    # Saxo's documented `Isin=` parameter is silently ignored — it returns
    # unfiltered top-100. `Keywords=` works for ISIN, symbol, AND name.
    d = _get(base, "/ref/v1/instruments",
             {"Keywords": query, "AssetTypes": "Stock,Etf,Etn,Etc", "$top": 20},
             token)
    data = d.get("Data", [])
    if not data:
        # R4/V2: retry without AssetTypes filter to catch unknown/new asset types
        d2 = _get(base, "/ref/v1/instruments",
                  {"Keywords": query, "$top": 5}, token)
        data = d2.get("Data", [])
        if data:
            discovered = data[0].get("AssetType", "unknown")
            print(
                f"Note: '{query}' not found in standard asset types. "
                f"Found as AssetType={discovered}.",
                file=sys.stderr,
            )
        else:
            return None, None, None
    # Sort by exchange preference
    def rank(inst):
        exch = inst.get("ExchangeId", "")
        try:
            return EXCHANGE_PREF.index(exch)
        except ValueError:
            return 99
    data.sort(key=rank)
    best = data[0]
    return best.get("Identifier"), best.get("AssetType", "Stock"), best.get("ExchangeId")

def get_price(token, uic, asset_type, base):
    d = _get(base, "/trade/v1/infoprices",
             {"Uic": uic, "AssetType": asset_type,
              "FieldGroups": "Quote,DisplayAndFormat,PriceInfo,PriceInfoDetails,InstrumentPriceDetails"},
             token)
    quote   = d.get("Quote", {})
    fmt     = d.get("DisplayAndFormat", {})
    details = d.get("PriceInfoDetails", {})
    inst    = d.get("InstrumentPriceDetails", {})

    dec = fmt.get("Decimals", 2)

    mid = to_decimal(quote.get("Mid"), dec)
    ask = to_decimal(quote.get("Ask"), dec)
    bid = to_decimal(quote.get("Bid"), dec)
    price  = mid or ask or bid
    source = "Mid" if mid else ("Ask" if ask else ("Bid" if bid else None))

    bid_status = quote.get("PriceTypeBid")
    ask_status = quote.get("PriceTypeAsk")
    no_access  = bid_status == "NoAccess" or ask_status == "NoAccess"

    # When live quote is unavailable (market closed), fall back to last traded
    # and previous close — both are always populated in PriceInfoDetails.
    last_traded = to_decimal(details.get("LastTraded"), dec)
    last_close  = to_decimal(details.get("LastClose"),  dec)
    fallback        = last_traded or last_close
    fallback_source = "LastTraded" if last_traded else ("LastClose" if last_close else None)

    return {
        "price":           price,
        "source":          source,
        "bid":             bid,
        "ask":             ask,
        "bid_status":      bid_status,
        "ask_status":      ask_status,
        "no_access":       no_access,
        "fallback":        fallback,
        "fallback_source": fallback_source,
        "last_close":      last_close,
        "last_traded":     last_traded,
        "day_open":        to_decimal(details.get("Open"),               dec),
        "day_high":        to_decimal(d.get("PriceInfo", {}).get("High"), dec),
        "day_low":         to_decimal(d.get("PriceInfo", {}).get("Low"),  dec),
        "volume":          details.get("Volume"),
        "is_market_open":  inst.get("IsMarketOpen"),
        "delayed_mins":    quote.get("DelayedByMinutes", 0),
        "currency":        fmt.get("Currency", ""),
        "name":            fmt.get("Description", ""),
        "decimals":        dec,
    }

MAX_FALLBACK_ATTEMPTS = 3


def find_live_fallback(token, uic, asset_type, exchange_id, base, config):
    """Try sibling listings when the primary exchange returns NoAccess.

    Looks for a sibling listing (same GroupId) on an open exchange.
    Prefers fully-open markets over extended-hours sessions. Returns a dict
    with 'exchange_id', 'asset_type', 'currency', and 'price_result' keys,
    or None if no live price was found on any sibling.
    """
    if not _SIBLINGS_AVAILABLE or not _EXCHANGE_HOURS_AVAILABLE:
        return None

    try:
        siblings = _get_siblings(token, uic, asset_type, base)
    except Exception:
        return None

    if not siblings:
        return None

    open_siblings = []
    extended_siblings = []
    for sib in siblings:
        sid = sib["exchange_id"]
        if not sid:
            continue
        try:
            mkt = _get_market_status(sid, token, config)
            if mkt["is_open"]:
                open_siblings.append(sib)
            elif mkt["label"] in ("pre-market", "post-market"):
                extended_siblings.append(sib)
        except Exception:
            continue

    def rank(sib):
        try:
            return EXCHANGE_PREF.index(sib["exchange_id"])
        except ValueError:
            return 99

    candidates = sorted(open_siblings, key=rank) or sorted(extended_siblings, key=rank)
    if not candidates:
        return None

    for sib in candidates[:MAX_FALLBACK_ATTEMPTS]:
        try:
            result = get_price(token, sib["uic"], sib["asset_type"], base)
            if not result["no_access"] and result["price"] is not None:
                return {
                    "exchange_id":  sib["exchange_id"],
                    "asset_type":   sib["asset_type"],
                    "currency":     result["currency"],
                    "price_result": result,
                }
        except Exception:
            continue

    return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python saxo_price.py <SYMBOL_OR_ISIN> [sim|live]")
        sys.exit(1)

    query   = sys.argv[1]
    env_arg = sys.argv[2] if len(sys.argv) > 2 else None
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

    print(f"Looking up '{query}' on Saxo ({env})...")

    uic, asset_type, exchange_id = find_instrument(token, query, base, config)
    if not uic:
        print(f"ERROR: Instrument '{query}' not found.")
        sys.exit(1)

    print(f"Found: UIC={uic}, AssetType={asset_type}")

    # Show exchange market status from cache before the price API call,
    # so Claude knows upfront whether to expect live or fallback data.
    if _EXCHANGE_HOURS_AVAILABLE and exchange_id:
        try:
            mkt = _get_market_status(exchange_id, token, config)
            label = mkt["label"]
            name  = mkt["name"]
            ends  = f", closes {mkt['session_ends']}" if mkt["is_open"] and mkt["session_ends"] else ""
            opens = f", opens {mkt['session_ends']}" if not mkt["is_open"] and mkt["session_ends"] else ""
            state_str = f"[{label}{ends}{opens}]"
            print(f"Exchange : {exchange_id} — {name}  {state_str}")
        except Exception:
            pass  # cache miss or stale — price call will still work

    result = get_price(token, uic, asset_type, base)

    dec = result["decimals"]
    fmt = f"{{:.{dec}f}}"
    ccy = result["currency"]

    print(f"\n{result['name']}")

    market_state = (
        "open" if result["is_market_open"] else
        "closed" if result["is_market_open"] is False else
        "unknown"
    )
    delay = result["delayed_mins"]

    if result["no_access"]:
        # No live quote — show last traded / previous close instead
        fb = result["fallback"]
        if fb:
            label = result["fallback_source"]
            print(f"  Price : {fmt.format(fb)} {ccy} ({label})  [market {market_state}]")
            if result["last_close"] and label != "LastClose":
                print(f"  Prev close: {fmt.format(result['last_close'])} {ccy}")
        else:
            print(f"  Price : NA  ({result['bid_status']}/{result['ask_status']})  [market {market_state}]")

        if market_state == "closed":
            print("  Note  : Market is closed — showing last traded / previous close.")
        else:
            print("  Note  : NoAccess — market may be closed or token lacks entitlements.")
            print("          Try again during exchange trading hours before switching to a live token.")

        # Cross-venue fallback: try a sibling listing on an open exchange
        fallback_venue = find_live_fallback(token, uic, asset_type, exchange_id, base, config)
        if fallback_venue:
            fr   = fallback_venue["price_result"]
            f_dec = fr["decimals"]
            f_fmt = f"{{:.{f_dec}f}}"
            f_price = fr["price"]
            f_ccy   = fr["currency"]
            delay_tag = f"  [{fr['delayed_mins']}m delayed]" if fr["delayed_mins"] else ""
            ccy_note  = f"  (different currency from primary)" if f_ccy != ccy else ""
            print(f"\n  Live via {fallback_venue['exchange_id']}: "
                  f"{f_fmt.format(f_price)} {f_ccy} ({fr['source']}){delay_tag}{ccy_note}")
            if fr["bid"] and fr["ask"]:
                spread = fr["ask"] - fr["bid"]
                print(f"  Bid : {f_fmt.format(fr['bid'])}")
                print(f"  Ask : {f_fmt.format(fr['ask'])}")
    else:
        p = result["price"]
        if p is None:
            print(f"  Price : N/A  [market {market_state}]")
            print("  Note  : No price data returned — instrument may be inactive or delisted on this venue.")
            sys.exit(0)
        delay_tag = f"  [{delay}m delayed]" if delay else ""
        print(f"  Price : {fmt.format(p)} {ccy} ({result['source']}){delay_tag}  [market {market_state}]")
        if result["bid"] and result["ask"]:
            spread = result["ask"] - result["bid"]
            print(f"  Bid   : {fmt.format(result['bid'])}")
            print(f"  Ask   : {fmt.format(result['ask'])}")
            print(f"  Spread: {spread:.4f} ({spread/p*100:.3f}%)")
        if result["last_close"]:
            print(f"  Prev close: {fmt.format(result['last_close'])} {ccy}")

if __name__ == "__main__":
    main()
