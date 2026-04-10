#!/usr/bin/env python3
"""
Regression test suite for the Saxo OpenAPI plugin.

Runs all scripts via subprocess and asserts on exit code, output content,
and basic data validity. No test framework required — plain stdlib only.

Usage:
    python test_regression.py sim    # after every code change (~26 tests, ~35s)
    python test_regression.py live   # before every release tag (~26 tests)

Exit code: 0 if all tests pass, 1 if any fail.

Test tagging:
    BOTH — runs on sim and live (assertions may differ by env)
    SIM  — sim only (e.g. IsTrialAccount: true, empty positions)
    LIVE — live only (e.g. non-trial account, real positions, listing counts ≥ sim)
"""
import json
import pathlib
import subprocess
import sys

SCRIPTS = pathlib.Path(__file__).parent
ENV = sys.argv[1] if len(sys.argv) > 1 else "sim"
IS_LIVE = ENV == "live"

PASS = "PASS"
FAIL = "FAIL"
results = []


# ── helpers ──────────────────────────────────────────────────────────────────

def run(script, *args):
    """Run a script and return (exit_code, stdout, stderr)."""
    cmd = [sys.executable, str(SCRIPTS / script)] + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def check(name, code, stdout, stderr, *assertions):
    """Evaluate assertions and record the result. Prints one line per test."""
    failures = []
    if code != 0:
        failures.append(f"non-zero exit code ({code})")
    if "ERROR:" in stdout:
        failures.append(f"ERROR in output: {stdout.strip()[:120]}")
    for label, ok in assertions:
        if not ok:
            failures.append(label)
    status = PASS if not failures else FAIL
    results.append((status, name, failures))
    tag = "✅" if status == PASS else "❌"
    print(f"  {tag} {name}")
    for f in failures:
        print(f"       → {f}")


def price_from(stdout):
    """Extract the first numeric price value from saxo_price.py output."""
    for line in stdout.splitlines():
        if line.strip().startswith("Price :"):
            for part in line.split():
                try:
                    return float(part)
                except ValueError:
                    continue
    return None


def count_from(stdout, label="Found"):
    """Extract the first integer after label in saxo_instrument.py output."""
    for line in stdout.splitlines():
        if line.strip().startswith(label):
            for part in line.split():
                if part.isdigit():
                    return int(part)
    return 0


def parse_account(stdout):
    """Parse saxo_account.py JSON output. Returns first account dict or {}."""
    try:
        return json.loads(stdout).get("Data", [{}])[0]
    except (json.JSONDecodeError, IndexError):
        return {}


def parse_positions(stdout):
    """Parse saxo_positions.py JSON output. Returns the full response dict."""
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return {}


# ── test sections ─────────────────────────────────────────────────────────────

print(f"\nSaxo OpenAPI regression tests — environment: {ENV}")
print("=" * 64)

# ── Auth (BOTH) ───────────────────────────────────────────────────────────────
print("\n[Auth]")

code, out, err = run("saxo_auth.py", "status")
check("T01 auth status shows valid tokens",
      code, out, err,
      ("'valid' in output",       "valid" in out.lower()),
      (f"environment label is {ENV}", ENV in out))

# ── Instrument lookup (BOTH) ──────────────────────────────────────────────────
print("\n[Instrument lookup]")

code, out, err = run("saxo_instrument.py", "ASML", ENV)
check("T02 instrument by symbol (ASML)",
      code, out, err,
      ("≥4 listings found",       count_from(out) >= 4),
      ("AMS exchange present",    "AMS" in out),
      ("primary listing ★ shown", "★" in out))

code, out, err = run("saxo_instrument.py", "CA9628791027", ENV)
check("T03 instrument by ISIN (Wheaton CA9628791027)",
      code, out, err,
      ("≥3 listings found",       count_from(out) >= 3),
      ("TSE exchange present",    "TSE" in out),
      ("(ISIN) label in output",  "(ISIN)" in out),
      ("issuer country CA shown", "CA" in out))

code, out, err = run("saxo_instrument.py", "Wheaton Precious Metals", ENV)
check("T04 instrument by free-text name",
      code, out, err,
      ("≥1 listing found",        count_from(out) >= 1),
      ("Wheaton in output",       "Wheaton" in out))

