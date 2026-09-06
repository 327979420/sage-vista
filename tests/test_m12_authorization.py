"""M12 approval contracts: synthetic trusted evidence, never live credentials."""

from copy import deepcopy
import unittest

from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import ContractError, validate_contract, validate_contracts
from services.publication.authorization import build_publication_authorization

TIME = "2026-09-06T00:00:00Z"


def ref(name):
    return {"id": name, "content_fingerprint": canonical_fingerprint({"name": name})}


def approval():
    return {
        "request": {
            "action": "grant", "prior_authorization_ref": None,
            "config_ref": ref("configuration"), "code_commit": "a" * 40,
            "publication_mode": "research_only", "scope": "complex_multifactor_main",
            "effective_from": "2026-09-08", "valid_until": None,
            "permissions": ["prepare", "publish", "notify", "rollback"],
            "reason": "approved research release",
        },
        "approver_id": "reviewer-1", "approval_evidence_ref": ref("environment-approval"),
        "job": {"repository_id": "repository-1", "workflow_ref": "repo/workflow@refs/heads/main",
                "workflow_commit": "b" * 40, "run_id": "run-1", "run_attempt": 1, "environment": "production"},
        "history": [],
    }


def authorization_ref(payload):
    return {"id": payload["authorization_id"], "content_fingerprint": payload["content_fingerprint"]}


def resign(payload):
    body = {k: v for k, v in payload.items() if k not in {
        "authorization_id", "content_fingerprint", "generated_at",
    }}
    fingerprint = canonical_fingerprint(body)
    payload.update(content_fingerprint=fingerprint, authorization_id="publication-authorization:" + fingerprint)
    return payload


class PublicationAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.evidence = approval()
        self.payload = build_publication_authorization(self.evidence, generated_at=TIME)

    def validate(self, payload, evidence=None):
        validate_contract("PublicationAuthorization", payload,
                          publication_authorization_evidence=self.evidence if evidence is None else evidence)

    def revoke_evidence(self):
        evidence = deepcopy(self.evidence)
        evidence["request"].update(action="revoke", prior_authorization_ref=authorization_ref(self.payload),
                                   permissions=[], reason="withdraw publication approval")
        evidence["history"] = [self.payload]
        return evidence

    def test_grant_and_revoke_roundtrip(self):
        self.validate(self.payload)
        evidence = self.revoke_evidence()
        revoked = build_publication_authorization(evidence, generated_at=TIME)
        self.validate(revoked, evidence)
        self.assertEqual(revoked["prior_authorization_ref"], authorization_ref(self.payload))
        self.assertEqual(revoked["permissions"], [])

    def test_public_entry_fails_without_trusted_evidence(self):
        with self.assertRaises(ContractError):
            validate_contract("PublicationAuthorization", self.payload)

    def test_resealed_approver_job_or_receipt_cannot_replace_trusted_evidence(self):
        candidates = []
        for key, value in (("approver_id", "attacker"), ("approval_evidence_ref", ref("forged"))):
            payload = deepcopy(self.payload)
            payload[key] = value
            candidates.append(payload)
        for key in self.payload["job"]:
            payload = deepcopy(self.payload)
            payload["job"][key] = 2 if key == "run_attempt" else ("c" * 40 if key == "workflow_commit" else "other")
            candidates.append(payload)
        for payload in candidates:
            with self.subTest(payload=payload), self.assertRaises(ContractError):
                self.validate(resign(payload))

    def test_resealed_code_config_date_and_reason_must_match_approval(self):
        for key, value in (("code_commit", "c" * 40), ("config_ref", ref("new-config")),
                           ("effective_from", "2026-09-09"), ("valid_until", "2026-09-10"), ("reason", "changed")):
            payload = deepcopy(self.payload)
            payload[key] = value
            with self.subTest(key=key), self.assertRaises(ContractError):
                self.validate(resign(payload))

    def test_scope_mode_and_strategy_permissions_fail_even_in_injected_request(self):
        for key, value in (("scope", "strategy"), ("publication_mode", "trading"),
                           ("permissions", ["strategy_active"]), ("permissions", []),
                           ("permissions", ["prepare", "publish", "notify", "rollback", "notify"])):
            evidence = deepcopy(self.evidence)
            evidence["request"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ContractError):
                build_publication_authorization(evidence, generated_at=TIME)

    def test_revoke_requires_same_code_config_and_immediate_predecessor(self):
        for key, value in (("code_commit", "c" * 40), ("config_ref", ref("changed")),
                           ("prior_authorization_ref", None), ("prior_authorization_ref", ref("stale")),
                           ("permissions", ["prepare"])):
            evidence = self.revoke_evidence()
            evidence["request"][key] = value
            with self.subTest(key=key), self.assertRaises(ContractError):
                build_publication_authorization(evidence, generated_at=TIME)

    def test_history_cannot_be_omitted_truncated_reordered_or_forked(self):
        evidence = self.revoke_evidence()
        revoked = build_publication_authorization(evidence, generated_at=TIME)
        request = deepcopy(self.evidence)
        request["request"]["prior_authorization_ref"] = authorization_ref(revoked)
        request["history"] = [self.payload, revoked]
        renewed = build_publication_authorization(request, generated_at=TIME)
        self.validate(renewed, request)
        for history in ([], [revoked], [revoked, self.payload], [self.payload, self.payload], [self.payload]):
            bad = deepcopy(request)
            bad["history"] = history
            with self.subTest(history=history), self.assertRaises(ContractError):
                build_publication_authorization(bad, generated_at=TIME)

    def test_unsealed_history_mutation_is_rejected(self):
        evidence = deepcopy(self.revoke_evidence())
        evidence["history"][0]["reason"] = "rewritten"
        with self.assertRaises(ContractError):
            build_publication_authorization(evidence, generated_at=TIME)

    def test_unknown_fields_and_versions_rejected(self):
        for key, value in (("schema_version", "1.0.1"), ("schema_version", "2.0.0"), ("extra", None)):
            payload = deepcopy(self.payload)
            payload[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ContractError):
                self.validate(resign(payload))
        evidence = deepcopy(self.evidence)
        evidence["request"]["extra"] = "ignored?"
        with self.assertRaises(ContractError):
            build_publication_authorization(evidence, generated_at=TIME)

    def test_job_uint_and_exact_fields(self):
        for value in (True, -1, 1.5, "1"):
            evidence = deepcopy(self.evidence)
            evidence["job"]["run_attempt"] = value
            with self.subTest(value=value), self.assertRaises(ContractError):
                build_publication_authorization(evidence, generated_at=TIME)
        evidence = deepcopy(self.evidence)
        evidence["job"]["token"] = "must not be stored"
        with self.assertRaises(ContractError):
            build_publication_authorization(evidence, generated_at=TIME)

    def test_invalid_dates_commits_and_blank_identity(self):
        for key, value in (("effective_from", "2026-02-30"), ("valid_until", "2026-09-01"),
                           ("code_commit", "ABC123"), ("reason", " "), ("action", "activate")):
            evidence = deepcopy(self.evidence)
            evidence["request"][key] = value
            with self.subTest(key=key), self.assertRaises(ContractError):
                build_publication_authorization(evidence, generated_at=TIME)
        evidence = deepcopy(self.evidence)
        evidence["approver_id"] = True
        with self.assertRaises(ContractError):
            build_publication_authorization(evidence, generated_at=TIME)

    def test_date_window_inclusive_and_no_expiry_allowed(self):
        evidence = deepcopy(self.evidence)
        evidence["request"]["valid_until"] = evidence["request"]["effective_from"]
        self.validate(build_publication_authorization(evidence, generated_at=TIME), evidence)
        self.assertIsNone(self.payload["valid_until"])

    def test_identity_ignores_generation_time_but_not_semantics(self):
        later = build_publication_authorization(self.evidence, generated_at="2026-09-07T00:00:00Z")
        self.assertEqual(later["authorization_id"], self.payload["authorization_id"])
        evidence = deepcopy(self.evidence)
        evidence["request"]["reason"] = "another decision"
        self.assertNotEqual(build_publication_authorization(evidence, generated_at=TIME)["authorization_id"], self.payload["authorization_id"])
        for key in ("authorization_id", "content_fingerprint"):
            payload = deepcopy(self.payload)
            payload[key] = "fake"
            with self.assertRaises(ContractError):
                self.validate(payload)

    def test_builder_does_not_alias_or_mutate_evidence(self):
        before = deepcopy(self.evidence)
        payload = build_publication_authorization(self.evidence, generated_at=TIME)
        payload["job"]["run_id"] = "changed"
        payload["config_ref"]["id"] = "changed"
        self.assertEqual(self.evidence, before)

    def test_collection_uses_same_evidence_and_duplicate_rules(self):
        validate_contracts([("PublicationAuthorization", self.payload)], publication_authorization_evidence=self.evidence)
        with self.assertRaises(ContractError):
            validate_contracts([("PublicationAuthorization", self.payload)])
        with self.assertRaises(ContractError):
            validate_contracts([("PublicationAuthorization", self.payload)] * 2, publication_authorization_evidence=self.evidence)
        payload = deepcopy(self.payload)
        payload["approver_id"] = "forged"
        with self.assertRaises(ContractError):
            validate_contracts([("PublicationAuthorization", resign(payload))], publication_authorization_evidence=self.evidence)


if __name__ == "__main__":
    unittest.main()
