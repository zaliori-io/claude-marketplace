# Saxo OpenAPI — Undocumented Behaviours & Gotchas

Empirically tested against Saxo sim, 2026-04-09. All findings are real and non-obvious.

## 1. `Isin=` query parameter is silently ignored

`GET /ref/v1/instruments?Isin=CA9628791027` returns an unfiltered top-100 list as if
the parameter were not present. It does not filter, does not error, and does not warn.

**Workaround:** use `Keywords=<isin>` instead. `Keywords` accepts ISIN values as input
and filters correctly. Saxo does not echo the ISIN back in any response field — see §3.

## 2. `GroupId=` query parameter is silently ignored

Same failure mode as `Isin=`. Passing `GroupId=109` returns an unfiltered top-50 list.

**Workaround:** search via `Keywords=<Description>` and filter client-side by `GroupId`.
`saxo_instrument.py` implements this pattern in `_expand_by_group()`.

## 3. Saxo returns no external identifiers

**Officially confirmed:** Saxo's own sample code (`SaxoBank/openapi-samples-js`,
`instruments/instrument-search/demo.js`) contains this comment verbatim:
> *"You can search for an ISIN. That will work. But due to market limitations the
> ISIN won't be in the response."*

`/ref/v1/instruments` and `/ref/v1/instruments/details/{uic}/{assetType}` return:
- **No ISIN**
- **No FIGI**
- **No CUSIP**
- **No SEDOL**
- **No WKN**

The only identifiers Saxo returns:

| Field | Example | Scope |
|---|---|---|
| `Identifier` (UIC) | `1636` | Numeric, per listing — canonical key for all API calls |
| `Symbol` | `ASML:xams`, `SII:xetr` | Exchange-qualified ticker, unique within Saxo |
| `GroupId` | `109` | Shared across all listings of the same underlying |
| `PrimaryListing` | UIC of canonical listing | Per instrument group |
| `IssuerCountry` | `CA`, `NL` | ISO-2 country code |

If users need external identifiers (ISIN/FIGI/CUSIP) for reconciliation they must source
them from OpenFIGI, their broker export, or another reference provider.

## 4. `$select=` is rejected with HTTP 400

Sending `?$select=Symbol,Description` to any `/ref/` endpoint returns:

```
400 Bad Request
{"Message": "Query parameter $select is not supported!"}
```

You get the full fixed field set or nothing. Do not try to trim the response shape.

## 5. Live quotes are time-gated; last close is always available via PriceInfoDetails

**Updated finding (2026-04-09):** `Quote.Bid/Ask` returns `NoAccess` outside market
hours, but `PriceInfoDetails` always returns last traded and previous close regardless
of market state. Request these additional FieldGroups to get off-hours data:

```
FieldGroups=Quote,DisplayAndFormat,PriceInfoDetails,InstrumentPriceDetails
```

| Field | Always available? | Notes |
|---|---|---|
| `Quote.Bid` / `Quote.Ask` / `Quote.Mid` | ❌ NoAccess off-hours | Live order book |
| `PriceInfoDetails.LastTraded` | ✅ Yes | Last traded price from any session |
| `PriceInfoDetails.LastClose` | ✅ Yes | Previous session closing price |
| `PriceInfoDetails.Open` | ✅ Yes | Current session open |
| `InstrumentPriceDetails.IsMarketOpen` | ✅ Yes | Boolean — use for diagnostic messages |
| `Quote.DelayedByMinutes` | ✅ Yes | 15 on sim; 0 on live with entitlements |

`saxo_price.py` uses `PriceInfoDetails` as an automatic fallback, showing
`LastTraded` or `LastClose` with a `[market closed]` label when `NoAccess`.

**Market hours behaviour (same trial account, same day, 2026-04-09):**
- Off-hours: `Quote` → `NoAccess` on all exchanges
- During European hours: ASML on AMS returned `1198.90 EUR Mid` (15-min delayed on sim)

Reference data (instrument search, exchange metadata, UIC lookup) works on sim at all times.

## 6. Saxo uses its own short exchange codes, not MIC

`ExchangeId` in all responses uses Saxo-internal codes — see `exchange-codes.md` for
the full table. The standard MIC codes (`XAMS`, `XETR`, `XLON` etc.) are never returned
and will silently fail to match any exchange preference logic.

