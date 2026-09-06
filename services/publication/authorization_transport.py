"""Internal Actions-to-coordinator HTTPS transport; no workflow activation.

Runtime configuration and the opener are trusted dependencies, never request
parameters. The server must still verify OIDC and all persistent bindings.
"""

import base64
import binascii
from copy import deepcopy
from contextlib import suppress
import hashlib
import json
import re
import ssl
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.error import HTTPError
from urllib.request import HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener


PROTOCOL = "m12-authorization-job/1"
AUDIENCE = "sage-vista-publication"
PREPARE_LIMIT = 32 * 1024 * 1024
UUID = re.compile(r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}")


class AuthorizationTransportError(RuntimeError):
    """Sanitized transport failure; never embeds credentials or response bodies."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
        if not isinstance(value, dict):
            raise ValueError("not an object")
        json.dumps(value, allow_nan=False)  # Includes exponent overflow.
        return value
    except (UnicodeError, ValueError, TypeError):
        raise AuthorizationTransportError("validation transport JSON invalid") from None


def _body(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _url(value):
    try:
        if not isinstance(value, str) or re.search(r"[\s\\\x00-\x1f\x7f]", value):
            raise ValueError("invalid URL")
        parsed = urlsplit(value)
        host = parsed.hostname
        if (parsed.scheme != "https" or parsed.netloc != host or parsed.fragment or not host or
                not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}", host)):
            raise ValueError("noncanonical HTTPS URL")
        return parsed
    except (ValueError, TypeError):
        raise AuthorizationTransportError("validation transport URL invalid") from None


def _lease(value):
    if (type(value) is not dict or set(value) != {"epoch", "fence"} or
            not isinstance(value["epoch"], str) or not UUID.fullmatch(value["epoch"]) or
            type(value["fence"]) is not int or not 1 <= value["fence"] <= 2**53 - 1):
        raise AuthorizationTransportError("validation transport lease invalid")
    return dict(value)


class AuthorizationHttpsTransport:
    def __init__(self, coordinator_origin: str, actions_environment: dict, *, opener=None):
        origin = _url(coordinator_origin)
        if origin.path not in ("", "/") or origin.query:
            raise AuthorizationTransportError("validation coordinator must be a fixed origin")
        environment = dict(actions_environment)
        if environment.get("GITHUB_ACTIONS") != "true":
            raise AuthorizationTransportError("validation transport requires Actions runtime")
        request = _url(environment.get("ACTIONS_ID_TOKEN_REQUEST_URL"))
        if not request.hostname.endswith(".actions.githubusercontent.com"):
            raise AuthorizationTransportError("validation OIDC host invalid")
        query = parse_qsl(request.query, keep_blank_values=True)
        if any(key == "audience" for key, _ in query):
            raise AuthorizationTransportError("validation OIDC audience override refused")
        credential = environment.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
        if not isinstance(credential, str) or not credential or not re.fullmatch(r"[\x21-\x7e]+", credential):
            raise AuthorizationTransportError("validation OIDC credential unavailable")
        self._origin = "https://" + origin.netloc
        self._oidc_url = urlunsplit(request._replace(query=urlencode([*query, ("audience", AUDIENCE)])))
        self._credential = credential
        self._opener = opener if opener is not None else build_opener(
            ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), _NoRedirect())
        self._state = "new"
        self._prepared = None

    def _request(self, url, token, *, data=None, limit):
        request = Request(url, data=data, method="GET" if data is None else "POST", headers={
            "Authorization": "Bearer " + token, "Accept": "application/json", "Accept-Encoding": "identity",
            "Content-Type": "application/json", "Cache-Control": "no-store"})
        try:
            with self._opener.open(request, timeout=30) as response:
                if response.status != 200 or response.geturl() != url:
                    raise ValueError("unexpected response")
                headers = response.headers
                if (headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json" or
                        headers.get("Content-Encoding", "identity").lower() != "identity" or
                        any(len(headers.get_all(name, [])) > 1 for name in ("Content-Type", "Content-Length", "Content-Encoding"))):
                    raise ValueError("unexpected headers")
                length = headers.get("Content-Length")
                if length is not None and (not re.fullmatch(r"[0-9]+", length) or int(length) > limit):
                    raise ValueError("response length invalid")
                chunks, size = [], 0
                while True:
                    part = response.read(min(65536, limit + 1 - size))
                    if not part:
                        break
                    size += len(part)
                    if size > limit:
                        raise ValueError("response too large")
                    chunks.append(part)
                if not size or (length is not None and size != int(length)):
                    raise ValueError("response incomplete")
                return b"".join(chunks)
        except Exception as exc:
            if isinstance(exc, HTTPError):
                with suppress(Exception):
                    exc.close()
            raise AuthorizationTransportError("validation transport request failed") from None

    def _token(self):
        document = _json(self._request(self._oidc_url, self._credential, limit=131072))
        token = document.get("value")
        if not isinstance(token, str) or len(token) > 65536 or not re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", token):
            raise AuthorizationTransportError("validation OIDC response invalid")
        return token  # Signature, issuer, Job and policy remain server-verified.

    def prepare(self):
        if self._state != "new":
            raise AuthorizationTransportError("validation transport session already used")
        self._state = "preparing"
        try:
            value = _json(self._request(self._origin + "/v1/authorization/prepare", self._token(), data=b"{}", limit=PREPARE_LIMIT))
            if (set(value) != {"protocol", "dispatch_id", "lease_token", "input_sha256", "input_size_bytes", "input_base64"} or
                    value["protocol"] != PROTOCOL or not isinstance(value["dispatch_id"], str) or not UUID.fullmatch(value["dispatch_id"])):
                raise AuthorizationTransportError("validation preparation response invalid")
            lease = _lease(value["lease_token"])
            encoded = value["input_base64"]
            try:
                raw = base64.b64decode(encoded, validate=True) if isinstance(encoded, str) else None
                if not raw or base64.b64encode(raw).decode("ascii") != encoded:
                    raise ValueError("invalid base64")
            except (ValueError, binascii.Error):
                raise AuthorizationTransportError("validation preparation bytes invalid") from None
            if (type(value["input_size_bytes"]) is not int or value["input_size_bytes"] != len(raw) or
                    value["input_sha256"] != "sha256:" + hashlib.sha256(raw).hexdigest()):
                raise AuthorizationTransportError("validation preparation fingerprint mismatch")
            prepared = {"dispatch_id": value["dispatch_id"], "lease_token": lease, "input_bytes": raw,
                        "input_sha256": value["input_sha256"], "input_size_bytes": value["input_size_bytes"]}
            self._prepared = deepcopy(prepared)
            self._state = "prepared"
            return prepared
        except Exception:
            self._state = "failed"
            raise

    def return_result(self, dispatch_id, lease_token, result_bytes):
        if (self._state != "prepared" or dispatch_id != self._prepared["dispatch_id"] or
                _lease(lease_token) != self._prepared["lease_token"] or type(result_bytes) is not bytes):
            raise AuthorizationTransportError("validation return session mismatch")
        self._state = "returning"
        try:
            data = _body({"protocol": PROTOCOL, "dispatch_id": dispatch_id, "lease_token": lease_token,
                          "result_base64": base64.b64encode(result_bytes).decode("ascii")})
            response = self._request(self._origin + "/v1/authorization/return", self._token(), data=data, limit=1048576)
            _json(response)  # Opaque JSON response; do not equate HTTP 200 with registered authority.
            self._state = "returned"
            return response
        except Exception:
            self._state = "failed"
            raise
