"""Same-day qualification facts, without IO, formal registration or MACD.

The trusted price intake must separately prove complete available history for
every listing. Neither RepositoryRead nor a caller's membership list proves
provider/calendar coverage. This internal seam is not a public capability or
a substitute for the future production source-evidence integration.
"""
from typing import Mapping

from services.contracts.market_data import (
    normalize_forward_universe_members, normalize_universe_qualifications, require_date,
)
from services.contracts.validation import ContractError
from services.gates.baseline import (
    price_complete, history_length_passed, minimum_price_passed, dollar_volume_passed,
)
from services.market_data.normalization import bars_fingerprint, validate_adjusted_rows
from services.market_data.repository import RepositoryRead


def build_same_day_qualifications(*, as_of, members, reads, complete_history_instruments):
    """Return detached original-contract facts, or fail the entire batch.

    complete_history_instruments is supplied only after trusted intake has
    checked provider completeness, listing coverage and the trading calendar;
    it must never come from CLI, HTTP bodies or inferred row counts.
    """
    as_of = require_date(as_of, "as_of")
    members = normalize_forward_universe_members(members)
    ids = {member["instrument_id"] for member in members}
    if not isinstance(reads, Mapping) or set(reads) != ids:
        raise ContractError("qualification needs exactly all member reads")
    if type(complete_history_instruments) not in (set, frozenset) or complete_history_instruments != ids:
        raise ContractError("qualification complete history evidence unavailable")
    result = []
    for member in members:
        if (member["listing_status"] != "active" or member["provider"] != "EODHD"
                or member["market"] != "US" or member["membership_effective_from"] > as_of):
            raise ContractError("qualification member is outside same-day active US input")
        instrument_id = member["instrument_id"]
        read = reads[instrument_id]
        if (not isinstance(read, RepositoryRead) or read.instrument_id != instrument_id
                or read.as_of != as_of):
            raise ContractError("qualification read identity or date differs")
        rows = validate_adjusted_rows(read.rows)
        if not price_complete(rows, as_of=as_of):
            raise ContractError("qualification same-day price unavailable")
        if bars_fingerprint(rows) != read.point_in_time_fingerprint:
            raise ContractError("qualification actual price fingerprint differs")
        facts = {
            "price_complete": True,
            "minimum_price_passed": minimum_price_passed(rows[-1]),
            "dollar_volume_passed": dollar_volume_passed(rows[-1]),
            "history_length_passed": history_length_passed(rows),
        }
        reasons = [reason for key, reason in (
            ("history_length_passed", "insufficient_history"),
            ("minimum_price_passed", "below_price_floor"),
            ("dollar_volume_passed", "below_liquidity_floor"),
        ) if not facts[key]]
        result.append({"instrument_id": instrument_id, "as_of": as_of, **facts,
                       "eligible": all(facts.values()),
                       "inclusion_reasons": [] if reasons else ["all-frozen-eligibility-checks-passed"],
                       "exclusion_reasons": reasons})
    return normalize_universe_qualifications(result)