code, out, err = run("saxo_instrument.py", "15777171", ENV)
check("T05 instrument by UIC (15777171 = Apple)",
      code, out, err,
      ("Apple in output",         "Apple" in out),
      ("NASDAQ present",          "NASDAQ" in out))

code, out, err = run("saxo_instrument.py", "Apple", ENV, "--include-bonds")
check("T06 instrument --include-bonds (Apple)",
      code, out, err,
      ("≥3 listings found",       count_from(out) >= 3),
      ("Bond asset type present", "Bond" in out),
      ("Stock also present",      "Stock" in out))

# Graceful not-found: bad query should exit 0 and say "not found", no ERROR:
code, out, err = run("saxo_instrument.py", "ZZZZNOTAREALINSTRUMENT99999", ENV)
check("T07 instrument graceful not-found (bad query)",
      code, out, err,
      ("exit 0 on not-found",     code == 0),
      ("no ERROR: prefix",        "ERROR:" not in out))

# ── Price lookup (BOTH) ───────────────────────────────────────────────────────
print("\n[Price lookup]")

code, out, err = run("saxo_price.py", "ASML", ENV)
price = price_from(out)
check("T08 price by symbol (ASML)",
      code, out, err,
      ("price > 0",                    price is not None and price > 0),
      ("EUR currency shown",           "EUR" in out),
      ("[market state] label present", "[market" in out),
      ("Prev close line present",      "Prev close" in out),
      ("Bid line present",             "Bid" in out),
      ("Ask line present",             "Ask" in out),
      ("Spread line present",          "Spread" in out))

code, out, err = run("saxo_price.py", "CA9628791027", ENV)
price = price_from(out)
check("T09 price by ISIN (CA9628791027 = Wheaton)",
      code, out, err,
      ("price > 0",          price is not None and price > 0),
      ("Wheaton in output",  "Wheaton" in out),
      ("Prev close present", "Prev close" in out))

code, out, err = run("saxo_price.py", "211", ENV)
price = price_from(out)
check("T10 price by UIC (211 = Apple NASDAQ) — tests UIC→Uics= fix",
      code, out, err,
      ("price > 0",         price is not None and price > 0),
      ("Apple in output",   "Apple" in out),
      ("USD currency",      "USD" in out),
      ("not HKD (old bug)", "HKD" not in out))

code, out, err = run("saxo_price.py", "VanEck Uranium", ENV)
price = price_from(out)
check("T11 price by ETF name (VanEck Uranium)",
      code, out, err,
      ("price > 0",          price is not None and price > 0),
      ("Etf in output",      "Etf" in out),
      ("Prev close present", "Prev close" in out))

# ── Account (BOTH, with env-specific assertion) ────────────────────────────────
print("\n[Account & Positions]")

code, out, err = run("saxo_account.py", ENV)
acct = parse_account(out)
check("T12 account metadata",
      code, out, err,
      ("IsTrialAccount field present",       "IsTrialAccount" in acct),
      ("Currency field present",             bool(acct.get("Currency"))),
      ("LegalAssetTypes non-empty",          len(acct.get("LegalAssetTypes", [])) > 0),
      ("IsTrialAccount=True on sim (env)",   IS_LIVE or acct.get("IsTrialAccount") is True),
      ("IsTrialAccount=False on live (env)", not IS_LIVE or acct.get("IsTrialAccount") is False))

# ── Positions (BOTH, with env-specific assertion) ─────────────────────────────

# T13: JSON structure via --raw flag
code, out, err = run("saxo_positions.py", ENV, "--raw")
pos = parse_positions(out)
data_list = pos.get("Data", [])
count      = pos.get("__count", -1)
has_display = (
    "DisplayAndFormat" in data_list[0] if data_list else not IS_LIVE
    # on sim trial account, Data is empty — acceptable
    # on live, first position must have DisplayAndFormat
)
check("T13 positions --raw JSON structure",
      code, out, err,
      ("valid JSON with __count",             "__count" in pos),
      ("Data is a list",                      isinstance(data_list, list)),
      ("__count matches len(Data)",           count == len(data_list)),
      ("DisplayAndFormat present if live",    has_display),
      ("count=0 on sim trial (expected)",     IS_LIVE or count == 0),
      ("count>0 on live (real account)",      not IS_LIVE or count > 0))

