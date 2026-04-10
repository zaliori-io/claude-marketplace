# Saxo Exchange Codes

Saxo OpenAPI returns its own short codes in the `ExchangeId` field — **not** standard
MIC codes. The MIC equivalents below are for reference only; use the Saxo codes
in all API calls and preference lists.

| Saxo Code | Exchange | MIC (reference) | Notes |
|---|---|---|---|
| `AMS` | Euronext Amsterdam | XAMS | |
| `PAR` | Euronext Paris | XPAR | |
| `FSE` | Deutsche Börse / XETRA (stocks) | XETR | Saxo's label for XETRA stock listings |
| `XETR_ETF` | Deutsche Börse / XETRA (ETFs) | XETR | Separate code for the ETF segment |
| `MIL` | Borsa Italiana / Milan (stocks) | XMIL | |
| `MIL_ETF` | Borsa Italiana (ETFs) | XMIL | |
| `LSE_SETS` | London Stock Exchange (stocks) | XLON | SETS = Stock Exchange Electronic Trading Service |
| `LSE_ETF` | London Stock Exchange (ETFs) | XLON | |
| `SWX` | SIX Swiss Exchange (stocks) | XSWX | |
| `SWX_ETF` | SIX Swiss Exchange (ETFs) | XSWX | |
| `TSE` | Toronto Stock Exchange | XTSE | |
| `CSE` | Copenhagen Stock Exchange | XCSE | |
| `NASDAQ` | NASDAQ | XNAS | |
| `NYSE` | New York Stock Exchange | XNYS | |
| `NYSE_ARCA` | NYSE Arca | ARCX | ETFs and equities |
| `SGX-ST` | Singapore Exchange | XSES | Note: code is `SGX-ST`, **not** `SGX` |
| `SGX-DT` | Singapore Exchange Derivatives | XSIM | Derivatives segment |
| `OOTC` | OTC / Pink Sheets | — | Last resort, typically illiquid |

## Important

- **Never use** `XETRA`, `XAMS`, `AEB`, or full MIC codes in exchange preference
  lists or matching logic — Saxo never returns these and they will silently fail to match.
- `FSE` and `XETR_ETF` are distinct codes for the same underlying XETRA system.
  Stocks trade under `FSE`; ETFs trade under `XETR_ETF`.
- `LSE_SETS` and `LSE_ETF` are similarly split by asset type.

## Recommended Exchange Preference Order (EU-based account)

When multiple listings exist for the same instrument, prefer in this order:

```
AMS → PAR → FSE → XETR_ETF → MIL → MIL_ETF → LSE_SETS → LSE_ETF
→ SWX → SWX_ETF → TSE → NASDAQ → NYSE → NYSE_ARCA → SGX-ST → OOTC
```

Always override with the exchange the user actually holds the position on,
if portfolio context is known.
