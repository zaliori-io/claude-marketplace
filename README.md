<div align="center">
  <img src="icon.svg" width="96" height="96" alt="Saxo OpenAPI Plugin icon"/>
  <h1>Saxo OpenAPI Plugin for Claude</h1>
</div>

A read-only Claude Code plugin that lets Claude fetch live instrument prices and
resolve securities from the [Saxo Bank OpenAPI](https://www.developer.saxo/openapi/learn).
Ask Claude "what's ASML trading at?" or "find the Saxo UIC for this ISIN" and it will
query live market data from your own Saxo account.

> [!WARNING]
> **Independent project — not affiliated with Saxo Bank A/S or Anthropic.**
> This is a personal MIT-licensed project. "Saxo" and "Saxo Bank" are trademarks of
> Saxo Bank A/S. "Claude" is a trademark of Anthropic, PBC. Neither company has
> endorsed, reviewed, or authorised this plugin.
>
> Market data delivered through the Saxo OpenAPI may be **delayed, inaccurate, or
> unavailable** — Saxo's own license explicitly excludes liability for data quality (§4.1).
> **Do not rely on this plugin for investment or trading decisions.**
> The author accepts no liability for financial losses or any other damages.
> **Use entirely at your own risk.** See [Security](#security) for a full account
> of what this plugin does and does not do to protect your credentials and data.

## What it does

| Capability | Example prompt |
|---|---|
| Live bid/ask/mid price | "What's the current price of Air Liquide?" |
| Instrument resolution | "What exchanges does Saxo list ASML on?" |
| ISIN → UIC lookup | "Find the Saxo UIC for IE00B4ND3602" |
| All listings for a security | "Show me all venues for Wheaton Precious Metals" |
| Exchange market status | "Is the Amsterdam exchange open right now?" |
| Portfolio positions | "What positions do I hold in my Saxo account?" |
| Account info | "Show my Saxo account details" |

**Read-only — no order placement, no account modification.**

> **License notice:** Saxo's 3rd Party Open API Non-Commercial License permits this
> plugin only for **personal use on your own Saxo account**. Each user must register
> their own app key on the Saxo developer portal — you cannot share or redistribute
> a single app key for others to use. The license explicitly states it is not intended
> for third-party applications for general usage. This plugin's architecture enforces
> this: the `client_id` in `~/.config/saxo/config.json` is always the user's own
> registered app key.

## Platform support

| Platform | Status |
|---|---|
| macOS | Supported |
| Windows | Not yet — see [Roadmap](#roadmap) |
| Linux | Not yet — see [Roadmap](#roadmap) |

Token storage uses the macOS Keychain via the built-in `security` CLI, which avoids
any third-party dependencies. Windows and Linux equivalents (Credential Manager,
`secret-tool`) follow a similar pattern — pull requests welcome.

## Prerequisites

- macOS with Python 3 (no third-party packages required)
- A [Saxo Bank](https://www.home.saxo) brokerage account (sim or live). Sim trial
  accounts serve prices during market hours; outside trading hours they return NoAccess.
- A registered app on the [Saxo developer portal](https://www.developer.saxo/openapi/appmanagement#/connectlive)
  with **Authorization Code + PKCE** grant type — no client secret required

## Setup

### 1. Register an app with Saxo

1. Go to [developer.saxo — Connect Live App](https://www.developer.saxo/openapi/appmanagement#/connectlive)
2. Create a new app:
   - **Grant type:** Authorization Code with PKCE
   - **Redirect URI:** `http://localhost/saxo-callback` (no port — this is intentional)
   - No client secret needed
3. Copy the **AppKey** — this is your `client_id`

> **Saxo live app disclaimer:** During live app registration Saxo asks you to confirm
> requirements across four areas. This plugin's compliance:
>
> **General**
>
> | Requirement | How this plugin complies |
> |---|---|
> | AppSecret / RefreshToken never sent to a public location | PKCE flow — no AppSecret exists. RefreshToken is stored exclusively in macOS Keychain, never written to disk or transmitted anywhere other than back to `live.logonvalidation.net/token`. |
> | "Monkey test" — rapid input cannot crash or hang | Scripts are CLI tools with no interactive UI. All HTTP calls have explicit timeouts (10–15 s). OAuth callback server shuts down via a daemon thread. No infinite loops. |
> | No excessive 400 errors | The only known 400 source in the Saxo ref API is `$select=` — all scripts avoid it. API calls use documented, tested parameters only. |
> | No throttling limit violations (429 / 409) | Personal interactive use only — one API call per user request, no background polling. No explicit rate-limiting layer; add one if automating heavy usage. |
>
> **Reading Data**
>
> | Requirement | How this plugin complies |
> |---|---|
> | App does not crash or hang with many positions / orders | `saxo_positions.py` and `saxo_account.py` follow Saxo cursor pagination (`__next`) and accumulate all pages before returning — no page-count assumptions. |
> | Do not assume client, account, or instrument currencies | Native currencies are reported as-is. No FX conversion is applied. A single client may have accounts in different currencies — the plugin surfaces all of them. |
> | Correctly show prices and amounts (decimal separators, decimals, tick sizes) | `saxo_price.py` reads `Decimals` from the `DisplayAndFormat` field and formats output accordingly. Claude interprets position data from raw API responses which carry their own currency and decimal metadata. |
> | Gracefully handle unexpected instruments, asset types, or positions | `saxo_positions.py` and `saxo_account.py` return the full raw API response without filtering — unknown asset types pass through to Claude. Price and instrument scripts filter by known asset types but fall back gracefully when no results match. |
> | Correctly handle fractional amounts | All quantities and prices are handled as Python floats. No integer-only assumptions anywhere. |
>
> **Trading** — Not applicable. This plugin is read-only. No order placement, modification, or cancellation is implemented or planned.
>
> **Future Changes / Versioning** — Saxo's policy states they will add new fields and new enum values to existing types without a version bump. All scripts use `.get()` with defaults for optional fields and do not crash on unknown keys. New asset type values in existing filters may cause those instruments to be silently excluded — this is a known limitation and a future robustness improvement.
>
> **Technical requirements (§8)**
>
> | Requirement | How this plugin complies |
> |---|---|
> | App must not intercept browser login or present its own login dialog (§8.2) | The PKCE flow opens Saxo's own login page in the user's browser. The local callback server receives only the auth code redirect — credentials never touch the plugin. |
> | RefreshToken must only be used in direct communication with the Saxo auth server (§8.3) | `saxo_auth.py` sends the RefreshToken exclusively to `logonvalidation.net/token`. It is never logged, stored on disk, or transmitted elsewhere. |
> | No cross-contamination of data between End Users (§8.7) | Each user registers their own AppKey and holds their own Keychain entry (`saxo-openapi-live` / `saxo-openapi-sim`). Tokens from one user's account cannot be accessed by another. |
>
> **Other license points to be aware of (§2.2, §4.1, §6.1, §7.1):**
> - **§2.2:** By registering a live app, you grant Saxo the right to mention or promote your app on their websites.
> - **§4.1 — Data accuracy:** Saxo explicitly states that information received through the Open API may be inaccurate, incomplete, and/or not up to date. Do not rely solely on this plugin for financial decisions.
> - **§6.1(b):** The license terminates automatically if you cease to be a Saxo Bank client.
> - **§7.1 — Market conditions:** Saxo may limit or close access to your app immediately and without notice during exceptional market conditions (extreme volatility, market closure, etc.). Expect the plugin to become unavailable at exactly the moments markets are most stressed.
> - **§9.3 — Sim testing obligation:** You are expected to verify your software against the sim environment before accessing live, and to continue running against sim to spot API changes early. The sim smoke test in this project satisfies the initial verification; re-running it periodically is good practice.
> - **§11.1 — API changes:** Non-breaking changes may arrive without notice. Breaking changes come with at least 30 days notice (attempted). Monitor Saxo's release notes and update the plugin promptly. You are obliged to inform end users of any changes that affect their access.
> - **§12.1 — Public announcements:** You may not make any separate public announcement about this license or its contents without Saxo's prior written consent. The compliance notes above are included for transparency about how this plugin operates — not as a public announcement of the license itself.
> - **§15 — Governing law:** This license is subject to Danish law; disputes fall under the exclusive jurisdiction of the Danish Courts.

> **Note:** The developer portal (`developer.saxo`) is a separate site from the
> trading platforms (`saxotrader.com`, `saxoinvestor.com`) that most Saxo clients
> use day-to-day. This is a genuine trust gap in the setup experience — it requires
> you to log in to an unfamiliar-looking portal with your real Saxo credentials.
> Confidence would be significantly higher if app registration were accessible from
> within the trading platform you already know and trust. Until Saxo integrates this,
> the mitigations are: (a) verify the TLS certificate shows `O=Saxo Bank A/S` before
> entering credentials (see §3 above), and (b) note that `developer.saxo` is listed
> in Saxo's official documentation and on the same certificate as `saxotrader.com`.

### 2. Configure the plugin

Copy the example config and fill in your `client_id`:

```bash
cp skills/saxo/config.example.json ~/.config/saxo/config.json
```

`~/.config/saxo/config.json` should look like this (the file at
`skills/saxo/config.example.json` is the template):

```json
{
  "environment":   "live",
  "client_id":     "YOUR_APP_KEY_HERE",
  "redirect_uri":  "http://localhost/saxo-callback",
  "callback_port": 53682
}
```

- `environment`: `"live"` for a real brokerage account, `"sim"` for the Saxo
  simulation environment (instrument resolution works on sim at all times; prices work on sim during market hours)
- `client_id`: the **AppKey** from your registered app on the developer portal
- `redirect_uri`: must match what you registered on the developer portal — **no port**
  (Saxo requires the registered URI to be port-less; the auth script appends the port
  at runtime when constructing the actual callback URL)
- `callback_port`: the local port the auth script will listen on for the OAuth callback

### 3. Authenticate

```bash
python skills/saxo/scripts/saxo_auth.py login
```

This opens your browser for the Saxo login, handles the OAuth callback locally, and
stores the token securely in macOS Keychain. Re-run any time your session expires.

**Verifying the auth domain is legitimate:**
The login page is served from `live.logonvalidation.net` (or `sim.logonvalidation.net`
for the sim environment). You can confirm this is a genuine Saxo domain before entering
credentials:

```bash
echo | openssl s_client -connect live.logonvalidation.net:443 \
  -servername live.logonvalidation.net 2>/dev/null \
  | openssl x509 -noout -subject -issuer
```

Expected output: `O=Saxo Bank A/S, C=DK` issued by DigiCert/GeoTrust. The certificate
covers the entire Saxo infrastructure (`saxotrader.com`, `saxoinvestor.com`, all
regional variants) and cannot be forged without compromising Saxo Bank's private key.
The browser padlock should show the same — click it and verify the organisation is
`Saxo Bank A/S` before logging in.

Other auth commands:

```bash
python skills/saxo/scripts/saxo_auth.py status   # check token expiry
python skills/saxo/scripts/saxo_auth.py refresh  # force a refresh now
python skills/saxo/scripts/saxo_auth.py logout   # delete stored tokens
```

### 4. Install the plugin in Claude Code

Run these two commands in your terminal:

```bash
claude plugin marketplace add zaliori-io/claude-marketplace
claude plugin install saxotrader@saxotrader
```

That's it — Claude Code pulls the plugin directly from GitHub. Steps 2 and 3 above
(config file + `saxo_auth.py login`) are still required and must be done on the same
machine; the plugin installation does not handle authentication.

Once installed, restart Claude Code (or open a new session). Your skill will be
available as `/saxo`.

## Usage

Once installed, just ask Claude naturally:

- "What's the live price of ASML?"
- "Check the bid/ask on the gold ETF IE00B4ND3602"
- "What's the Saxo UIC for Broadcom?"
- "List all exchanges Saxo covers for Wheaton Precious Metals"

Claude will call the scripts, fetch live data from your Saxo account, and respond
with prices, spreads, and instrument details.

## Token lifetime

Saxo access tokens expire after 20 minutes; refresh tokens after 60 minutes.
Refresh is **rolling** — each successful refresh resets the 60-minute window and
issues a new refresh token. As long as Claude is used at least once within any
60-minute idle window, the session auto-refreshes indefinitely. Only a hard idle
of more than 60 minutes requires re-authentication:

```bash
python skills/saxo/scripts/saxo_auth.py login
```

## Security

This plugin handles access to a live brokerage account, so security has been a
first-class design concern throughout. Below is an honest summary of what has been
done and where the boundaries of that effort lie.

**What the plugin does to protect you**

| Area | Approach |
|---|---|
| **Credentials** | Your Saxo username and password are never seen by this plugin. The PKCE flow opens Saxo's own login page in your browser; the plugin receives only a short-lived authorisation code via a local HTTP redirect. |
| **Token storage** | Access and refresh tokens are stored exclusively in the **macOS Keychain** via the built-in `security` CLI — encrypted at rest, protected by your login session. They are never written to disk in plaintext and never logged. |
| **Refresh token transmission** | The refresh token is sent only to `logonvalidation.net/token` (Saxo's own auth server). It is never forwarded to any third party or included in log output. |
| **Config file** | `~/.config/saxo/config.json` contains no secrets — only your `client_id` (an AppKey, which is semi-public by design in PKCE), the environment flag, and the redirect URI. |
| **Read-only API surface** | The plugin calls only `GET` endpoints. No order-placement, account-modification, or any write path exists in the codebase. |
| **Per-user isolation** | Each user registers their own AppKey and gets their own Keychain entry (`saxo-openapi-live` / `saxo-openapi-sim`). There is no shared credential or multi-tenant token store. |
| **Local execution** | All scripts run on your machine. No data is relayed through a cloud service, proxy, or third-party server of any kind. |
| **No telemetry** | The plugin collects and transmits nothing. No analytics, no crash reporting, no usage data. |
| **TLS** | All API calls use standard HTTPS to Saxo's endpoints. You can verify the TLS certificate is genuinely `O=Saxo Bank A/S` before logging in (see Setup §3). |

**Known limitations and best-effort boundaries**

- **Rate-limit awareness is implemented but not tested under load.** All scripts parse `X-RateLimit-AppDay-Remaining` and `X-RateLimit-RefDataInstrumentsMinute-Remaining` on every response, warn at ≤5 remaining, and raise an error at 0. For interactive single-query use this limit is never approached, but automated or high-frequency use has not been load-tested.
- **macOS Keychain dependency.** On Windows and Linux, a secure token store is not yet implemented — this is a known gap, not an oversight (see [Roadmap](#roadmap)).
- **No code signing or integrity verification.** The plugin is delivered as plain Python source from a public GitHub repository. You should review the code yourself before running it against a live brokerage account — this README links directly to all scripts in [Project structure](#project-structure).
- **Token auto-refresh window.** If your machine is idle for more than 60 minutes the refresh token expires and a full re-authentication is needed. This is a Saxo API constraint, not a plugin choice.
- **This is not a security audit.** The plugin has been built with security in mind and reviewed against Saxo's own technical requirements (§8), but it has not undergone independent penetration testing or a formal security review. Use it accordingly.

## Project structure

```
claude-saxo-openapi-plugin/
├── .claude-plugin/
│   ├── plugin.json               ← plugin manifest (name, version, skill list)
│   └── marketplace.json          ← enables /plugin marketplace add from GitHub
├── README.md
├── LICENSE
├── skills/
│   └── saxo/
│       ├── SKILL.md              ← skill instructions for Claude
│       ├── config.example.json   ← copy to ~/.config/saxo/config.json
│       ├── scripts/
│       │   ├── saxo_auth.py         ← PKCE auth + token cache (macOS Keychain)
│       │   ├── saxo_common.py       ← shared constants + rate-limit helper
│       │   ├── saxo_price.py        ← live price lookup + exchange status + cross-venue fallback
│       │   ├── saxo_instrument.py   ← instrument resolution + all listings + get_siblings()
│       │   ├── saxo_positions.py    ← live positions from Saxo account
│       │   ├── saxo_account.py      ← account info + diagnostics
│       │   ├── saxo_exchange_hours.py ← exchange open/closed/pre/post-market cache
│       │   └── test_regression.py   ← 26-test regression suite (sim or live)
│       └── references/
│           ├── gotchas.md                   ← undocumented Saxo API behaviours
│           ├── exchange-codes.md            ← Saxo exchange code reference
│           ├── saxo-api-license.md          ← 3rd-party non-commercial license text
│           ├── license-compliance-checklist.md ← per-clause compliance status
│           ├── saxo-terms-of-use.md         ← end-user ToU shown at OAuth consent step
│           └── oauth-consent-screenshot.png ← OAuth approval dialog screenshot
└── CLAUDE.md                     ← project context for Claude Code sessions
```

## Known Saxo API quirks

A number of Saxo OpenAPI behaviours are undocumented or contradict the docs.
See [`skills/saxo/references/gotchas.md`](skills/saxo/references/gotchas.md) for the
full list. Key ones:

- `Isin=` query parameter is **silently ignored** — use `Keywords=` instead
- `GroupId=` query parameter is **silently ignored** — filter client-side
- `$select=` returns HTTP 400 — you get the full fixed field set or nothing
- Exchange IDs are Saxo short codes (`AMS`, `FSE`, `LSE_SETS`), not MIC codes
- Sim/trial accounts return `NoAccess` outside market hours — try again during trading hours before switching to a live token

## Roadmap

### Released (v0.1 – v0.7)

- [x] Live price lookup (`saxo_price.py`)
- [x] Instrument resolution — symbol, ISIN, name → UIC, all exchange listings (`saxo_instrument.py`)
- [x] PKCE authentication — browser-based login, macOS Keychain token storage, auto-refresh (`saxo_auth.py`)
- [x] Live positions — `GET /port/v1/positions/me` (`saxo_positions.py`)
- [x] Account info — `GET /port/v1/accounts/me`, useful for diagnostics (`saxo_account.py`)
- [x] Exchange hours cache — market open/closed/pre/post-market status for all exchanges (`saxo_exchange_hours.py`)
- [x] Holdings-aware price lookup — checks held positions first to use the exact UIC, avoiding wrong-exchange matches
- [x] Saxo live-app compliance — rate-limit headers parsed on every request; structured positions output; API schema monitoring; asset-type fallback for unknown instrument types
- [x] Shared utilities module (`saxo_common.py`) — centralises `BASE_URLS` and rate-limit logic
- [x] 28-test regression suite covering all scripts on sim and live
- [x] **Cross-venue live quote fallback** — when the primary exchange is closed, automatically
      tries sibling listings (same `GroupId`) on open exchanges. If ASML on AMS is closed
      but NASDAQ is open, appends `Live via NASDAQ: 219.70 USD (Mid)` to the output.
      Prefers fully-open markets over extended-hours; caps at 3 attempts; notes when the
      sibling trades in a different currency from the primary.

### Planned

- [ ] **Orders blotter** — open and filled orders via `GET /port/v1/orders/me`
- [ ] **Historical prices** — OHLCV chart data for technical analysis
- [ ] **FX conversion** — native-currency positions converted to a base currency for consolidated P&L
- [ ] **Multi-account** — support for users with more than one Saxo account key

### Platform

- [ ] **Windows support** — replace `security` CLI calls in `saxo_auth.py` with
      Windows Credential Manager (`cmdkey` / `wincred`). The rest of the code is
      pure Python and should work unchanged.
- [ ] **Linux support** — use `secret-tool` (libsecret) or fall back to
      `~/.config/saxo/token.json` with a warning.

Pull requests welcome, especially for Windows and Linux token storage.

## Troubleshooting

### Plugin update fails (`ENAMETOOLONG` or `Failed to update`)

`claude plugin update saxo-openapi` triggers a Claude Code bug (confirmed
2026-04-10) where the update command copies the plugin cache directory into
itself recursively until the OS returns `ENAMETOOLONG`. The plugin is not
updated and the cache directory is left in a broken state.

**Workaround — clear both cache directories and reinstall:**

```bash
rm -rf ~/.claude/plugins/cache/saxotrader
rm -rf ~/.claude/plugins/marketplaces/saxotrader
claude plugin uninstall saxotrader
claude plugin marketplace add zaliori-io/claude-marketplace
claude plugin install saxotrader@saxotrader
```

The `rm -rf` steps are required — a plain uninstall leaves stale files in
`~/.claude/plugins/marketplaces/` that prevent the fresh version from loading.

This is a Claude Code issue, not a problem with the plugin. Your config
(`~/.config/saxo/config.json`) and tokens (macOS Keychain) are not affected
by the reinstall — no re-authentication is needed.

## Reference resources

| Resource | Notes |
|---|---|
| [SaxoBank/openapi-samples-js](https://github.com/SaxoBank/openapi-samples-js) | Official Saxo sample code (JavaScript). Most useful for understanding API patterns, error codes, rate-limit headers, and instrument search behaviour. No official Python samples exist. |
| [SaxoBank/openapi-samples-csharp](https://github.com/SaxoBank/openapi-samples-csharp) | Official samples in C#. |
| [hootnot/saxo_openapi](https://github.com/hootnot/saxo_openapi) | Third-party Python wrapper covering ~200 endpoints. Uses 24h developer-portal tokens rather than PKCE — useful for endpoint URL patterns and response shapes. |
| [Saxo developer docs](https://www.developer.saxo/openapi/learn) | Official API documentation index. |
| [Saxo reference docs](https://www.developer.saxo/openapi/referencedocs) | Endpoint reference. |

## License

MIT
