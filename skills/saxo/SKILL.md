---
name: saxo
description: >
  Look up the current live price of any instrument via the Saxo OpenAPI, OR resolve an
  instrument name / ISIN / symbol to all Saxo listings across every exchange it trades
  on. Use the PRICE capability whenever the user asks about the current price of a stock,
  ETF, or any instrument — e.g. "what's ASML trading at?", "check the gold ETF price",
  "where is Air Liquide now?", "is the copper ETF above $83?". Use the INSTRUMENT LOOKUP
  capability when the user asks "what exchanges is X traded on?", "find the Saxo UIC for
  X", "what's the ISIN of X", "does Saxo have X?", or when disambiguating listings before
  placing an order. Always prefer live data over your training knowledge when a price
  matters to the decision.
---

# Saxo Price Lookup Skill

## Purpose
Fetch live prices from the Saxo OpenAPI for any instrument the user mentions, without
requiring them to upload a broker export. Use this during any discussion where a current
price matters.

## Prerequisites
- Run `python scripts/saxo_auth.py login` once to authenticate via browser. The token
  is stored securely in macOS Keychain and auto-refreshed (rolling 60-minute window).
  A `UserPromptSubmit` hook keeps the refresh window warm whenever you talk to Claude,
  so re-login is only needed after ≥60 minutes of full inactivity, or after the
  configurable session age cap (`max_session_hours`, default 4h) — whichever comes first.
- If Claude tells you the Saxo session expired, run the `/saxo-login` slash command
  (no need to switch to a terminal).
- Python 3 (no external packages required — all scripts use stdlib only).
- A Saxo account (sim or live). Sim trial accounts serve prices **during market hours**;
  outside trading hours they return `PriceTypeBid/Ask: NoAccess`. If you get NoAccess,
  first check whether the exchange is currently open before concluding you need a live token.

## API Environment
- **Dev/sim token** → use `https://gateway.saxobank.com/sim/openapi`
- **Live token** → use `https://gateway.saxobank.com/openapi`

**Important:** Sim price availability is time-gated by market hours.
- **During market hours:** sim trial accounts return real bid/ask/mid prices (confirmed
  2026-04-09: ASML 1202.60 EUR mid on AMS during European hours).
- **Outside market hours:** sim returns `PriceTypeBid/Ask: NoAccess` on all exchanges.

Reference data (instrument resolution, exchange metadata, ISIN→UIC mapping) works on
sim at all times. Diagnostic: if instrument lookup succeeds but `infoprices` returns
`NoAccess`, first check whether the target exchange is currently open. If markets are
open and NoAccess persists, the token may lack entitlements — try a live token.

## Lookup Workflow

### Step 1 — Resolve the instrument to a UIC

Search by symbol, name, or ISIN using `/ref/v1/instruments`:

```python
import json, urllib.parse, urllib.request

def find_instrument(token, query, base_url):
    # Always use Keywords= — it accepts symbols, names, AND ISIN values.
    # The documented Isin= parameter is silently ignored by Saxo and returns
    # an unfiltered top-100 list. Verified on sim 2026-04-09.
    url = f"{base_url}/ref/v1/instruments?" + urllib.parse.urlencode({
        "Keywords": query,
        "AssetTypes": "Stock,Etf,Etn,Etc",
        "$top": 20,
    })
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    return json.loads(urllib.request.urlopen(req).read()).get("Data", [])
```

When multiple results come back (same ticker on multiple exchanges), prefer in order:
`AMS` → `PAR` → `FSE`/`XETR_ETF` → `MIL` → `LSE_SETS`/`LSE_ETF` → `SWX` → `TSE` →
`NASDAQ` → `NYSE` → `NYSE_ARCA` → `SGX-ST` → `OOTC`. Note: Singapore Exchange is `SGX-ST`
(not `SGX`) — confirmed from live API. Note these are Saxo's short codes, not MICs (no `XETRA`,
no `XAMS` — use `FSE` and `AMS`). Always prefer the exchange the user actually holds
the position on if portfolio context is known.

### Step 2 — Fetch the price

Use `/trade/v1/infoprices` with the resolved UIC and AssetType. Always request
`PriceInfoDetails` and `InstrumentPriceDetails` in addition to `Quote` — these
provide last traded and previous close regardless of market hours:

```python
import json, urllib.parse, urllib.request

def get_price(token, uic, asset_type, base_url):
    url = f"{base_url}/trade/v1/infoprices?" + urllib.parse.urlencode({
        "Uic": uic,
        "AssetType": asset_type,
        "FieldGroups": "Quote,DisplayAndFormat,PriceInfoDetails,InstrumentPriceDetails",
    })
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    data = json.loads(urllib.request.urlopen(req, timeout=10).read())
    quote   = data.get("Quote", {})
    fmt     = data.get("DisplayAndFormat", {})
    details = data.get("PriceInfoDetails", {})
    inst    = data.get("InstrumentPriceDetails", {})
    price   = quote.get("Mid") or quote.get("Ask") or quote.get("Bid")
    # When market is closed, Quote returns NoAccess — fall back to PriceInfoDetails
    fallback = details.get("LastTraded") or details.get("LastClose")
    no_access = (quote.get("PriceTypeBid") == "NoAccess" or
                 quote.get("PriceTypeAsk") == "NoAccess")
    ccy  = fmt.get("Currency", "")
    name = fmt.get("Description", "")
    is_open = inst.get("IsMarketOpen")
    return price if not no_access else fallback, ccy, name, is_open
```

