"""Pure M12 daily composition of the original M02--M09 producers.

No runtime route, source attestation, persistence, publication or activation is
created here. The production caller must supply independently acquired originals
and recheck current authorization before calling; synthetic originals are useful
for local wiring tests only. Returned original batches are the inventory handoff,
not a registered SourceInventory or a durable execution checkpoint.
"""

from dataclasses import dataclass
from typing import Any, Mapping

from services.context import ContextBatch, produce_market_industry_context
from services.contracts.configuration import _policy_objects
from services.contracts.validation import ContractError
from services.execution import TradePlanBatch, produce_trade_plans
from services.factors import (
    SupportEvidenceBatch, TechnicalEvidenceBatch,
    produce_support_evidence, produce_technical_evidence,
)
from services.gates import GateBatch, produce_gate_batch
from services.ledger import (
    EventLedgerBatch, produce_event_ledger_batch, produce_trade_plan_links,
)
from services.market_data import ShadowConsumerInput, prepare_shadow_consumer_input
from services.ranking import RankingRun, produce_versioned_ranking
from services.selectors import ModelAssessmentBatch, produce_model_assessments


@dataclass(frozen=True)
class DailyChain:
    """Original immutable outputs; no replacement business contract."""

    stock: ShadowConsumerInput
    etf: ShadowConsumerInput
    gates: GateBatch
    technical: TechnicalEvidenceBatch
    support: SupportEvidenceBatch
    models: ModelAssessmentBatch
    context: ContextBatch
    ranking: RankingRun
    events: EventLedgerBatch
    plans: TradePlanBatch
    plan_links: tuple[Mapping[str, Any], ...]


def produce_daily_chain(
    *, as_of, stock_snapshots, etf_snapshots, stock_reader, etf_reader,
    data_source, etf_registry, membership_registry, activation,
    generated_at, scan_batch_id,
) -> DailyChain:
    """Compose once, using explicit original 3.x inputs and fixed policies.

    An activation argument is validated by M07; it is not proof of current
    production permission. Never construct it from a caller's approval string.
    No next-day reads are allowed in the signal-day calculation. Execution
    continuation consumes the frozen ranking/support/events independently.
    """
    _policy_objects()  # Reuse the existing nine-policy content check.
    common = dict(mode="formal", as_of=as_of, generated_at=generated_at,
                  data_source=data_source)
    stock = prepare_shadow_consumer_input(
        consumer="factor_snapshot", snapshots=stock_snapshots,
        reader=stock_reader, **common,
    )
    etf = prepare_shadow_consumer_input(
        consumer="market_etf", snapshots=etf_snapshots, reader=etf_reader, **common,
    )
    # Existing M06 needs both snapshots, even for an empty gate batch. Do not
    # fabricate a snapshot or report a partially calculated day as publishable.
    if stock.market_snapshot_id is None or etf.market_snapshot_id is None:
        raise ContractError("daily chain requires original M02 market snapshots")
    gates = produce_gate_batch(stock, generated_at=generated_at,
                               scan_batch_id=scan_batch_id)
    shared = dict(gate_events=gates.events, generated_at=generated_at)
    technical = produce_technical_evidence(stock, **shared)
    support = produce_support_evidence(stock, technical_evidence=technical, **shared)
    models = produce_model_assessments(stock, technical_evidence=technical, **shared)
    context = produce_market_industry_context(
        stock, etf, technical_evidence=technical, model_assessments=models,
        etf_registry=etf_registry, membership_registry=membership_registry, **shared,
    )
    ranking = produce_versioned_ranking(
        technical_evidence=technical, model_assessments=models, contexts=context,
        ranking_role="authoritative", activation=activation, **shared,
    )
    plans = produce_trade_plans(ranking.snapshot, support, entry_reads={},
                               generated_at=generated_at)
    events = produce_event_ledger_batch(
        technical_evidence=technical, model_assessments=models, contexts=context,
        ranking_snapshot=ranking.snapshot, **shared,
    )
    links = produce_trade_plan_links(events, plans, generated_at=generated_at)
    return DailyChain(stock, etf, gates, technical, support, models, context,
                      ranking, events, plans, links)
