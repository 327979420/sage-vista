"""Append-only, shadow-only storage for M09 event-ledger records."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import AbstractSet, Any, Callable, Mapping

from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import ContractError
from services.market_data.storage import require_shadow_root

from .producer import (
    validate_human_review,
    validate_machine_link,
    validate_opportunity_event,
)


_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            _plain(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode() + b"\n"
    except (TypeError, ValueError) as exc:
        raise ContractError("M09 ledger record must be canonical JSON") from exc


def _id_digest(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{field} must be a stable content-addressed ID")
    digest = value.rsplit(":", 1)[-1]
    if not _DIGEST.fullmatch(digest):
        raise ContractError(f"{field} must end in a lowercase SHA-256 digest")
    return digest


def _review_subject_digest(review: Mapping[str, Any]) -> str:
    reference = review.get("subject_reference")
    if not isinstance(reference, Mapping):
        raise ContractError("human review subject_reference must be an object")
    if review.get("subject_type") == "event":
        return _id_digest(reference.get("event_id"), field="subject_reference.event_id")
    return _id_digest(
        canonical_fingerprint(_plain(reference)),
        field="subject_reference fingerprint",
    )


def _reject_json_constant(value: str) -> None:
    raise ContractError(f"stored M09 record contains non-finite JSON: {value}")


class EventLedgerStore:
    """Atomically create immutable M09 records under an approved shadow root."""

    def __init__(
        self,
        root: str | Path,
        *,
        workspace_root: str | Path | None = None,
        known_ranking_exclusions: AbstractSet[tuple[str, str]] = frozenset(),
        known_approval_refs: AbstractSet[str] = frozenset(),
    ) -> None:
        self.root = require_shadow_root(root, workspace_root=workspace_root)
        self.known_ranking_exclusions = frozenset(known_ranking_exclusions)
        self.known_approval_refs = frozenset(known_approval_refs)

    def _event_record(self, event_id: str) -> Mapping[str, Any] | None:
        digest = _id_digest(event_id, field="event_id")
        paths = list((self.root / "events").glob(f"*/{digest}.json"))
        if len(paths) > 1:
            raise ContractError("M09 ledger contains duplicate event-root files")
        if not paths:
            return None
        existing = self._load_existing(paths[0], validator=validate_opportunity_event)
        if existing.get("event_id") != event_id:
            raise ContractError("M09 event-root file does not match its requested identity")
        return existing

    def _validate_review_for_store(self, review: Mapping[str, Any]) -> None:
        reference = review.get("subject_reference")
        event_ids: set[str] = set()
        if isinstance(reference, Mapping) and review.get("subject_type") == "event":
            event_id = str(reference.get("event_id"))
            if self._event_record(event_id) is not None:
                event_ids.add(event_id)
        validate_human_review(
            review,
            known_event_ids=event_ids,
            known_ranking_exclusions=self.known_ranking_exclusions,
            known_approval_refs=self.known_approval_refs,
            require_known_subject=True,
        )

    @staticmethod
    def _load_existing(
        path: Path, *, validator: Callable[[Mapping[str, Any]], None]
    ) -> Mapping[str, Any]:
        try:
            mode = path.lstat().st_mode
        except OSError as exc:
            raise ContractError("existing M09 record cannot be inspected") from exc
        if not stat.S_ISREG(mode):
            raise ContractError("existing M09 record must be a regular file")
        try:
            payload = json.loads(
                path.read_bytes(), parse_constant=_reject_json_constant
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ContractError("existing M09 record is not valid JSON") from exc
        if not isinstance(payload, Mapping):
            raise ContractError("existing M09 record must be an object")
        validator(payload)
        return payload

    def _write(
        self,
        payload: Mapping[str, Any],
        *,
        target: Path,
        validator: Callable[[Mapping[str, Any]], None],
        id_field: str,
        fingerprint_field: str,
    ) -> Path:
        validator(payload)
        content = _canonical_bytes(payload)

        if target.exists() or target.is_symlink():
            existing = self._load_existing(target, validator=validator)
            if (
                existing.get(id_field) == payload.get(id_field)
                and existing.get(fingerprint_field) == payload.get(fingerprint_field)
            ):
                return target
            raise ContractError("immutable M09 record already exists with different content")

        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=target.name + ".", suffix=".tmp", dir=target.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())

            try:
                staged = json.loads(
                    temporary.read_bytes(), parse_constant=_reject_json_constant
                )
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ContractError("staged M09 record is not valid JSON") from exc
            if not isinstance(staged, Mapping):
                raise ContractError("staged M09 record must be an object")
            validator(staged)

            try:
                os.link(temporary, target)
            except FileExistsError:
                existing = self._load_existing(target, validator=validator)
                if (
                    existing.get(id_field) != payload.get(id_field)
                    or existing.get(fingerprint_field) != payload.get(fingerprint_field)
                ):
                    raise ContractError("concurrent immutable M09 record conflict")

            directory_fd = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return target
        finally:
            if temporary.exists():
                temporary.unlink()

    def write_event(self, event: Mapping[str, Any]) -> Path:
        validate_opportunity_event(event)
        target = (
            self.root
            / "events"
            / str(event["signal_date"])
            / (_id_digest(event["event_id"], field="event_id") + ".json")
        )
        return self._write(
            event,
            target=target,
            validator=validate_opportunity_event,
            id_field="event_id",
            fingerprint_field="event_content_fingerprint",
        )

    def write_machine_link(self, link: Mapping[str, Any]) -> Path:
        validate_machine_link(link)
        event = self._event_record(str(link["event_id"]))
        if event is None:
            raise ContractError("M09 machine link cannot exist before its event root")
        if (
            link["instrument_id"] != event["instrument_id"]
            or link["signal_date"] != event["signal_date"]
        ):
            raise ContractError("M09 machine link crosses its stored event root")
        reference = link["source_reference"]
        if link["link_type"] == "trade_plan_decision" and (
            reference.get("ranking_snapshot_id") != event["ranking_snapshot_id"]
            or reference.get("score_result_id") != event["score_result_id"]
        ):
            raise ContractError("M08 link does not belong to the stored ranking event")
        if link["link_type"] == "exit_state":
            plan_id = reference.get("plan_id")
            linked_plan = False
            link_root = self.root / "machine-links" / _id_digest(link["event_id"], field="event_id")
            for path in link_root.glob("*.json"):
                existing = self._load_existing(path, validator=validate_machine_link)
                if (
                    existing.get("link_type") == "trade_plan_decision"
                    and existing.get("source_reference", {}).get("plan_id") == plan_id
                ):
                    linked_plan = True
                    break
            if not linked_plan:
                raise ContractError("ExitState link cannot precede its TradePlan link")
        target = (
            self.root
            / "machine-links"
            / _id_digest(link["event_id"], field="event_id")
            / (_id_digest(link["link_id"], field="link_id") + ".json")
        )
        return self._write(
            link,
            target=target,
            validator=validate_machine_link,
            id_field="link_id",
            fingerprint_field="link_content_fingerprint",
        )

    def write_human_review(self, review: Mapping[str, Any]) -> Path:
        self._validate_review_for_store(review)
        target = (
            self.root
            / "human-reviews"
            / _review_subject_digest(review)
            / (_id_digest(review["review_id"], field="review_id") + ".json")
        )
        return self._write(
            review,
            target=target,
            validator=self._validate_review_for_store,
            id_field="review_id",
            fingerprint_field="review_content_fingerprint",
        )


__all__ = ["EventLedgerStore"]