## 7. `Uics=` filter works reliably

Comma-separated UIC lookup via `?Uics=1636,2535381&AssetTypes=Stock` works correctly
and is the right way to batch-fetch instruments when UICs are already known.

## 8. Refresh token is rolling with a 60-minute window

Empirically measured 2026-04-09. Each successful `POST /token` with
`grant_type=refresh_token` returns a **new** `refresh_token` value and a new
`refresh_token_expires_in` of 3600 seconds (60 minutes). The Saxo documentation
states 2400 seconds — this is incorrect.

**Consequence:** as long as the user interacts at least once per 60 minutes, the
session stays alive indefinitely without a full re-login. `saxo_auth.py` handles
the rolling update automatically.

## 9. Redirect URI registration — omit the port

Register the redirect URI **without** a port: `http://localhost/saxo-callback`.

At runtime, Saxo accepts any port appended to the port-less registered URI. If you
register `http://localhost:53682/saxo-callback` and then use a different port (e.g.
OS-assigned on collision), Saxo returns:

```
invalid_request: Value of redirect_uri parameter is not registered
```

`saxo_auth.py` constructs the runtime URI from the configured (port-less) URI +
actual bound port using `urllib.parse.urlparse` / `urlunparse`.

## 10. Tickers are not stable across venues

The same underlying security can have completely different tickers on different
exchanges within Saxo. Example:

| Instrument | TSE/NYSE ticker | Frankfurt ticker |
|---|---|---|
| Wheaton Precious Metals | `WPM` | `SII` |

Always store the UIC when you need a stable key. Do not assume the user's ticker
is the same across all listings.

## 11. `Symbol` suffix uses lowercase MIC notation; `ExchangeId` uses Saxo short codes

The same response contains two parallel but incompatible exchange notations:

| Field | Example | Format |
|---|---|---|
| `Symbol` | `ASML:xams`, `ASME:xetr`, `WPM:xtse` | `<ticker>:<mic-lowercase>` |
| `ExchangeId` | `AMS`, `FSE`, `TSE` | Saxo short code (uppercase) |

The `:xams` / `:xetr` suffix in `Symbol` looks like a MIC code — but it is only
part of the display identifier and **must never be used for exchange filtering or
matching**. Always use `ExchangeId` for any preference-list logic, routing, or
comparison. Mixing the two will silently produce wrong matches.

Confirmed in smoke test output (2026-04-09):

```
ASML:xams   → ExchangeId: AMS
ASME:xetr   → ExchangeId: FSE
WPM:xtse    → ExchangeId: TSE
SII:xetr    → ExchangeId: FSE
WPM:xnys    → ExchangeId: NYSE
```

## 12. Numeric UIC passed as `Keywords=` matches unrelated instruments

`/ref/v1/instruments?Keywords=211` does not return the instrument with UIC 211.
Instead it matches any instrument whose name, symbol, or description contains "211"
— returning unrelated results (e.g. "211" resolves to Best Pacific International
Holdings Ltd, HKD, not Apple Inc.).

**Workaround:** use `Uics=211` for direct UIC lookup. `saxo_price.py` now detects
numeric-only queries and routes them via `Uics=` automatically (as `saxo_instrument.py`
already did). Never pass a raw UIC to `Keywords=`.

## 13. `DelayedByMinutes` varies per listing, not just per exchange region

The same underlying instrument can show different delay values depending on which
listing (UIC) is fetched:

| Listing | ExchangeId | DelayedByMinutes |
|---|---|---|
| AAPL:xmil (UIC 15777171) | MIL | 20 |
| AAPL:xnas (UIC 211) | NASDAQ | 15 |

Do not assume all US listings are 20 minutes or all EU listings are 15 minutes.
Always read `Quote.DelayedByMinutes` from the `infoprices` response for the
specific UIC being priced.

## 14. Live returns more listings than sim for the same instrument

`saxo_instrument.py "Wheaton Precious Metals"` returns:
- **Sim:** 3 listings (TSE★, FSE, NYSE)
- **Live:** 4 listings (TSE★, FSE, NYSE, LSE)

Live accounts have access to more exchange coverage. Reference data results from sim
should be treated as a lower bound — live may surface additional venues.
