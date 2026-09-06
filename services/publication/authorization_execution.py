"""Fixed Python job execution over a future authenticated coordinator transport.

This module does not authenticate a supplied transport. Runtime construction,
OIDC, lease renewal, immutable checkout and the protected workflow remain with
the trusted job adapter; never expose this as an arbitrary transport RPC.
"""

from copy import deepcopy
import hashlib
import re
from typing import Protocol

from services.contracts.validation import ContractError, publication_validation_input
from services.publication.authorization_validation import authorization_validation_output


class AuthorizationJobTransport(Protocol):
    def prepare(self) -> dict: ...

    def return_result(self, dispatch_id: str, lease_token: dict, result_bytes: bytes) -> bytes: ...


def execute_authorization_validation(transport: AuthorizationJobTransport) -> bytes:
    """Fetch our input, run the one validator, and return its unmodified output.

    The return is the transport's raw response, not an authorization-success
    assertion. Exceptions are propagated without retry or fabricated receipts.
    """
    prepared = deepcopy(transport.prepare())
    fields = {"dispatch_id", "lease_token", "input_sha256", "input_size_bytes", "input_bytes"}
    if type(prepared) is not dict or set(prepared) != fields:
        raise ContractError("validation job preparation fields differ")
    uuid = r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}"
    lease = prepared["lease_token"]
    if (not isinstance(prepared["dispatch_id"], str) or not re.fullmatch(uuid, prepared["dispatch_id"]) or
            type(lease) is not dict or set(lease) != {"epoch", "fence"} or
            not isinstance(lease["epoch"], str) or not re.fullmatch(uuid, lease["epoch"]) or
            type(lease["fence"]) is not int or lease["fence"] < 1):
        raise ContractError("validation job dispatch or lease handle is invalid")
    raw = prepared["input_bytes"]
    if (type(raw) is not bytes or type(prepared["input_size_bytes"]) is not int or prepared["input_size_bytes"] != len(raw) or
            prepared["input_sha256"] != "sha256:" + hashlib.sha256(raw).hexdigest()):
        raise ContractError("validation job input bytes differ from preparation")
    ticket = publication_validation_input(raw)["validation_ticket"]
    if not isinstance(ticket, dict) or lease != {"epoch": ticket.get("epoch"), "fence": ticket.get("fence")}:
        raise ContractError("validation job lease differs from its input ticket")
    result = authorization_validation_output(raw)
    # No caller-provided stdout, executable, arguments or alternate validator.
    response = transport.return_result(prepared["dispatch_id"], lease, result)
    if type(response) is not bytes:
        raise ContractError("validation job transport response must be raw bytes")
    return response
