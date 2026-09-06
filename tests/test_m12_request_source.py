"""Frozen source semantics only; injected source evidence is not authentication."""

from copy import deepcopy
import hashlib
import json
import unittest

from services.contracts.validation import (
    ContractError, publication_request_body, validate_contract, validate_contracts,
)
from services.publication.authorization import build_publication_authorization
from test_m12_authorization import TIME, approval, authorization_ref, ref, resign

CONTROL = "c" * 40


def source_bytes(raw, commit=CONTROL):
    return {
        "source_commit": commit, "path": "config/publication-authorization-request.json",
        "blob_sha": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest(),
        "bytes": raw, "sha256": "sha256:" + hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw),
    }


def frozen(evidence=None, commit=CONTROL):
    evidence = deepcopy(approval() if evidence is None else evidence)
    evidence["source_commit"] = commit
    raw = (json.dumps(evidence["request"], ensure_ascii=False, indent=2) + "\n").encode()
    evidence["request_source"] = source_bytes(raw, commit)
    return evidence


class RequestSourceTests(unittest.TestCase):
    def test_raw_request_and_existing_authorization_share_exact_semantics_and_identity(self):
        evidence = frozen()
        self.assertEqual(publication_request_body(evidence["request_source"], source_commit=CONTROL), evidence["request"])
        sourced = build_publication_authorization(evidence, generated_at=TIME)
        original = build_publication_authorization(approval(), generated_at=TIME)
        self.assertEqual(sourced, original)
        validate_contract("PublicationAuthorization", sourced, publication_authorization_evidence=evidence)
        validate_contracts([("PublicationAuthorization", sourced)], publication_authorization_evidence=evidence)

    def test_revoke_retains_business_target_while_control_commit_changes(self):
        first_evidence = frozen()
        first = build_publication_authorization(first_evidence, generated_at=TIME)
        evidence = approval()
        evidence["request"].update(action="revoke", permissions=[], prior_authorization_ref=authorization_ref(first))
        evidence["history"] = [first]
        evidence = frozen(evidence, commit="d" * 40)
        revoked = build_publication_authorization(evidence, generated_at=TIME)
        self.assertEqual(revoked["code_commit"], first["code_commit"])
        self.assertNotEqual(revoked["code_commit"], evidence["source_commit"])
        self.assertEqual(revoked["permissions"], [])

    def test_each_valid_field_substitution_rejected_at_builder_single_and_collection(self):
        original = frozen()
        for field, value in (("code_commit", "e" * 40), ("config_ref", ref("changed")),
                             ("effective_from", "2026-09-09"), ("valid_until", "2026-09-10"), ("reason", "changed")):
            evidence = deepcopy(original)
            evidence["request"][field] = value
            payload = build_publication_authorization(original, generated_at=TIME)
            payload[field] = value
            payload = resign(payload)
            for operation in (
                lambda: build_publication_authorization(evidence, generated_at=TIME),
                lambda: validate_contract("PublicationAuthorization", payload, publication_authorization_evidence=evidence),
                lambda: validate_contracts([("PublicationAuthorization", payload)], publication_authorization_evidence=evidence),
            ):
                with self.subTest(field=field), self.assertRaises(ContractError):
                    operation()

    def test_all_fields_required_and_unknown_keys_rejected(self):
        original = approval()["request"]
        for field in original:
            request = deepcopy(original)
            del request[field]
            with self.subTest(field=field), self.assertRaises(ContractError):
                publication_request_body(source_bytes(json.dumps(request).encode()), source_commit=CONTROL)
        for field in ("schema_version", "approver_id", "source_commit", "authorization_id", "extra"):
            request = {**original, field: "unapproved"}
            with self.subTest(field=field), self.assertRaises(ContractError):
                publication_request_body(source_bytes(json.dumps(request).encode()), source_commit=CONTROL)

    def test_illegal_scope_permissions_refs_dates_and_target_are_rejected_in_raw_bytes(self):
        for field, value in (("scope", "strategy"), ("publication_mode", "trading"),
                             ("permissions", ["strategy_active"]), ("permissions", ["prepare"]),
                             ("permissions", ["prepare", "publish", "notify", "rollback", "notify"]),
                             ("effective_from", "2026-02-30"), ("valid_until", "2026-01-01"),
                             ("config_ref", None), ("prior_authorization_ref", True),
                             ("code_commit", "main"), ("reason", " "), ("action", "activate")):
            request = {**approval()["request"], field: value}
            with self.subTest(field=field, value=value), self.assertRaises(ContractError):
                publication_request_body(source_bytes(json.dumps(request).encode()), source_commit=CONTROL)

    def test_json_duplicate_keys_nonfinite_utf8_and_nonobjects_are_rejected(self):
        raw = frozen()["request_source"]["bytes"]
        for candidate in (b"[]", b"null", b"not JSON", b"\xff", raw.replace(b'"action": "grant"', b'"action":"revoke","action":"grant"'),
                          raw.replace(b'"reason": "approved research release"', b'"reason": NaN'),
                          raw.replace(b'"reason": "approved research release"', b'"reason": 1e999')):
            with self.subTest(raw=candidate[:50]), self.assertRaises(ContractError):
                publication_request_body(source_bytes(candidate), source_commit=CONTROL)

    def test_source_commit_path_hash_length_and_blob_must_match_exact_original(self):
        source = frozen()["request_source"]
        for field, value in (("source_commit", "d" * 40), ("path", "elsewhere.json"),
                             ("sha256", "sha256:" + "e" * 64), ("blob_sha", "e" * 40),
                             ("size_bytes", True), ("size_bytes", len(source["bytes"]) + 1),
                             ("bytes", bytearray(source["bytes"])), ("bytes", source["bytes"] + b"\n")):
            bad = {**source, field: value}
            with self.subTest(field=field), self.assertRaises(ContractError):
                publication_request_body(bad, source_commit=CONTROL)
        for raw in (b"", b" " * 65_537):
            with self.assertRaises(ContractError):
                publication_request_body(source_bytes(raw), source_commit=CONTROL)

    def test_partial_source_context_and_unknown_metadata_cannot_bypass_binding(self):
        for missing in ("request_source", "source_commit"):
            evidence = frozen()
            del evidence[missing]
            with self.assertRaises(ContractError):
                build_publication_authorization(evidence, generated_at=TIME)
        evidence = frozen()
        evidence["request_source"]["trusted"] = True
        with self.assertRaises(ContractError):
            build_publication_authorization(evidence, generated_at=TIME)

    def test_source_binding_does_not_relax_direct_predecessor_or_revocation_target(self):
        first = build_publication_authorization(frozen(), generated_at=TIME)
        for field, value in (("prior_authorization_ref", ref("wrong")), ("code_commit", "e" * 40),
                             ("config_ref", ref("other")), ("permissions", ["publish"])):
            evidence = approval()
            evidence["request"].update(action="revoke", permissions=[], prior_authorization_ref=authorization_ref(first))
            evidence["request"][field] = value
            evidence["history"] = [first]
            with self.subTest(field=field), self.assertRaises(ContractError):
                build_publication_authorization(frozen(evidence), generated_at=TIME)

    def test_equal_semantic_bytes_have_distinct_raw_digest_and_no_aliasing(self):
        evidence = frozen()
        source = evidence["request_source"]
        compact = source_bytes(json.dumps(evidence["request"], separators=(",", ":")).encode())
        self.assertNotEqual(source["sha256"], compact["sha256"])
        self.assertEqual(publication_request_body(source, source_commit=CONTROL), publication_request_body(compact, source_commit=CONTROL))
        parsed = publication_request_body(source, source_commit=CONTROL)
        parsed["permissions"].append("strategy_active")
        self.assertEqual(publication_request_body(source, source_commit=CONTROL)["permissions"], approval()["request"]["permissions"])


if __name__ == "__main__":
    unittest.main()
