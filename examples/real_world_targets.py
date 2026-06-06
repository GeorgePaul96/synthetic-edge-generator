"""
Real-world fuzzing targets for synthedge.

Libraries under test:
- humanize 4.15.0  — human-readable number/size/time formatting
- validators 0.35.0 — string validation (email, URL, IPv4, UUID)
- boltons 25.0.0    — utility belt (strutils: bytes2human, parse_int_list, slugify)
"""

from edge_case_engine.contracts import fuzz_contract

import humanize
import validators
from boltons import strutils


# ─── humanize ─────────────────────────────────────────────────────────────────

@fuzz_contract(allowed_exceptions=(TypeError,))
def fuzz_humanize_intword(value: float) -> str:
    """Fuzz humanize.intword with edge-case float values including inf/nan."""
    return humanize.intword(value)


@fuzz_contract(allowed_exceptions=(TypeError,))
def fuzz_humanize_naturalsize(value: float) -> str:
    """Fuzz humanize.naturalsize — known to crash on NaN with ValueError."""
    return humanize.naturalsize(value)


@fuzz_contract(allowed_exceptions=(TypeError,))
def fuzz_humanize_intcomma(value: float) -> str:
    """Fuzz humanize.intcomma with edge-case float values."""
    return humanize.intcomma(value)


@fuzz_contract(allowed_exceptions=(TypeError,))
def fuzz_humanize_scientific(value: float) -> str:
    """Fuzz humanize.scientific with edge-case float values."""
    return humanize.scientific(value)


# ─── validators ───────────────────────────────────────────────────────────────

@fuzz_contract(allowed_exceptions=())
def fuzz_validators_email(email: str) -> bool:
    """Fuzz validators.email — should never raise, only return True/ValidationError."""
    result = validators.email(email)
    return bool(result)


@fuzz_contract(allowed_exceptions=())
def fuzz_validators_url(url: str) -> bool:
    """Fuzz validators.url — should never raise, only return True/ValidationError."""
    result = validators.url(url)
    return bool(result)


@fuzz_contract(allowed_exceptions=())
def fuzz_validators_ipv4(address: str) -> bool:
    """Fuzz validators.ipv4 — should never raise, only return True/ValidationError."""
    result = validators.ipv4(address)
    return bool(result)


@fuzz_contract(allowed_exceptions=())
def fuzz_validators_uuid(value: str) -> bool:
    """Fuzz validators.uuid — should never raise, only return True/ValidationError."""
    result = validators.uuid(value)
    return bool(result)


# ─── boltons.strutils ─────────────────────────────────────────────────────────

@fuzz_contract(allowed_exceptions=(TypeError,))
def fuzz_boltons_bytes2human(value: float) -> str:
    """Fuzz boltons.strutils.bytes2human — returns 'infZ'/'nanZ' for inf/nan (wrong)."""
    return strutils.bytes2human(value)


@fuzz_contract(allowed_exceptions=(TypeError,))
def fuzz_boltons_ordinalize(value: float) -> str:
    """Fuzz boltons.strutils.ordinalize with edge-case numbers."""
    return strutils.ordinalize(value)


@fuzz_contract(allowed_exceptions=(TypeError,))
def fuzz_boltons_parse_int_list(value: str) -> list:
    """Fuzz boltons.strutils.parse_int_list — known to crash on strings with leading '-'."""
    return strutils.parse_int_list(value)


@fuzz_contract(allowed_exceptions=(TypeError,))
def fuzz_boltons_slugify(value: str) -> str:
    """Fuzz boltons.strutils.slugify with edge-case strings."""
    return strutils.slugify(value)
