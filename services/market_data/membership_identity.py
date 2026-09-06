"""Replay trusted complete observation history into existing M02 identities.

No downloads, persistence, qualified UniverseSnapshot, or permission issuance.
The coordinator must read the complete frozen index and all original bytes;
caller-selected observations cannot prove an epoch's beginning or continuity.
"""
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from services.contracts.market_data import (
    canonical_fingerprint, observed_instrument_id, normalize_forward_universe_members,
    normalize_forward_membership_evidence,
)
from services.contracts.validation import ContractError, membership_observation_history


@dataclass(frozen=True)
class ObservedMembership:
    as_of: str
    members: tuple[Mapping, ...]
    membership_evidence: Mapping
    source_history: tuple[Mapping, ...]


def build_observed_membership(evidence, *, as_of) -> ObservedMembership:
    """Assign no IPO dates, infer no relisting from names, and never merge ISINs.

    Successful observations alone advance presence. Failed acquisition days
    must stay in the audit archive and are absent from this success index.
    """
    observations = membership_observation_history(evidence, as_of=as_of)
    active = {}
    for parsed, archive in observations:
        next_active = {}
        for symbol in parsed.included:
            key = (symbol.exchange, symbol.provider_code)
            prior = active.get(key)
            known_isin = prior['isin'] if prior else None
            if known_isin and symbol.isin and known_isin != symbol.isin:
                raise ContractError('continuous listing ISIN conflicts; source review required')
            next_active[key] = {
                'epoch': prior['epoch'] if prior else parsed.as_of,
                'origin': prior['origin'] if prior else archive['key'],
                'isin': symbol.isin or known_isin,
                'isin_origin': archive['key'] if symbol.isin else (prior['isin_origin'] if prior else None),
            }
        # A missing date is not an empty source. Absence only follows a fully
        # restored successful observation; later reappearance gets a new epoch.
        active = next_active
    parsed, archive = observations[-1]
    members = []
    for symbol in parsed.included:
        state = active[(symbol.exchange, symbol.provider_code)]
        identity = dict(provider='EODHD', market='US', exchange=symbol.exchange,
                        provider_code=symbol.provider_code, observed_listing_epoch=state['epoch'])
        members.append({**identity, 'instrument_id': observed_instrument_id(**identity),
            'symbol': symbol.provider_code, 'tier': 'main', 'listing_status': 'active',
            'membership_source': archive['key'] + ':' + parsed.policy_version,
            'membership_effective_from': state['epoch'],
            'identity_source': 'observed_listing_origin=' + state['origin'] +
                ';not_ipo_date;isin_observation=' + (state['isin_origin'] or 'unavailable'),
            **({'isin': state['isin']} if state['isin'] else {})})
    members = normalize_forward_universe_members(members)
    source = normalize_forward_membership_evidence({
        'source_id': archive['key'], 'source_as_of': as_of, 'complete': True,
        'member_count': len(members), 'content_fingerprint': canonical_fingerprint(members),
    }, as_of=as_of, members=members)
    return ObservedMembership(as_of, tuple(MappingProxyType(item) for item in members),
        MappingProxyType(source), tuple(MappingProxyType(item) for _, item in observations))