# T13b: formatted output (default, no --raw) — L8.6 compliance
code2, out2, err2 = run("saxo_positions.py", ENV)
check("T13b positions formatted output",
      code2, out2, err2,
      ("formatted header present",            "Open Positions" in out2),
      ("env label shown",                     ENV in out2),
      ("position count shown",                "position" in out2))

# ── Exchange hours (BOTH) ─────────────────────────────────────────────────────
print("\n[Exchange hours]")

# T14 — CLI runs and prints a table
code, out, err = run("saxo_exchange_hours.py", ENV)
check("T14 exchange hours CLI (default exchanges)",
      code, out, err,
      ("AMS in output",    "AMS" in out),
      ("NASDAQ in output", "NASDAQ" in out),
      ("NYSE in output",   "NYSE" in out),
      ("FSE in output",    "FSE" in out),
      ("status label shown (open/closed/pre/post)",
       any(w in out for w in ("open", "closed", "pre-market", "post-market"))))

# T15 — Cache file created and contains expected exchanges
# sys.path already set up here so we can import CACHE_PATH from the module itself
# (avoids duplicating the path constant).
sys.path.insert(0, str(SCRIPTS))
from saxo_exchange_hours import CACHE_PATH as cache_path
import json as _json
cache_ok = False
cache_count = 0
cache_has_ams = cache_has_nasdaq = False
if cache_path.exists():
    try:
        cache_data = _json.loads(cache_path.read_text())
        exch = cache_data.get("exchanges", {})
        cache_count    = len(exch)
        cache_has_ams  = "AMS" in exch
        cache_has_nasdaq = "NASDAQ" in exch
        cache_ok = True
    except Exception:
        pass

# Run a dummy command to ensure the cache is populated
if not cache_ok:
    run("saxo_exchange_hours.py", "--refresh", ENV)

check("T15 exchange hours cache created and populated",
      0, "", "",    # cache check is independent of a subprocess call
      ("cache file exists",           cache_path.exists()),
      ("≥50 exchanges cached",        cache_count >= 50),
      ("AMS in cache",                cache_has_ams),
      ("NASDAQ in cache",             cache_has_nasdaq))

# T16 — get_market_status() returns a valid label for AMS
try:
    from saxo_auth import get_valid_token, load_config
    from saxo_exchange_hours import get_market_status
    _cfg = load_config()
    _cfg["environment"] = ENV
    _tok = get_valid_token(_cfg)
    status = get_market_status("AMS", _tok, _cfg)
    valid_label = status.get("label") in ("open", "closed", "pre-market", "post-market")
    has_name    = bool(status.get("name"))
    has_state   = bool(status.get("state"))
    is_bool     = isinstance(status.get("is_open"), bool)
    import_ok   = True
except Exception as exc:
    valid_label = has_name = has_state = is_bool = import_ok = False
    print(f"       (import error: {exc})")

check("T16 get_market_status('AMS') returns valid structure",
      0, "", "",
      ("import succeeds",            import_ok),
      ("label is open/closed/pre/post", valid_label),
      ("name is non-empty",          has_name),
      ("state is non-empty",         has_state),
      ("is_open is bool",            is_bool))

# T17 — specific exchange by CLI argument
code, out, err = run("saxo_exchange_hours.py", "NASDAQ", ENV)
check("T17 exchange hours CLI single exchange (NASDAQ)",
      code, out, err,
      ("NASDAQ in output", "NASDAQ" in out),
      ("label shown",      any(w in out for w in ("open", "closed", "pre-market", "post-market"))))

# T18 — saxo_price.py shows "Exchange :" line from cache before price block
code, out, err = run("saxo_price.py", "ASML", ENV)
check("T18 price output includes exchange hours line",
      code, out, err,
      ("'Exchange :' line present",       "Exchange :" in out),
      ("exchange name in output",         "Euronext" in out or "Amsterdam" in out),
      ("market state label in exch line", any(w in out for w in ("[open", "[closed", "[pre-", "[post-"))))

# T19 — UIC input shows correct exchange (NASDAQ, not a random exchange)
code, out, err = run("saxo_price.py", "211", ENV)
check("T19 price by UIC shows correct exchange (Apple → NASDAQ)",
      code, out, err,
      ("Exchange line present", "Exchange :" in out),
      ("NASDAQ in exchange line", "NASDAQ" in out))

