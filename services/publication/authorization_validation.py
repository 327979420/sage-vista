"""Internal Python validation artifact producer; no registration or credentials.

The byte receipt is not a signature. A coordinator must bind the exact input to
its dispatch record and authenticate the returning pinned workflow before use.
"""

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sys
import time
from typing import Callable

from services.contracts.validation import ContractError, publication_approval_archive_body, publication_validation_input
from services.publication.authorization import build_publication_authorization_for_ticket


def _bytes(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _time(clock: Callable[[], int]) -> datetime:
    now = clock()
    if type(now) is not int:
        raise ContractError("validation clock must return integer milliseconds")
    try:
        return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=now)
    except OverflowError as exc:
        raise ContractError("validation clock is out of range") from exc


def validate_authorization_input(raw: bytes, *, clock: Callable[[], int] = lambda: time.time_ns() // 1_000_000) -> dict[str, bytes]:
    """Emit success artifacts only after the single mandatory contract path."""
    started = _time(clock)
    value = publication_validation_input(raw)
    ticket, archive = value["validation_ticket"], value["approval_archive"]
    publication_approval_archive_body(archive, value["approval_evidence_ref"])
    bundle = json.loads(archive["bundle_bytes"])
    observed = datetime.fromisoformat(bundle["observed_at"].replace("Z", "+00:00"))
    authorization = build_publication_authorization_for_ticket(
        archive, value["approval_evidence_ref"], ticket, value["history_bytes"],
        # Stable across retries/tickets for the same archived approval. The
        # actual computation time belongs in the validation receipt below.
        generated_at=observed.isoformat(timespec="seconds").replace("+00:00", "Z"),
    )
    # All fields below have passed the unique archive/ticket validation above.
    # This only rejects an expired computation; it cannot prove a live DO lease.
    identity = bundle["identity"]
    completed = _time(clock)
    parse = lambda stamp: datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    earliest = max(parse(ticket["prepared_at"]), observed, epoch + timedelta(seconds=identity["issued_at"]))
    latest = min(parse(ticket["expires_at"]), epoch + timedelta(seconds=identity["expires_at"]))
    if not earliest <= started <= completed < latest:
        raise ContractError("authorization validation computation is outside its frozen time window")
    authorization_bytes = _bytes(authorization)
    receipt = {"protocol": "m12-authorization-validation/1", "verdict": "valid",
               "validated_at": completed.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
               "input_sha256": _sha(raw), "input_size_bytes": len(raw),
               "ticket_id": ticket["ticket_id"], "ticket_sha256": _sha(_bytes(ticket)),
               "approval_evidence_ref": value["approval_evidence_ref"],
               "authorization_ref": {"id": authorization["authorization_id"], "content_fingerprint": authorization["content_fingerprint"]},
               "authorization_archive": {"key": "authority/" + authorization["content_fingerprint"][7:] + ".json",
                                         "sha256": _sha(authorization_bytes), "size_bytes": len(authorization_bytes)}}
    return {"receipt_bytes": _bytes(receipt), "authorization_bytes": authorization_bytes}


def authorization_validation_output(raw: bytes) -> bytes:
    """The single stdout encoding used by both the CLI and the fixed job."""
    result = validate_authorization_input(raw)
    return _bytes({key.replace("_bytes", "_base64"): base64.b64encode(value).decode("ascii")
                   for key, value in result.items()}) + b"\n"


def main() -> int:
    try:
        output = authorization_validation_output(sys.stdin.buffer.read())
    except ContractError:
        # Do not echo private request bytes or provide a success-shaped failure.
        print("authorization validation failed", file=sys.stderr)
        return 1
    sys.stdout.buffer.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