**Always-available fields in `PriceInfoDetails`** (confirmed 2026-04-09):

| Field | Always available? |
|---|---|
| `Quote.Bid` / `Quote.Ask` / `Quote.Mid` | No — `NoAccess` when market closed |
| `PriceInfoDetails.LastTraded` | Yes |
| `PriceInfoDetails.LastClose` | Yes |
| `PriceInfoDetails.Open` | Yes |
| `InstrumentPriceDetails.IsMarketOpen` | Yes |
| `Quote.DelayedByMinutes` | Yes (15 on sim, 0 on live with entitlements) |

### Step 2b — Cross-venue fallback when primary exchange is closed

When `PriceTypeBid/Ask: NoAccess` is returned (primary market closed), `saxo_price.py`
automatically attempts to find a live price from a sibling listing on an open exchange:

1. Fetches all sibling listings via `get_siblings()` in `saxo_instrument.py` — uses
   `GroupId` to find every venue where the same underlying trades.
2. Checks each sibling exchange's market status using the exchange hours cache.
3. Tries fully-open markets first, extended-hours (pre/post-market) second.
4. Caps at `MAX_FALLBACK_ATTEMPTS = 3` to avoid excessive API calls.
5. Reports the result as `Live via <EXCHANGE>: <price> <CCY>`, noting when the currency
   differs from the primary listing (e.g. AMS closed → NASDAQ live in USD).

This means that when AMS is closed but NASDAQ is open, a query for "ASML" will show:
```
  Price : 1212.60 EUR (LastClose)  [market closed]
  Note  : Market is closed — showing last traded / previous close.

  Live via NASDAQ: 219.70 USD (Mid)  [15m delayed]
  Bid : 219.60
  Ask : 219.80
```

If no sibling has a live quote (all global markets are closed), the fallback returns
nothing and only the last-close from the primary listing is shown.

### Step 3 — Contextualise the price

After fetching, always relate the price to the user's position if relevant:

- Compare to cost basis → show P&L %
- Compare to any open limit/stop → show distance %
- Flag if within 3% of a limit ("your XYZ sell at $X is 1.5% away — close to filling")
- For ETFs, note NAV vs price if bid/ask spread is wide

## Holdings Context

Do **not** ask the user for their holdings — assume they are available in context via
one of these sources (in order of preference):

1. **This conversation** — the user has stated their position inline
2. **Claude persistent memory** — the user has previously taught Claude a holdings list
3. **Live Saxo account** — fall back to `saxo_positions.py` hitting `/port/v1/positions/me`

The skill is a pure price/valuation engine. It knows nothing about whose positions they
are or where they are held.

## Output Format

Keep it concise. During a trading conversation, one line is enough:

> **ASML** €1,089.50 — down 8.2% from your cost basis. No active order.

If the user is explicitly asking for a price check (not mid-conversation), add:
- Bid / Ask / Spread
- Day change % if available from the quote
- Distance to nearest limit/stop if applicable

## Error Handling

| Error | Action |
|---|---|
| 401 Unauthorized | Token expired — ask user for a fresh token from developer.saxo |
| 404 / empty Data | Instrument not found — try alternative search terms or ask user for ISIN |
| No Mid price | Use Ask or Bid, note which one was used |
| Network error | Fall back to web search for approximate price, flag it as non-live |

## Helper Scripts

Several standalone scripts are available under `scripts/`:

### `saxo_price.py` — fetch live price

```bash
python scripts/saxo_price.py <QUERY> [sim|live]
# Examples:
python scripts/saxo_price.py "ASML"
python scripts/saxo_price.py "IE00B4ND3602"
python scripts/saxo_price.py "COPX" live
```

### `saxo_instrument.py` — resolve name / ISIN / symbol to all listings

Returns every Saxo listing for an instrument across all exchanges, with UIC,
symbol, exchange name, currency, asset type, and which listing is the primary.
Useful for finding the right UIC before placing an order, or answering "what
exchanges does Saxo cover for X?".

```bash
python scripts/saxo_instrument.py <QUERY> [sim|live] [--include-bonds]
# Examples:
python scripts/saxo_instrument.py "ASML"                    # by name
python scripts/saxo_instrument.py "CA9628791027"            # by ISIN
python scripts/saxo_instrument.py "Wheaton Precious Metals" # by full name
python scripts/saxo_instrument.py "2535381"                 # by UIC → expands to all sibling listings
python scripts/saxo_instrument.py "ASML" sim --include-bonds
```

### `saxo_positions.py` — live open positions

