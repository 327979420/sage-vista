"""Pure parsing of a US symbol response; not HTTP provenance or formal coverage.

The trusted collector must retain raw responses, including rejected ones, and
prove the fixed request/transport separately. No I/O, identity assignment,
qualification or UniverseSnapshot construction happens here.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
from zoneinfo import ZoneInfo

from services.contracts.market_data import require_date
from services.contracts.validation import ContractError
from services.scanner.audit_eodhd import PRIMARY, common

POLICY_VERSION = 'm12-eodhd-membership-source-1.0.0'
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
NEW_YORK = ZoneInfo('America/New_York')
# Recognized source vocabulary, not an expanded selection universe. Unknown
# values require source review; they must not silently become exclusions.
KNOWN_TYPES = frozenset({'Common Stock', 'Preferred Stock', 'ETF', 'FUND',
                         'Mutual Fund', 'Warrant', 'Unit', 'Notes'})
KNOWN_EXCHANGES = frozenset(PRIMARY) | frozenset({
    'BATS', 'PINK', 'NMFQS', 'OTCQB', 'OTCQX', 'OTCMKTS', 'OTCBB', 'OTCGREY', 'OTC',
})


class MembershipSourceError(ContractError):
    """Finite diagnostics without provider bodies, credentials or URLs."""


@dataclass(frozen=True)
class SourceSymbol:
    provider_code: str
    exchange: str
    instrument_type: str
    name: str
    country: str
    currency: str
    isin: str | None


@dataclass(frozen=True)
class ExcludedSymbol:
    symbol: SourceSymbol
    reason: str


@dataclass(frozen=True)
class ParsedMembership:
    as_of: str
    started_at: datetime
    completed_at: datetime
    raw_bytes: bytes
    raw_sha256: str
    policy_version: str
    raw_count: int
    included: tuple[SourceSymbol, ...]
    excluded: tuple[ExcludedSymbol, ...]


def _text(value):
    if (type(value) is not str or not value or value.strip() != value or
            any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise MembershipSourceError('membership_field_invalid')
    return value


def parse_us_symbol_response(raw: bytes, *, as_of: str, started_at: datetime,
                             completed_at: datetime) -> ParsedMembership:
    """Parse all rows and retain every inclusion/exclusion without choosing IDs.

    Dates/timestamps are collector observations, not supplier historical claims.
    This result deliberately has no `complete` flag or formal universe identity.
    """
    try:
        require_date(as_of, 'as_of')
        for stamp in (started_at, completed_at):
            if type(stamp) is not datetime or stamp.utcoffset() != timedelta(0):
                raise ValueError('UTC observation required')
            if stamp.astimezone(NEW_YORK).date().isoformat() != as_of:
                raise ValueError('cross-date response')
        if completed_at < started_at:
            raise ValueError('clock reversed')
    except (ValueError, TypeError, OverflowError, ContractError):
        raise MembershipSourceError('membership_observation_date_invalid') from None
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_RESPONSE_BYTES:
        raise MembershipSourceError('membership_response_size_invalid')

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate key')
            result[key] = value
        return result

    try:
        rows = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
        json.dumps(rows, ensure_ascii=False, allow_nan=False).encode("utf-8")  # All metadata too.
        if type(rows) is not list or not rows:
            raise ValueError('nonempty complete response required')
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise MembershipSourceError('membership_response_json_invalid') from None

    included, excluded, seen = [], [], set()
    for row in rows:
        if type(row) is not dict:
            raise MembershipSourceError('membership_row_invalid')
        values = {key: _text(row.get(key)) for key in ('Code', 'Exchange', 'Type', 'Name', 'Country', 'Currency')}
        isin = row.get('Isin')
        if isin is not None:
            isin = _text(isin)
        if values['Type'] not in KNOWN_TYPES or values['Exchange'] not in KNOWN_EXCHANGES:
            raise MembershipSourceError('membership_vocabulary_unknown')
        if values['Code'] in seen:
            raise MembershipSourceError('membership_code_conflict')
        seen.add(values['Code'])
        symbol = SourceSymbol(values['Code'], values['Exchange'], values['Type'], values['Name'],
                              values['Country'], values['Currency'], isin)
        if common([row]):  # Reuse the existing approved filter, never its cache population.
            included.append(symbol)
        else:
            excluded.append(ExcludedSymbol(symbol, 'not_common_stock' if values['Type'] != 'Common Stock'
                                           else 'outside_primary_exchanges'))
    if not included:
        raise MembershipSourceError('membership_primary_common_empty')
    key = lambda symbol: (symbol.exchange, symbol.provider_code)
    return ParsedMembership(as_of, started_at, completed_at, raw, 'sha256:' + hashlib.sha256(raw).hexdigest(),
                            POLICY_VERSION, len(rows), tuple(sorted(included, key=key)),
                            tuple(sorted(excluded, key=lambda item: key(item.symbol))))