# ── API schema check (BOTH) ───────────────────────────────────────────────────
print("\n[API schema check]")

# T20 — saxo_auth.py check-api probes API and writes result file (L11.1)
# Note: check-api reads environment from config; no positional ENV arg.
code, out, err = run("saxo_auth.py", "check-api")  # noqa: E501
api_check_path = pathlib.Path.home() / ".config" / "saxo" / "api-check.json"
api_check_written = api_check_path.exists()
api_check_fields_ok = False
if api_check_written:
    try:
        api_check_data = json.loads(api_check_path.read_text())
        api_check_fields_ok = (
            "ok" in api_check_data
            and "checked_at" in api_check_data
        )
    except Exception:
        pass

check("T20 check-api validates API schema (L11.1)",
      code, out, err,
      ("exit 0",                  code == 0),
      ("pass/warn/fail in output", any(w in out.lower() for w in
                                       ("responding normally", "schema as expected",
                                        "warning", "unexpected", "missing"))),
      ("api-check.json written",  api_check_written),
      ("result file has status",  api_check_fields_ok))

# T21 — _check_schema_fields() detects missing / present fields (L11.1 unit)
# Pure in-process test — no API call needed. Verifies the detection logic
# that T20 cannot exercise without actually removing a field from the live API.
try:
    from saxo_auth import _check_schema_fields, _API_EXPECTED_FIELDS
    _full_item    = {f: "x" for f in _API_EXPECTED_FIELDS}
    _partial_item = {f: "x" for f in _API_EXPECTED_FIELDS - {"Symbol"}}

    _ok_full,    _            = _check_schema_fields([_full_item])
    _ok_missing, _msg_missing = _check_schema_fields([_partial_item])
    _ok_empty,   _            = _check_schema_fields([])
    _schema_import_ok = True
except Exception as exc:
    _ok_full = _ok_missing = _ok_empty = _schema_import_ok = False
    _msg_missing = ""
    print(f"       (import error: {exc})")

check("T21 _check_schema_fields detects schema changes (L11.1 unit test)",
      0, "", "",
      ("import succeeds",           _schema_import_ok),
      ("full set → ok=True",        _ok_full is True),
      ("missing field → ok=False",  _ok_missing is False),
      ("missing field named in msg","Symbol" in _msg_missing),
      ("empty data → ok=False",     _ok_empty is False))

# ── Cross-venue fallback (BOTH) ───────────────────────────────────────────────
print("\n[Cross-venue fallback]")

# T22 — get_siblings() returns sibling listings with correct structure for ASML
try:
    from saxo_instrument import get_siblings as _get_siblings_fn
    from saxo_price import find_instrument as _find_instrument_fn
    from saxo_common import BASE_URLS as _BASE_URLS2
    _cfg3 = load_config()
    _cfg3["environment"] = ENV
    _tok3 = get_valid_token(_cfg3)
    _base3 = _BASE_URLS2[ENV]

    _asml_uic, _asml_at, _asml_exch = _find_instrument_fn(_tok3, "ASML", _base3, _cfg3)
    _siblings = _get_siblings_fn(_tok3, _asml_uic, _asml_at, _base3)
    _sib_list_ok = isinstance(_siblings, list)
    _sib_has_items = len(_siblings) >= 1
    _required_keys = ("uic", "exchange_id", "asset_type", "currency", "name", "group_id")
    _sib_keys_ok = all(
        all(k in s for k in _required_keys) for s in _siblings
    ) if _siblings else True
    _siblings_import_ok = True
except Exception as _exc:
    _sib_list_ok = _sib_has_items = _sib_keys_ok = _siblings_import_ok = False
    print(f"       (error: {_exc})")

check("T22 get_siblings() returns sibling listings for ASML",
      0, "", "",
      ("import and call succeed",         _siblings_import_ok),
      ("result is a list",                _sib_list_ok),
      ("≥1 sibling returned",             _sib_has_items),
      ("each sibling has required keys",  _sib_keys_ok))

