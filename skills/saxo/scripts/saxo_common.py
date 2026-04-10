#!/usr/bin/env python3
"""
Shared constants and utilities for Saxo OpenAPI scripts.

Imported by saxo_price, saxo_instrument, saxo_account, saxo_positions,
and saxo_exchange_hours to eliminate copy-pasted BASE_URLS and
_warn_rate_limits across files.
"""
import sys
from decimal import Decimal, ROUND_HALF_UP

BASE_URLS = {
    "sim":  "https://gateway.saxobank.com/sim/openapi",
    "live": "https://gateway.saxobank.com/openapi",
}

VALID_ENVS = frozenset(BASE_URLS)


def to_decimal(value, decimals):
    """Convert a Saxo API float to Decimal, quantized to instrument precision.

    Uses str() conversion to avoid IEEE 754 representation errors.
    decimals comes from DisplayAndFormat.Decimals in the API response.
    Returns None if value is None.
    """
    if value is None:
        return None
    quantizer = Decimal(10) ** -int(decimals)
    return Decimal(str(value)).quantize(quantizer, rounding=ROUND_HALF_UP)


def warn_rate_limits(headers):
    """Warn/raise on Saxo rate-limit response headers (G5 compliance).

    Saxo enforces ~60 req/min on /ref/v1/instruments and a daily app cap.
    Headers checked: X-RateLimit-AppDay-Remaining,
                     X-RateLimit-RefDataInstrumentsMinute-Remaining.
    Raises SaxoAuthError when either counter hits 0; prints a warning at ≤5.
    """
    from saxo_auth import SaxoAuthError
    for h in ("X-RateLimit-AppDay-Remaining",
              "X-RateLimit-RefDataInstrumentsMinute-Remaining"):
        val = headers.get(h)
        if val is None:
            continue
        n = int(val)
        if n == 0:
            raise SaxoAuthError(
                f"Saxo rate limit exhausted ({h}=0). Wait ~1 minute before retrying."
            )
        if n <= 5:
            print(f"WARNING: Saxo rate limit low: {h}={n}", file=sys.stderr)


def validate_env(env_arg):
    """Exit with a clear message if env_arg is not 'sim', 'live', or None."""
    if env_arg is not None and env_arg not in VALID_ENVS:
        sys.exit(
            f"[saxo] Invalid environment '{env_arg}'. "
            f"Valid values: {', '.join(sorted(VALID_ENVS))}."
        )