```bash
python scripts/saxo_positions.py [sim|live]
```

Fetches all open positions from the authenticated account via
`GET /port/v1/positions/me`. Outputs raw JSON — Claude interprets and formats
for the user. Follows Saxo cursor pagination (`__next`) automatically.

### `saxo_account.py` — account info and diagnostics

```bash
python scripts/saxo_account.py [sim|live]
```

Fetches account metadata via `GET /port/v1/accounts/me`. Surfaces
`IsTrialAccount`, account currency, `ClientId`, and `AccountKey`.
Useful for diagnosing `NoAccess` price errors (trial accounts have zero
market-data entitlements). Follows cursor pagination for multi-account clients.

### `saxo_instrument.py` — sample output

```
Saxo instrument lookup: 'CA9628791027'  (ISIN)
Found 3 listing(s) across 1 instrument(s)

UIC        Symbol       Exch   CCY  Asset  P  Exchange Name              Name
-----------------------------------------------------------------------------
  → Wheaton Precious Metals Corp.  [ISIN CA9628791027]  issuer: CA
6948406    WPM:xtse     TSE    CAD  Stock  ★  Toronto Stock Exchange     Wheaton Precious Metals Corp.
2535381    SII:xetr     FSE    EUR  Stock     Deutsche Börse (XETRA)     Wheaton Precious Metals Corp.
6948408    WPM:xnys     NYSE   USD  Stock     New York Stock Exchange    Wheaton Precious Metals Corp.

★ = Primary listing (as flagged by Saxo)
```

## Identifiers Saxo Actually Exposes

Saxo returns **no** external identifiers — no ISIN, no FIGI, no CUSIP, no
SEDOL, no WKN — in any response from `/ref/v1/instruments` or the details
endpoint. The `$select=` query parameter is rejected with HTTP 400, so you
can't request them either. The only identifiers Saxo returns are:

| Field | Example | What it is | Use it for |
|---|---|---|---|
| `Identifier` (UIC) | `1636` | Saxo numeric ID, one per listing | The canonical key for every other API call (price, order, position) |
| `Symbol` | `ASML:xams`, `SII:xetr` | Exchange-qualified ticker | Human-readable, globally unique within Saxo. Note: the ticker can differ across venues (WPM on TSE/NYSE is `WPM`, on Frankfurt it's `SII`) |
| `GroupId` | `109` | Shared by all listings of one underlying | Linking sibling listings — but there is no `GroupId=` query filter (silently ignored) |
| `PrimaryListing` | `6948406` | UIC of the canonical listing | Pick the "main" venue |
| `IssuerCountry` | `CA`, `NL` | ISO-2 country of the issuing company | Disambiguation |

**Consequences:**

1. **You can search by ISIN** via `Keywords=<isin>` (`Keywords` accepts ISIN
   values as input) — but you can never retrieve an ISIN from Saxo. If the
   user supplied an ISIN in the query, echo it back; never fabricate one
   from other sources.
2. **UIC is the only stable key once resolved.** Store UICs, not tickers —
   tickers are not even consistent across venues for the same security.
3. **To find all listings of an instrument given one UIC:** call
   `/ref/v1/instruments?Uics=<uic>` to get the `Description` and `GroupId`,
   then re-search via `Keywords=<Description>` and filter to that `GroupId`.
   `saxo_instrument.py` does this automatically when you pass a numeric UIC.
4. **Do not try `GroupId=` as a filter** — it is silently ignored and
   returns an unfiltered top-50, exactly like the broken `Isin=` parameter.
5. If you need real external identifiers (ISIN/FIGI/CUSIP) for reporting or
   reconciliation, source them from OpenFIGI, the user's broker export, or
   another reference provider — Saxo OpenAPI won't give them to you.

## Instrument Lookup Workflow

When the user asks about instrument mapping (not price), follow this flow:

1. Call `scripts/saxo_instrument.py` (or replicate it inline) with the user's query —
   symbol, ISIN, or free-text name. Always pass the query via `Keywords=` on the
   `/ref/v1/instruments` endpoint; the documented `Isin=` parameter is silently
   ignored by Saxo and returns unfiltered results.
2. Call `/ref/v1/instruments/details/{Uic}/{AssetType}` for each hit to get the full
   exchange name, `PrimaryListing` UIC, and `IsTradable` flag.
3. Group results by `GroupId` — every venue of the same underlying security shares
   a single `GroupId`. The primary listing is the one whose UIC equals `PrimaryListing`.
4. Report the UIC, symbol, exchange, currency, and which listing is primary.
5. Note that Saxo's instrument endpoints do NOT return the ISIN in responses. If the
   user passed an ISIN in their query, echo it back. Otherwise, do not fabricate one.

Reference data (instrument search, exchange metadata) works on sim tokens even when
market-data (price) entitlements are missing. Use this as a diagnostic: if instrument
lookup succeeds but `infoprices` returns `NoAccess`, the token is valid but lacks
exchange subscriptions — tell the user to use a live token.
