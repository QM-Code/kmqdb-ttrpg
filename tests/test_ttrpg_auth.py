from __future__ import annotations

import io
import hashlib
import json
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import parse_qs, urlencode, urlsplit
from unittest import mock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

from subdomains.ttrpg import backend, ttrpg_auth


ISSUER = "http://localhost:8010"
REDIRECT_URI = (
    "http://ttrpg.localhost:8011/.api/auth/sso/callback"
)


class TtrpgAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.store = ttrpg_auth.TtrpgAuthStore(
            Path(self.temporary.name) / "ttrpg-auth.db"
        )
        self.environment = mock.patch.dict(
            os.environ,
            {
                "KMQDB_TTRPG_SSO_ISSUER": ISSUER,
                "KMQDB_TTRPG_SSO_REDIRECT_URI": (
                    REDIRECT_URI
                ),
            },
        )
        self.environment.start()
        with ttrpg_auth._JWK_CACHE_LOCK:
            ttrpg_auth._JWK_CACHE.clear()

    def tearDown(self) -> None:
        with ttrpg_auth._JWK_CACHE_LOCK:
            ttrpg_auth._JWK_CACHE.clear()
        self.environment.stop()
        self.temporary.cleanup()

    @staticmethod
    def identity_material(
        claim_overrides: dict | None = None,
    ) -> tuple[str, dict]:
        private_key = Ed25519PrivateKey.generate()
        public_bytes = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        kid = ttrpg_auth.b64url_encode(
            hashlib.sha256(public_bytes).digest()[:12]
        )
        header = {
            "alg": "EdDSA",
            "kid": kid,
            "typ": "JWT",
        }
        timestamp = int(time.time())
        claims = {
            "iss": ISSUER,
            "aud": ttrpg_auth.CLIENT_ID,
            "sub": "17",
            "username": "owner@example.test",
            "role": "user",
            "email_verified": False,
            "service": ttrpg_auth.SERVICE_ID,
            "subscription_status": "active",
            "plan": "free",
            "iat": timestamp,
            "exp": timestamp + 120,
            "jti": "identity-1",
        }
        claims.update(claim_overrides or {})
        encoded_header = ttrpg_auth.b64url_encode(
            json.dumps(
                header,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
        encoded_claims = ttrpg_auth.b64url_encode(
            json.dumps(
                claims,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
        signing_input = (
            f"{encoded_header}.{encoded_claims}"
        )
        token = (
            f"{signing_input}."
            + ttrpg_auth.b64url_encode(
                private_key.sign(
                    signing_input.encode("ascii")
                )
            )
        )
        jwks = {
            "keys": [
                {
                    "kty": "OKP",
                    "crv": "Ed25519",
                    "use": "sig",
                    "alg": "EdDSA",
                    "kid": kid,
                    "x": ttrpg_auth.b64url_encode(
                        public_bytes
                    ),
                }
            ]
        }
        return token, jwks

    def test_signed_identity_creates_revocable_local_session(
        self,
    ) -> None:
        token, jwks = self.identity_material()
        principal = ttrpg_auth.verify_identity_token(
            token,
            jwks,
        )
        self.assertEqual(principal["id"], 17)
        self.assertFalse(principal["emailVerified"])
        self.assertEqual(
            principal["serviceId"],
            ttrpg_auth.SERVICE_ID,
        )
        self.assertEqual(
            principal["subscriptionStatus"],
            "active",
        )
        self.assertEqual(principal["planId"], "free")

        session, payload = self.store.create_session(
            principal
        )
        self.assertEqual(payload["id"], 17)
        self.assertEqual(
            payload["serviceId"],
            ttrpg_auth.SERVICE_ID,
        )
        self.assertEqual(payload["planId"], "free")
        cookie = ttrpg_auth.session_cookie_header(
            session
        )[1]
        self.assertNotIn("Secure", cookie)
        environ = {
            "HTTP_COOKIE": cookie.split(";", 1)[0],
        }
        self.assertEqual(
            ttrpg_auth.principal_from_environ(
                self.store,
                environ,
            )["id"],
            17,
        )
        self.store.revoke_session(session)
        self.assertIsNone(
            ttrpg_auth.principal_from_environ(
                self.store,
                environ,
            )
        )

    def test_identity_must_assert_this_active_service_subscription(
        self,
    ) -> None:
        for overrides in (
            {"service": "other.kmqdb.com"},
            {"subscription_status": "canceled"},
            {"plan": ""},
        ):
            with self.subTest(overrides=overrides):
                token, jwks = self.identity_material(
                    overrides
                )
                with self.assertRaisesRegex(
                    ttrpg_auth.TtrpgAuthenticationError,
                    "claims are invalid",
                ):
                    ttrpg_auth.verify_identity_token(
                        token,
                        jwks,
                    )

    def test_older_auth_schema_is_a_hard_cut(self) -> None:
        legacy = Path(self.temporary.name) / "legacy-auth.db"
        with sqlite3.connect(legacy) as connection:
            connection.execute("PRAGMA user_version = 3")

        with self.assertRaisesRegex(
            ttrpg_auth.TtrpgAuthUnavailableError,
            "schema is unsupported",
        ):
            ttrpg_auth.TtrpgAuthStore(legacy)

    def test_auth_schema_contains_only_browser_auth_state(self) -> None:
        with self.store.connection() as connection:
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                4,
            )
            tables = {
                str(row["name"])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' "
                    "AND name NOT LIKE 'sqlite_%'"
                )
            }
        self.assertEqual(
            tables,
            {"pending_authorizations", "browser_sessions"},
        )
        for retired_attribute in (
            "API_CREDENTIAL_TOKEN_PREFIX",
            "API_CREDENTIAL_SCOPES",
            "issue_api_credential",
            "authenticate_api_credential",
            "list_api_credentials",
            "revoke_api_credential",
        ):
            with self.subTest(retired_attribute=retired_attribute):
                self.assertFalse(
                    hasattr(ttrpg_auth, retired_attribute)
                    or hasattr(
                        ttrpg_auth.TtrpgAuthStore,
                        retired_attribute,
                    )
                )
        source = Path(ttrpg_auth.__file__).read_text(
            encoding="utf-8"
        )
        for retired_value in (
            "kmqdb.ttrpg.api.v1",
            "api_credentials",
            "stable:read",
            "encounter:create",
            "encounter:control",
            "encounter:read",
        ):
            with self.subTest(retired_value=retired_value):
                self.assertNotIn(retired_value, source)

    def test_pending_state_is_one_time_and_return_is_local(
        self,
    ) -> None:
        pending = self.store.begin_authorization(
            return_to="/pf2er/stable/?view=roster"
        )
        authorization = urlsplit(
            pending["authorizationUrl"]
        )
        query = parse_qs(authorization.query)
        self.assertEqual(
            query["redirect_uri"],
            [REDIRECT_URI],
        )
        self.assertEqual(
            query["code_challenge_method"],
            ["S256"],
        )
        with self.assertRaisesRegex(
            ttrpg_auth.TtrpgAuthenticationError,
            "invalid or expired",
        ):
            self.store.consume_authorization(
                pending["state"],
                browser_token="x" * 43,
            )
        consumed = self.store.consume_authorization(
            pending["state"],
            browser_token=pending["browserToken"],
        )
        self.assertEqual(
            consumed["returnTo"],
            "/pf2er/stable/?view=roster",
        )
        with self.assertRaisesRegex(
            ttrpg_auth.TtrpgAuthenticationError,
            "invalid or expired",
        ):
            self.store.consume_authorization(
                pending["state"],
                browser_token=pending["browserToken"],
            )
        for unsafe_return in (
            "https://evil.example/",
            "/\\evil.example/",
            "/bad path",
            "/café",
        ):
            with self.subTest(return_to=unsafe_return):
                with self.assertRaisesRegex(
                    ttrpg_auth.TtrpgAuthError,
                    "return path",
                ):
                    self.store.begin_authorization(
                        return_to=unsafe_return
                    )

    def test_production_cookie_is_secure_and_host_only(
        self,
    ) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "KMQDB_TTRPG_SSO_ISSUER": (
                    "https://kmqdb.com"
                ),
                "KMQDB_TTRPG_SSO_REDIRECT_URI": (
                    "https://ttrpg.kmqdb.com/"
                    ".api/auth/sso/callback"
                ),
            },
        ):
            header = ttrpg_auth.session_cookie_header(
                "opaque"
            )[1]
            pending_header = (
                ttrpg_auth.pending_cookie_header("b" * 43)[1]
            )
        self.assertTrue(
            header.startswith(
                "__Host-kmqdb_ttrpg_session=opaque;"
            )
        )
        self.assertIn("; Secure", header)
        self.assertIn("; HttpOnly", header)
        self.assertIn("; SameSite=Lax", header)
        self.assertNotIn("Domain=", header)
        self.assertTrue(
            pending_header.startswith(
                "__Host-kmqdb_ttrpg_sso=" + ("b" * 43) + ";"
            )
        )
        self.assertIn("; Secure", pending_header)
        self.assertIn("; HttpOnly", pending_header)
        self.assertNotIn("Domain=", pending_header)

    def test_concurrent_fresh_store_initialization_is_serialized(
        self,
    ) -> None:
        database = (
            Path(self.temporary.name) / "concurrent-auth.db"
        )
        with ThreadPoolExecutor(max_workers=6) as executor:
            stores = list(
                executor.map(
                    lambda _index: (
                        ttrpg_auth.TtrpgAuthStore(database)
                    ),
                    range(6),
                )
            )
        self.assertEqual(len(stores), 6)
        pending = stores[0].begin_authorization()
        self.assertTrue(pending["authorizationUrl"])

    def test_identity_http_client_does_not_follow_redirects(
        self,
    ) -> None:
        target_requests = []

        class RedirectHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", "/target")
                    self.end_headers()
                    return
                target_requests.append(self.path)
                body = b'{"unexpected":true}'
                self.send_response(200)
                self.send_header(
                    "Content-Type",
                    "application/json",
                )
                self.send_header(
                    "Content-Length",
                    str(len(body)),
                )
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format, *args) -> None:
                return

        server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            RedirectHandler,
        )
        thread = threading.Thread(
            target=server.serve_forever,
            daemon=True,
        )
        thread.start()
        try:
            request = urlrequest.Request(
                "http://127.0.0.1:"
                f"{server.server_port}/redirect"
            )
            with self.assertRaises(urlerror.HTTPError) as failure:
                ttrpg_auth._read_json_response(request)
            self.assertEqual(failure.exception.code, 302)
            self.assertEqual(target_requests, [])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_rejected_authorization_code_is_not_a_service_outage(
        self,
    ) -> None:
        rejected = urlerror.HTTPError(
            ttrpg_auth.token_endpoint(),
            400,
            "Bad Request",
            {},
            None,
        )
        with (
            mock.patch.object(
                ttrpg_auth,
                "_read_json_response",
                side_effect=rejected,
            ),
            self.assertRaisesRegex(
                ttrpg_auth.TtrpgAuthenticationError,
                "authorization code",
            ),
        ):
            ttrpg_auth.exchange_identity(
                code=(
                    "kmqdb.sso.code.v1."
                    + ("c" * 43)
                ),
                code_verifier="v" * 64,
            )

    @staticmethod
    def call_backend(
        path: str,
        *,
        query: dict[str, str] | None = None,
        method: str = "GET",
        cookie: str = "",
    ) -> tuple[str, dict[str, str], bytes]:
        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "QUERY_STRING": urlencode(query or {}),
            "HTTP_HOST": "ttrpg.localhost:8011",
            "REMOTE_ADDR": "127.0.0.1",
            "CONTENT_LENGTH": "",
            "wsgi.input": io.BytesIO(),
        }
        if cookie:
            environ["HTTP_COOKIE"] = cookie
        captured: dict = {}

        def start_response(status, headers):
            captured["status"] = status
            combined = {}
            for name, value in headers:
                if name in combined:
                    combined[name] += f"\n{value}"
                else:
                    combined[name] = value
            captured["headers"] = combined

        body = b"".join(
            backend.application(environ, start_response)
        )
        return (
            captured["status"],
            captured["headers"],
            body,
        )

    def test_backend_performs_redirect_callback_and_logout(
        self,
    ) -> None:
        principal = {
            "id": 17,
            "username": "owner@example.test",
            "emailVerified": False,
            "role": "user",
            "issuer": ISSUER,
            "serviceId": ttrpg_auth.SERVICE_ID,
            "subscriptionStatus": "active",
            "planId": "free",
        }
        with (
            mock.patch.object(
                backend,
                "ttrpg_auth_store",
                return_value=self.store,
            ),
            mock.patch.object(
                ttrpg_auth,
                "exchange_identity",
                return_value=principal,
            ) as exchange,
        ):
            status, headers, _body = self.call_backend(
                "/.api/auth/sso/start",
                query={"returnTo": "/pf2er/stable/"},
            )
            self.assertEqual(status, "303 See Other")
            authorization = urlsplit(headers["Location"])
            state = parse_qs(
                authorization.query
            )["state"][0]
            pending_cookie = headers["Set-Cookie"].split(
                ";",
                1,
            )[0]
            self.assertTrue(
                pending_cookie.startswith(
                    "kmqdb_ttrpg_sso="
                )
            )

            code = (
                "kmqdb.sso.code.v1."
                + ("c" * 43)
            )
            status, headers, _body = self.call_backend(
                "/.api/auth/sso/callback",
                query={"code": code, "state": state},
                cookie=pending_cookie,
            )
            self.assertEqual(status, "303 See Other")
            self.assertEqual(
                headers["Location"],
                "/pf2er/stable/",
            )
            exchange.assert_called_once()
            set_cookies = headers["Set-Cookie"].splitlines()
            self.assertTrue(
                any(
                    value.startswith(
                        "kmqdb_ttrpg_sso=;"
                    )
                    and "Max-Age=0" in value
                    for value in set_cookies
                )
            )
            cookie = next(
                value.split(";", 1)[0]
                for value in set_cookies
                if value.startswith(
                    "kmqdb_ttrpg_session="
                )
            )

            status, session_headers, body = self.call_backend(
                "/.api/auth/session",
                cookie=cookie,
            )
            self.assertEqual(status, "200 OK")
            self.assertEqual(
                session_headers["Cache-Control"],
                "no-store",
            )
            session = json.loads(body)["user"]
            self.assertEqual(session["id"], 17)
            self.assertFalse(session["emailVerified"])
            self.assertEqual(
                session["serviceId"],
                ttrpg_auth.SERVICE_ID,
            )
            self.assertEqual(
                session["subscriptionStatus"],
                "active",
            )
            self.assertEqual(session["planId"], "free")

            status, headers, body = self.call_backend(
                "/.api/auth/logout",
                method="POST",
                cookie=cookie,
            )
            self.assertEqual(status, "200 OK")
            self.assertEqual(json.loads(body), {"ok": True})
            self.assertIn("Max-Age=0", headers["Set-Cookie"])
            self.assertEqual(
                headers["Cache-Control"],
                "no-store",
            )

            status, _headers, body = self.call_backend(
                "/.api/auth/session",
                cookie=cookie,
            )
            self.assertEqual(status, "200 OK")
            self.assertIsNone(json.loads(body)["user"])


if __name__ == "__main__":
    unittest.main()
