#!/usr/bin/env python3
"""
Saxo instrument lookup.

Resolves a symbol, ISIN, or free-text name to ALL Saxo listings for that
instrument across every exchange, showing UIC, symbol, exchange, currency,
asset type, and which listing is the primary.

Usage:
    python saxo_instrument.py <QUERY> [sim|live] [--include-bonds]

Examples:
    python saxo_instrument.py "ASML"
    python saxo_instrument.py "IE00B4ND3602"
    python saxo_instrument.py "Wheaton Precious Metals"

Notes:
    * Saxo exposes NO external identifiers (no ISIN/FIGI/CUSIP/SEDOL/WKN)
      in any response. The only identifiers it returns are:
         - UIC (Identifier)        numeric, per listing, used in every API call
         - Symbol                  exchange-qualified ticker, e.g. ASML:xams
         - GroupId                 shared across all listings of one underlying
         - PrimaryListing (UIC)    canonical listing
         - IssuerCountry           ISO-2 country code
    * `Keywords=` DOES accept ISIN values as input and filters correctly —
      so you can still look up by ISIN, you just can't get one BACK.
      (The documented `Isin=` parameter is silently ignored in practice.)
    * If the user passes a UIC (integer), we look it up via `Uics=` to get
      all listings in the same GroupId.
    * `$select=` is rejected with HTTP 400. The endpoint returns a fixed
      field set.
    * Bonds are excluded by default — pass --include-bonds to keep them.
"""
import json
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from saxo_auth import get_valid_token, load_config, SaxoLoginRequired, SaxoAuthError
from saxo_common import BASE_URLS, warn_rate_limits as _warn_rate_limits, validate_env, raise_for_auth as _raise_for_auth

ASSET_TYPES_DEFAULT = "Stock,Etf,Etn,Etc,Fund"
ASSET_TYPES_WITH_BONDS = "Stock,Etf,Etn,Etc,Fund,Bond"


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
        raise SaxoAuthError(f"Network error reaching Saxo API: {e.reason}") from None


def is_isin(q):
    return len(q) == 12 and q[:2].isalpha() and q[2:].isalnum()


def is_uic(q):
    return q.isdigit()


def search_instruments(token, query, base, include_bonds=False):
    """Return Saxo listings matching the query.

    Accepts symbol (AAPL), exchange-qualified symbol (ASML:xams), ISIN
    (CA9628791027), free-text name (Air Liquide), or a numeric UIC.
    """
    asset_types = ASSET_TYPES_WITH_BONDS if include_bonds else ASSET_TYPES_DEFAULT

    # UIC → direct lookup via Uics=, then expand to the whole GroupId
    if is_uic(query):
        r = _get(base, "/ref/v1/instruments",
                 {"Uics": query, "AssetTypes": asset_types},
                 token)
        seeds = r.get("Data", [])
        if not seeds:
            return []
        return _expand_by_group(token, base, seeds[0], asset_types)

    # Keywords= filters correctly on ISIN, symbol, and name. Isin= and
    # GroupId= are both silently ignored by Saxo so we never use them.
    r = _get(base, "/ref/v1/instruments",
             {"Keywords": query, "AssetTypes": asset_types, "$top": 100},
             token)
    data = r.get("Data", [])
    if not data:
        # R4/V2: retry without AssetTypes filter to catch unknown/new asset types
        r2 = _get(base, "/ref/v1/instruments", {"Keywords": query, "$top": 100}, token)
        data = r2.get("Data", [])
        if data:
            discovered = {d.get("AssetType", "unknown") for d in data}
            print(
                f"Note: '{query}' not found in standard asset types. "
                f"Found as: {', '.join(sorted(discovered))}.",
                file=sys.stderr,
            )
    return data


def _expand_by_group(token, base, seed, asset_types):
    """Given a single listing, find all other listings in the same GroupId.

    Saxo has no `GroupId=` filter (silently ignored). Workaround: re-search
    by the instrument's Description, then filter to the seed's GroupId.
    Falls back to the seed alone if the description search misses it.
    """
    gid = seed.get("GroupId")
    desc = seed.get("Description") or ""
    if not gid or not desc:
        return [seed]
    r = _get(base, "/ref/v1/instruments",
             {"Keywords": desc, "AssetTypes": asset_types, "$top": 100},
             token)
    matches = [d for d in r.get("Data", []) if d.get("GroupId") == gid]
    # Guarantee the seed is included even if the description search didn't
    # return its specific UIC (happens for non-primary listings with odd names)
    if not any(d.get("Identifier") == seed.get("Identifier") for d in matches):
        matches.append(seed)
    return matches


def get_siblings(token, uic, asset_type, base):
    """Return all sibling listings for a given UIC (same GroupId), excluding the UIC itself.

    Returns [] if the instrument is ungrouped (GroupId == 0 or missing), or if the
    UIC does not exist. Auth errors and rate-limit exhaustion propagate to the caller.
    """
    r = _get(base, "/ref/v1/instruments",
             {"Uics": str(uic), "AssetTypes": asset_type}, token)
    seeds = r.get("Data", [])
    if not seeds:
        return []
    seed = seeds[0]
    gid = seed.get("GroupId")
    if not gid:
        return []
    all_listings = _expand_by_group(token, base, seed, asset_type)
    return [
        {
            "uic":         l.get("Identifier"),
            "exchange_id": l.get("ExchangeId", ""),
            "asset_type":  l.get("AssetType", asset_type),
            "currency":    l.get("CurrencyCode", ""),
            "name":        l.get("Description", ""),
            "group_id":    gid,
        }
        for l in all_listings
        if l.get("Identifier") != uic
    ]


