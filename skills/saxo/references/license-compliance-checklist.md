# Saxo API License — Compliance Checklist

Last reviewed: 2026-04-09. Based on the full license text in `saxo-api-license.md`.

Legend: ✅ Compliant | ⚠️ Partial / caveat | ❌ Not compliant | N/A Not applicable

---

## DISCLAIMER — General

| # | Requirement | Status | Evidence |
|---|---|---|---|
| G1 | AppSecret never sent to a public location | ✅ | PKCE flow — no AppSecret exists by design |
| G2 | RefreshToken never sent to a public location | ✅ | Stored in macOS Keychain only; transmitted solely to `logonvalidation.net/token` via HTTPS |
| G3 | Monkey test — rapid input cannot crash or hang | ✅ | CLI tools, no UI. HTTP timeouts 10–15 s. OAuth callback server shuts down via daemon thread. No infinite loops. |
| G4 | No excessive 400 errors | ✅ | `$select=` (only known 400 source in ref API) is never used. All parameters tested against sim. |
| G5 | No throttling limit violations (429 / 409) | ✅ | `X-RateLimit-AppDay-Remaining` and `X-RateLimit-RefDataInstrumentsMinute-Remaining` parsed in every `_get()` helper. Raises `SaxoAuthError` when either hits 0; prints stderr warning at ≤5. |

---

## DISCLAIMER — Reading Data

| # | Requirement | Status | Evidence |
|---|---|---|---|
| R1 | No crash/hang with many positions or orders | ✅ | `saxo_positions.py` and `saxo_account.py` follow `__next` cursor pagination with no page-count cap |
| R2 | Do not assume client/account/instrument currencies | ✅ | Native currencies reported as-is. No FX conversion. Multi-account clients surface all account currencies. |
| R3 | Correct decimal display (separator, decimals, tick sizes) | ✅ | `saxo_price.py` reads `Decimals` from `DisplayAndFormat` field and formats output accordingly |
| R4 | Gracefully handle unexpected instruments/asset types | ✅ | When filtered search returns no results, both `saxo_price.py` and `saxo_instrument.py` retry without `AssetTypes=` filter and surface the discovered type with a stderr note. |
| R5 | Correctly handle fractional amounts | ✅ | All quantities and prices handled as Python floats. No integer-only assumptions. |

---

## DISCLAIMER — Trading

| # | Requirement | Status | Evidence |
|---|---|---|---|
| T1 | All order types tested | N/A | Read-only plugin — no order placement in v1 |
| T2 | Invalid orders handled gracefully | N/A | Read-only plugin |
| T3 | Automatic trading safety measures | N/A | Read-only plugin — no automated trading |

---

## DISCLAIMER — Future Changes / Versioning

| # | Requirement | Status | Evidence |
|---|---|---|---|
| V1 | Read and understood versioning/obsolescence policy | ✅ | Policy documented in CLAUDE.md §11. New fields handled by `.get()` with defaults. |
| V2 | New enum values handled seamlessly (no crash) | ✅ | Same fix as R4 — fallback retry without `AssetTypes=` catches new enum values and surfaces them rather than silently excluding |

---

## LICENSE — §2 Rights Granted

| # | Clause | Status | Notes |
|---|---|---|---|
| L2.1 | Personal non-transferable use for own Saxo accounts only | ✅ | Each user registers their own AppKey; plugin enforces this by design |
| L2.2 | Grant Saxo right to mention/promote the app | ✅ (acknowledged) | Noted in README. Registering a live app implicitly grants this. |

---

## LICENSE — §4 Limitation of Liability

| # | Clause | Status | Notes |
|---|---|---|---|
| L4.1 | Acknowledge data may be inaccurate/incomplete/not up to date | ✅ | Stated in README. Prices carry implicit "use at own risk" from Saxo's disclaimer. |
| L4.2a | Comply with all applicable local laws | ✅ | Personal use tool; user is responsible for their own jurisdiction |
| L4.2b | No unlawful or fraudulent use | ✅ | Read-only, personal use |
| L4.2c | No malware/viruses/DoS/harmful code | ✅ | Open source, auditable. No network calls beyond Saxo APIs. |