# T23 — get_siblings() returns [] for a non-existent UIC
try:
    _no_siblings = _get_siblings_fn(_tok3, 999999999, "Stock", _base3)
    _no_sib_ok = isinstance(_no_siblings, list) and len(_no_siblings) == 0
    _no_sib_call_ok = True
except Exception as _exc:
    _no_sib_ok = _no_sib_call_ok = False
    print(f"       (error: {_exc})")

check("T23 get_siblings() returns [] for non-existent UIC",
      0, "", "",
      ("call succeeds",       _no_sib_call_ok),
      ("result is empty []",  _no_sib_ok))

# T24 — find_live_fallback() returns None or a valid dict (result type check)
try:
    from saxo_price import find_live_fallback as _find_fallback_fn
    _fb = _find_fallback_fn(_tok3, _asml_uic, _asml_at, _asml_exch, _base3, _cfg3)
    _fb_type_ok = _fb is None or (
        isinstance(_fb, dict) and
        all(k in _fb for k in ("exchange_id", "price_result", "currency", "asset_type"))
    )
    _fb_call_ok = True
except Exception as _exc:
    _fb_type_ok = _fb_call_ok = False
    print(f"       (error: {_exc})")

check("T24 find_live_fallback() returns None or valid dict",
      0, "", "",
      ("call succeeds",              _fb_call_ok),
      ("returns None or valid dict", _fb_type_ok))

# T25 — saxo_price.py output: if "Live via" appears it has valid format
import re as _re
code, out, err = run("saxo_price.py", "ASML", ENV)
_live_via_lines = [l for l in out.splitlines() if "Live via" in l]
_live_via_fmt_ok = True
if _live_via_lines:
    # Expected format: "  Live via NASDAQ: 219.70 USD (Mid)  [15m delayed]"
    _live_via_fmt_ok = bool(_re.search(r"Live via \w+: [\d.]+", _live_via_lines[0]))
check("T25 price output cross-venue format (if Live via present, format is valid)",
      code, out, err,
      ("no ERROR: in output",           "ERROR:" not in out),
      ("Live via format valid",         _live_via_fmt_ok))

# ── SGX-ST regression guard (BOTH) ───────────────────────────────────────────
print("\n[SGX-ST regression guard]")

# T26 — EXCHANGE_PREF unit: SGX-ST present, bare SGX absent (v0.7.2 fix)
# Prior to v0.7.2, the list contained "SGX" which Saxo never returns as an
# ExchangeId — Singapore Exchange is "SGX-ST". This caused DBS and other
# SGX-listed holdings to rank 99 (unknown) and fall back to the OOTC ADR.
try:
    from saxo_price import EXCHANGE_PREF as _EXCH_PREF
    _sgx_st_in  = "SGX-ST" in _EXCH_PREF
    _sgx_bare_out = "SGX" not in _EXCH_PREF   # old broken code used bare "SGX"
    _sgx_import_ok = True
except Exception as _exc:
    _sgx_st_in = _sgx_bare_out = _sgx_import_ok = False
    print(f"       (import error: {_exc})")

check("T26 EXCHANGE_PREF has 'SGX-ST', not bare 'SGX' (v0.7.2 regression)",
      0, "", "",
      ("import succeeds",            _sgx_import_ok),
      ("'SGX-ST' in EXCHANGE_PREF",  _sgx_st_in),
      ("bare 'SGX' not in list",     _sgx_bare_out))

# T27 — exchange hours cache recognises SGX-ST as a valid exchange code
code, out, err = run("saxo_exchange_hours.py", "SGX-ST", ENV)
check("T27 exchange hours SGX-ST recognised and shows status",
      code, out, err,
      ("SGX-ST in output", "SGX-ST" in out),
      ("status label shown", any(w in out for w in
                                 ("open", "closed", "pre-market", "post-market"))))

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 64)
passed = sum(1 for s, _, _ in results if s == PASS)
failed = sum(1 for s, _, _ in results if s == FAIL)
total  = len(results)
print(f"Results: {passed}/{total} passed, {failed} failed  ({ENV})")
if failed:
    print("\nFailed tests:")
    for status, name, failures in results:
        if status == FAIL:
            print(f"  {name}")
            for f in failures:
                print(f"    • {f}")
    sys.exit(1)
else:
    print("All tests passed.")
    sys.exit(0)
