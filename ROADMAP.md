# Roadmap

Issues are tracked at https://github.com/zaliori-io/claude-marketplace/issues

---

## Released

### v1.1.0 (2026-04-10)

- Decimal arithmetic — all prices and quantities use `decimal.Decimal`, quantized to
  instrument precision via `DisplayAndFormat.Decimals`. Eliminates IEEE 754 rounding
  errors from price and P&L display.
- Keychain prefix renamed from `saxo-openapi` to `saxotrader` (breaking change:
  re-authentication required after upgrade).

### v1.0.0 (2026-04-10)

- Live price lookup — bid/ask/mid/last, spread, delay label, prev close
- Instrument resolution — symbol, ISIN, name, or UIC → UIC + all exchange listings
- PKCE authentication — browser-based login, macOS Keychain token storage, auto-refresh
- Live positions — `GET /port/v1/positions/me` with formatted table and `--raw` JSON
- Account info — `GET /port/v1/accounts/me`, useful for diagnostics
- Exchange hours cache — market open/closed/pre/post-market for all 266 Saxo exchanges
- Holdings-aware price lookup — resolves against held positions first to use the exact UIC
- Cross-venue live quote fallback — when primary exchange is closed, tries sibling listings
  (same `GroupId`) on open exchanges
- 28-test regression suite covering all scripts on sim and live
- Shared utilities module (`saxo_common.py`) — centralises `BASE_URLS`, rate-limit logic,
  `to_decimal()`
- Saxo live-app compliance — rate-limit headers parsed on every request, structured
  positions output, API schema monitoring (`check-api`), asset-type fallback

---

## v1.2 — UX and robustness

Target: next minor release. Small, self-contained fixes.

### [#1 Token expiry: clean re-auth prompt instead of raw 401](https://github.com/zaliori-io/claude-marketplace/issues/1) `High`

When the refresh token expires (>60 min idle), scripts currently surface the raw HTTP 401
response. Instead they should catch this, print a clear message (`Session expired — run:
python saxo_auth.py login`), and exit 1 cleanly.

Affects all API scripts. Fix in `saxo_common.py`'s `_get()` helper — detect 401,
check Keychain for a stale token, raise `SaxoLoginRequired` with a user-friendly message.

### [#4 Per-endpoint rate-limit minute-window checking](https://github.com/zaliori-io/claude-marketplace/issues/4) `Low-Medium`

`_warn_rate_limits()` in `saxo_common.py` currently checks only `X-RateLimit-AppDay-Remaining`.
The `/ref/v1/instruments` endpoint also has `X-RateLimit-RefDataInstrumentsMinute-Remaining`
(~60/min). Add parsing of the minute-level header alongside the day-level one.

### [#5 Input sanitisation for user-provided query strings](https://github.com/zaliori-io/claude-marketplace/issues/5) `Low`

Query strings from Claude are passed directly to `Keywords=` and `Uics=`. Sanitise:
strip shell metacharacters, enforce max length, reject null bytes. Low risk (read-only
API), but correct hygiene at system boundaries.

---

## v1.3 — Platform support

### [#2 Windows token storage (Credential Manager)](https://github.com/zaliori-io/claude-marketplace/issues/2) `Medium`

Replace the `security` CLI calls in `saxo_auth.py` with Windows Credential Manager
(`cmdkey` / `wincred` via `ctypes` or `keyring`). The `_keychain_read/write/delete`
interface in `saxo_auth.py` is the designed drop-in point — no other script needs
changing.

Prerequisites: access to a Windows machine for testing; Python 3.x on Windows.

### [#3 Linux token storage (secret-tool / libsecret)](https://github.com/zaliori-io/claude-marketplace/issues/3) `Medium`

Same as #2 but for Linux. Use `secret-tool` (gnome-keyring / libsecret) or fall back
to a `~/.config/saxo/` encrypted file if `secret-tool` is not available.

Pull requests welcome for both #2 and #3.

### Plugin install cache includes `.git/` directory `Low`

Claude Code installs plugins via `git clone` of `source.repo` at `source.sha`, so the
`.git/` directory always lands in `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`.
~50–200 KB of disk bloat per install; no runtime impact.

Not fixable from the plugin side — needs an upstream feature in Claude Code (e.g.
`--depth 1` clone, post-clone `.git` removal, or a non-git release-tarball source type
in the marketplace schema). File upstream when convenient.

---

## v2.0 — Feature expansion

These are net-new capabilities beyond the current read-only data set.

### [#6 Orders blotter — open and filled orders](https://github.com/zaliori-io/claude-marketplace/issues/6) `Feature`

New script `saxo_orders.py`. Endpoints:
- `GET /port/v1/orders/me` — open orders
- `GET /port/v1/orders/me?Status=FillOrKilled,Filled` or the `/history/` endpoint for fills

Format: tabular output matching `saxo_positions.py` style. Add `--raw` JSON flag.
Add regression tests T28+.

Note from official samples: `/port/v1/netpositions` with
`FieldGroups=NetPositionBase,NetPositionView,DisplayAndFormat` gives cleaner
portfolio-level data than `/port/v1/positions/me` — evaluate for a v2 positions refactor
at the same time.

### [#8 FX conversion for consolidated P&L](https://github.com/zaliori-io/claude-marketplace/issues/8) `Feature`

New script `saxo_fx.py` wrapping `GET /trade/v1/infoprices?AssetTypes=FxSpot` for
major pairs. Add a `--convert-to <CCY>` flag to `saxo_positions.py` that fetches spot
rates and converts all position values to a single reporting currency.

No FX conversion in v1.x — native currencies are always correct. Conversion is
explicitly additive, never replacing the native output.

### [#9 Multi-account support](https://github.com/zaliori-io/claude-marketplace/issues/9) `Feature`

Currently assumes a single account. `GET /port/v1/accounts/me` already returns all
accounts via cursor pagination. Add an `--account <AccountKey>` filter to
`saxo_positions.py` and `saxo_orders.py`. Show account breakdown in formatted output.

---

## v3.0 — Architectural

These require significant structural changes and are long-horizon.

### [#7 Historical prices — OHLCV chart data](https://github.com/zaliori-io/claude-marketplace/issues/7) `Feature`

Endpoint: `GET /chart/v1/charts?Uic=<uic>&AssetType=<at>&Horizon=<minutes>&Count=<n>`
Returns OHLCV bars. New script `saxo_historical.py`.

Claude can summarise trends in text; it cannot render charts natively. Useful for
questions like "how has ASML performed over the last 30 days?"

Design consideration: `Horizon=1440` (daily) is the most useful for conversational use.
Intraday data is available but volume is higher — use conservatively.

### [#10 Streaming prices via WebSocket](https://github.com/zaliori-io/claude-marketplace/issues/10) `Architectural`

Saxo's streaming API uses a custom WebSocket protocol (STOMP-like, not standard).
This is architecturally incompatible with the current synchronous CLI pattern — Claude
would need to hold a persistent connection between turns.

Prerequisite: a daemon process that maintains the WebSocket and writes quotes to a
local cache file that `saxo_price.py` reads. Significant complexity; defer until the
synchronous approach is a proven bottleneck.

---

## Not planned

- **Order placement / modification / cancellation** — explicitly out of scope. The plugin
  is read-only by design; this is a license compliance choice, not a technical limitation.
- **Commercial / multi-tenant deployment** — blocked by Saxo's 3rd-party non-commercial
  license. Each user must hold their own AppKey. A commercial license from Saxo would be
  required before any SaaS path.