---

## LICENSE — §8 Technical Requirements

| # | Clause | Status | Evidence |
|---|---|---|---|
| L8.1 | App Keys strictly confidential and non-transferable | ✅ | AppKey lives only in `~/.config/saxo/config.json` (user's machine). Never committed to repo. |
| L8.2 | Auth via Saxo login system only — no interception | ✅ | PKCE opens `logonvalidation.net` in browser. Local callback receives only the auth code redirect. Credentials never touch plugin code. |
| L8.3 | RefreshToken only used with Saxo auth server | ✅ | `saxo_auth.py` sends refresh token only to `logonvalidation.net/token` |
| L8.4 | App's sole responsibility to monitor/restrict API usage | ✅ (acknowledged) | Personal use; user is sole operator |
| L8.5 | Responsible for all Transactions via the App | N/A | Read-only — no transactions |
| L8.6 | Correct display of positions, orders, holdings, quotes | ✅ | `saxo_positions.py` outputs a formatted table (name, qty, open price, current price, P&L, P&L%, currency) using API decimals. Raw JSON available via `--raw` flag. |
| L8.7 | No cross-contamination between End Users | ✅ | Each user has own AppKey + separate Keychain entry (`saxotrader-live` / `saxotrader-sim`) |
| L8.8 | Best efforts to comply with all laws and exchange rules | ✅ (acknowledged) | Personal use; user is responsible. No exchange rules violated by read-only data access. |
| L8.9 | Protect credential security; indemnify Saxo for breaches | ✅ | Keychain storage; no tokens on disk or in repo. Config file contains only non-secret AppKey. |

---

## LICENSE — §9 Environments

| # | Clause | Status | Evidence |
|---|---|---|---|
| L9.3 | Verify against sim before live; continue sim testing | ✅ | Sim smoke test documented in CLAUDE.md §11. Re-run periodically. |

---

## LICENSE — §10 Verification

| # | Clause | Status | Evidence |
|---|---|---|---|
| L10.1 | Solely responsible for verifying API compatibility | ✅ | Sim smoke test suite covers all five scripts |
| L10.2 | Solely responsible for testing End User access | ✅ | Each user tests their own setup via `saxo_auth.py login` |

---

## LICENSE — §11 Modifications

| # | Clause | Status | Notes |
|---|---|---|---|
| L11.1 | Update app when API changes; notify End Users | ✅ | `saxo_auth.py check-api` probes `/ref/v1/instruments` for expected fields and records result + timestamp to `~/.config/saxo/api-check.json`. Result shown in `saxo_auth.py status`. |

---

## LICENSE — §12 Public Announcement

| # | Clause | Status | Notes |
|---|---|---|---|
| L12.1 | No public announcement about license without Saxo consent | ⚠️ | README and CLAUDE.md document compliance context and include the license text captured from the portal. This is arguably operational documentation rather than a "public announcement about the license." Saxo has not objected. Exercise caution about going further (blog posts, press releases, etc.). |

---

## LICENSE — §15 Governing Law

| # | Clause | Status | Notes |
|---|---|---|---|
| L15.1 | Danish law, Danish Courts | ✅ (acknowledged) | Noted. User accepts this on registration. |

---

## Summary

| Category | ✅ | ⚠️ | N/A |
|---|---|---|---|
| Disclaimer — General | 5 | 0 | 0 |
| Disclaimer — Reading Data | 5 | 0 | 0 |
| Disclaimer — Trading | 0 | 0 | 3 |
| Disclaimer — Versioning | 2 | 0 | 0 |
| License clauses | 17 | 1 | 2 |
| **Total** | **29** | **1** | **5** |

### Open items (⚠️)

| ID | Issue | Code fix | Risk |
|---|---|---|---|
| L12.1 | License text published in public repo | Non-code — operational transparency rather than announcement; no further action unless Saxo objects | Low |