def get_details(token, uic, asset_type, base):
    """Fetch exchange metadata + primary-listing flag for one UIC.

    Returns {} on a 404 (instrument not in ref data) or a parse error —
    the enrichment step degrades gracefully. Auth errors and rate-limit
    exhaustion propagate so the caller sees the real problem.
    """
    try:
        return _get(base, f"/ref/v1/instruments/details/{uic}/{asset_type}", {}, token)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {}
        raise   # 401, 403, 429, 5xx — let the caller see these
    except (json.JSONDecodeError, KeyError):
        return {}


def enrich(token, hits, base, fetch_details=True):
    """Attach exchange name and primary-listing flag to each hit."""
    out = []
    seen = set()
    for h in hits:
        uic = h.get("Identifier")
        if uic in seen:
            continue
        seen.add(uic)
        at = h.get("AssetType", "Stock")

        exchange_name = h.get("ExchangeId", "")
        country = h.get("IssuerCountry", "")
        primary_uic = h.get("PrimaryListing")
        tradable = True

        if fetch_details:
            try:
                d = get_details(token, uic, at, base)
                ex = d.get("Exchange") or {}
                exchange_name = ex.get("Name") or exchange_name
                country = ex.get("CountryCode") or country
                primary_uic = d.get("PrimaryListing", primary_uic)
                tradable = d.get("IsTradable", True)
            except SaxoAuthError as e:
                if "rate limit" in str(e).lower():
                    print(
                        "WARNING: Rate limit reached during enrichment — "
                        "remaining listings shown without full exchange details.",
                        file=sys.stderr,
                    )
                    fetch_details = False  # degrade for remaining items
                else:
                    raise

        out.append({
            "uic":         uic,
            "symbol":      h.get("Symbol", ""),
            "name":        h.get("Description", ""),
            "exchange_id": h.get("ExchangeId", ""),
            "exchange":    exchange_name,
            "country":     country,
            "currency":    h.get("CurrencyCode", ""),
            "asset":       at,
            "group_id":    h.get("GroupId"),
            "primary_uic": primary_uic,
            "is_primary":  primary_uic == uic,
            "tradable":    tradable,
            "issuer_ctry": h.get("IssuerCountry", ""),
        })
    return out


def print_table(rows, query):
    if not rows:
        print(f"No Saxo instruments found for '{query}'.")
        return

    # Group by GroupId — all listings of the same underlying instrument
    groups = {}
    for r in rows:
        groups.setdefault(r["group_id"] or r["name"], []).append(r)

    query_is_isin = is_isin(query)
    print(f"\nSaxo instrument lookup: '{query}'"
          + (f"  (ISIN)" if query_is_isin else ""))
    print(f"Found {len(rows)} listing(s) across {len(groups)} instrument(s)\n")

    header = (f"{'UIC':<10} {'Symbol':<16} {'Exch':<6} {'CCY':<4} "
              f"{'Asset':<6} {'P':<2} {'Exchange Name':<32} {'Name'}")
    print(header)
    print("-" * 120)

    for gid, listings in groups.items():
        listings.sort(key=lambda x: (not x["is_primary"], x["exchange_id"]))
        # The instrument name
        inst_name = listings[0]["name"]
        issuer = listings[0].get("issuer_ctry", "")
        if query_is_isin:
            print(f"  → {inst_name}  [ISIN {query.upper()}]"
                  + (f"  issuer: {issuer}" if issuer else ""))
        else:
            print(f"  → {inst_name}"
                  + (f"  [issuer: {issuer}]" if issuer else ""))

        for r in listings:
            primary = "★" if r["is_primary"] else " "
            name = (r["name"] or "")[:40]
            exch_name = (r["exchange"] or "")[:32]
            print(f"{str(r['uic']):<10} {r['symbol'][:16]:<16} "
                  f"{r['exchange_id'][:6]:<6} {r['currency']:<4} "
                  f"{r['asset'][:6]:<6} {primary:<2} "
                  f"{exch_name:<32} {name}")
        print()

    # Legend
    if any(not r["is_primary"] for r in rows):
        print("★ = Primary listing (as flagged by Saxo)")


def main():
    args = sys.argv[1:]
    include_bonds = "--include-bonds" in args
    args = [a for a in args if a != "--include-bonds"]

    if not args:
        print(__doc__)
        sys.exit(1)

    query   = args[0]
    env_arg = args[1] if len(args) > 1 else None
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

    hits = search_instruments(token, query, base, include_bonds=include_bonds)
    rows = enrich(token, hits, base, fetch_details=True)
    print_table(rows, query)


if __name__ == "__main__":
    main()
