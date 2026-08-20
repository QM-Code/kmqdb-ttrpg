from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from http.cookies import SimpleCookie
from pathlib import Path
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PublicKey,
)


ROOT = Path(__file__).resolve().parent
DATABASE_ENVIRONMENT_VARIABLE = "KMQDB_TTRPG_AUTH_DB"
DEFAULT_DATABASE_PATH = ROOT / "work" / "ttrpg-auth.db"
SCHEMA_VERSION = 4
CLIENT_ID = "ttrpg"
SERVICE_ID = "ttrpg.kmqdb.com"
DEFAULT_ISSUER = "https://kmqdb.com"
DEFAULT_REDIRECT_URI = (
    "https://ttrpg.kmqdb.com/.api/auth/sso/callback"
)
DEFAULT_RETURN_TO = "/pf2er/stable/"
PENDING_LIFETIME_SECONDS = 10 * 60
SESSION_LIFETIME_SECONDS = 24 * 60 * 60
MAX_PENDING_AUTHORIZATIONS = 4096
MAX_SESSIONS_PER_OWNER = 20
IDENTITY_TOKEN_MAX_LIFETIME_SECONDS = 5 * 60
IDENTITY_CLOCK_SKEW_SECONDS = 30
NETWORK_TIMEOUT_SECONDS = 8
MAX_IDENTITY_RESPONSE_BYTES = 64 * 1024
SESSION_TOKEN_PREFIX = "kmqdb.ttrpg.session.v1."
SECURE_COOKIE_NAME = "__Host-kmqdb_ttrpg_session"
DEVELOPMENT_COOKIE_NAME = "kmqdb_ttrpg_session"
SECURE_PENDING_COOKIE_NAME = "__Host-kmqdb_ttrpg_sso"
DEVELOPMENT_PENDING_COOKIE_NAME = "kmqdb_ttrpg_sso"
STATE_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")
CODE_RE = re.compile(
    r"^kmqdb\.sso\.code\.v1\.[A-Za-z0-9_-]{43}$"
)
PENDING_BROWSER_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16}$")
SESSION_SECRET_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")
PLAN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_JWK_CACHE: dict[str, tuple[float, dict]] = {}
_JWK_CACHE_LOCK = threading.Lock()


class TtrpgAuthError(ValueError):
    pass


class TtrpgAuthenticationError(TtrpgAuthError):
    pass


class TtrpgAuthUnavailableError(RuntimeError):
    pass


class _NoRedirectHandler(urlrequest.HTTPRedirectHandler):
    def redirect_request(
        self,
        request,
        file_pointer,
        code,
        message,
        headers,
        new_url,
    ):
        return None


_NO_REDIRECT_OPENER = urlrequest.build_opener(
    _NoRedirectHandler()
)


def now_seconds() -> int:
    return int(time.time())


def b64url_encode(value: bytes) -> str:
    return (
        base64.urlsafe_b64encode(value)
        .decode("ascii")
        .rstrip("=")
    )


def b64url_decode(value: str) -> bytes:
    text = str(value or "")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", text):
        raise ValueError("base64url value is invalid")
    return base64.urlsafe_b64decode(
        text + ("=" * (-len(text) % 4))
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(
        str(value or "").encode("utf-8")
    ).hexdigest()


def pkce_challenge(verifier: str) -> str:
    return b64url_encode(
        hashlib.sha256(
            str(verifier or "").encode("ascii")
        ).digest()
    )


def configured_issuer() -> str:
    raw = str(
        os.environ.get("KMQDB_TTRPG_SSO_ISSUER")
        or DEFAULT_ISSUER
    ).strip()
    parsed = urlparse.urlsplit(raw)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or (
            parsed.scheme != "https"
            and parsed.hostname
            not in {"localhost", "127.0.0.1", "::1"}
        )
    ):
        raise TtrpgAuthUnavailableError(
            "KMQDB_TTRPG_SSO_ISSUER must be an HTTPS origin"
        )
    return raw.rstrip("/")


def configured_redirect_uri() -> str:
    raw = str(
        os.environ.get("KMQDB_TTRPG_SSO_REDIRECT_URI")
        or DEFAULT_REDIRECT_URI
    ).strip()
    parsed = urlparse.urlsplit(raw)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path != "/.api/auth/sso/callback"
        or (
            parsed.scheme != "https"
            and parsed.hostname
            not in {"localhost", "127.0.0.1", "::1"}
            and not parsed.hostname.endswith(".localhost")
        )
    ):
        raise TtrpgAuthUnavailableError(
            "KMQDB_TTRPG_SSO_REDIRECT_URI is invalid"
        )
    return raw


def secure_cookie_enabled() -> bool:
    return (
        urlparse.urlsplit(configured_redirect_uri()).scheme
        == "https"
    )


def session_cookie_name() -> str:
    return (
        SECURE_COOKIE_NAME
        if secure_cookie_enabled()
        else DEVELOPMENT_COOKIE_NAME
    )


def pending_cookie_name() -> str:
    return (
        SECURE_PENDING_COOKIE_NAME
        if secure_cookie_enabled()
        else DEVELOPMENT_PENDING_COOKIE_NAME
    )


def normalize_return_to(value: str) -> str:
    raw = str(value or DEFAULT_RETURN_TO).strip()
    parsed = urlparse.urlsplit(raw)
    if (
        len(raw) > 2048
        or parsed.scheme
        or parsed.netloc
        or parsed.fragment
        or not parsed.path.startswith("/")
        or parsed.path.startswith("//")
        or "\\" in raw
        or any(
            ord(character) < 33
            or ord(character) > 126
            for character in raw
        )
    ):
        raise TtrpgAuthError("return path is invalid")
    return parsed.path + (
        f"?{parsed.query}" if parsed.query else ""
    )


def authorization_endpoint() -> str:
    return f"{configured_issuer()}/.authorize/"


def token_endpoint() -> str:
    return f"{configured_issuer()}/.api/auth/sso/token"


def jwks_endpoint() -> str:
    return f"{configured_issuer()}/.api/auth/sso/jwks"


def _cookie_header(
    name: str,
    token: str,
    *,
    max_age: int,
) -> tuple[str, str]:
    value = (
        f"{name}={token}; "
        "Path=/; HttpOnly; SameSite=Lax"
    )
    if secure_cookie_enabled():
        value += "; Secure"
    value += f"; Max-Age={int(max_age)}"
    return "Set-Cookie", value


def session_cookie_header(
    token: str,
    *,
    max_age: int = SESSION_LIFETIME_SECONDS,
) -> tuple[str, str]:
    return _cookie_header(
        session_cookie_name(),
        token,
        max_age=max_age,
    )


def clear_session_cookie_header() -> tuple[str, str]:
    return _cookie_header(
        session_cookie_name(),
        "",
        max_age=0,
    )


def pending_cookie_header(token: str) -> tuple[str, str]:
    return _cookie_header(
        pending_cookie_name(),
        token,
        max_age=PENDING_LIFETIME_SECONDS,
    )


def clear_pending_cookie_header() -> tuple[str, str]:
    return _cookie_header(
        pending_cookie_name(),
        "",
        max_age=0,
    )


def cookie_token(environ: dict, name: str) -> str:
    raw = str(environ.get("HTTP_COOKIE") or "")
    if not raw:
        return ""
    cookies = SimpleCookie()
    try:
        cookies.load(raw)
    except Exception:
        return ""
    morsel = cookies.get(name)
    return str(morsel.value) if morsel is not None else ""


def cookie_session_token(environ: dict) -> str:
    return cookie_token(environ, session_cookie_name())


def cookie_pending_token(environ: dict) -> str:
    return cookie_token(environ, pending_cookie_name())


class TtrpgAuthStore:
    def __init__(self, path: Path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
            mode=0o755,
        )
        descriptor = os.open(
            self.path,
            os.O_CREAT | os.O_RDWR,
            0o600,
        )
        os.close(descriptor)
        self._secure_files()
        with self.connection() as connection:
            self._enable_write_ahead_logging(connection)
            self._initialize(connection)

    def _secure_files(self) -> None:
        for path in (
            self.path,
            Path(f"{self.path}-wal"),
            Path(f"{self.path}-shm"),
        ):
            try:
                path.chmod(0o600)
            except FileNotFoundError:
                pass

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=10,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    @staticmethod
    def _enable_write_ahead_logging(
        connection: sqlite3.Connection,
    ) -> None:
        deadline = time.monotonic() + 10
        while True:
            try:
                mode = str(
                    connection.execute(
                        "PRAGMA journal_mode = WAL"
                    ).fetchone()[0]
                ).casefold()
                if mode != "wal":
                    raise TtrpgAuthUnavailableError(
                        "TTRPG auth database did not enter WAL mode"
                    )
                return
            except sqlite3.OperationalError as failure:
                if (
                    "locked" not in str(failure).casefold()
                    or time.monotonic() >= deadline
                ):
                    raise
                time.sleep(0.01)

    @staticmethod
    def _verify_schema(
        connection: sqlite3.Connection,
    ) -> None:
        expected = {
            "pending_authorizations": {
                "state_digest",
                "browser_token_digest",
                "code_verifier",
                "return_to",
                "created_at",
                "expires_at",
                "consumed_at",
            },
            "browser_sessions": {
                "token_id",
                "token_digest",
                "owner_id",
                "username",
                "role",
                "email_verified",
                "issuer",
                "service_id",
                "plan_id",
                "created_at",
                "expires_at",
                "revoked_at",
            },
        }
        tables = {
            str(row["name"])
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                """
            )
        }
        if tables != set(expected):
            raise TtrpgAuthUnavailableError(
                "TTRPG auth database schema is invalid"
            )
        for table, columns in expected.items():
            column_rows = connection.execute(
                f"PRAGMA table_info({table})"
            ).fetchall()
            actual = {str(row["name"]) for row in column_rows}
            if actual != columns:
                raise TtrpgAuthUnavailableError(
                    "TTRPG auth database schema is invalid"
                )

    def _initialize(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        connection.execute("BEGIN IMMEDIATE")
        try:
            version = int(
                connection.execute(
                    "PRAGMA user_version"
                ).fetchone()[0]
            )
            tables = {
                str(row["name"])
                for row in connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table'
                      AND name NOT LIKE 'sqlite_%'
                    """
                )
            }
            if version == 0:
                if tables:
                    raise TtrpgAuthUnavailableError(
                        "TTRPG auth database has no schema version"
                    )
                connection.execute(
                    """
                    CREATE TABLE pending_authorizations (
                        state_digest TEXT PRIMARY KEY,
                        browser_token_digest TEXT NOT NULL,
                        code_verifier TEXT NOT NULL,
                        return_to TEXT NOT NULL,
                        created_at INTEGER NOT NULL,
                        expires_at INTEGER NOT NULL,
                        consumed_at INTEGER
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX
                        pending_authorizations_expiry
                    ON pending_authorizations (
                        expires_at,
                        consumed_at
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE browser_sessions (
                        token_id TEXT PRIMARY KEY,
                        token_digest TEXT NOT NULL UNIQUE,
                        owner_id INTEGER NOT NULL,
                        username TEXT NOT NULL,
                        role TEXT NOT NULL,
                        email_verified INTEGER NOT NULL,
                        issuer TEXT NOT NULL,
                        service_id TEXT NOT NULL,
                        plan_id TEXT NOT NULL,
                        created_at INTEGER NOT NULL,
                        expires_at INTEGER NOT NULL,
                        revoked_at INTEGER,
                        CHECK (owner_id >= 0),
                        CHECK (
                            role IN ('user', 'administrator')
                        ),
                        CHECK (email_verified IN (0, 1)),
                        CHECK (service_id = 'ttrpg.kmqdb.com'),
                        CHECK (plan_id <> '')
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX browser_sessions_expiry
                    ON browser_sessions (
                        expires_at,
                        revoked_at
                    )
                    """
                )
                connection.execute(
                    f"PRAGMA user_version = {SCHEMA_VERSION}"
                )
            elif version != SCHEMA_VERSION:
                raise TtrpgAuthUnavailableError(
                    "TTRPG auth database schema is unsupported"
                )
            self._verify_schema(connection)
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    @contextmanager
    def connection(self):
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()
            self._secure_files()

    def begin_authorization(
        self,
        *,
        return_to: str = DEFAULT_RETURN_TO,
        browser_token: str = "",
    ) -> dict:
        normalized_return = normalize_return_to(return_to)
        normalized_browser_token = str(browser_token or "")
        if not PENDING_BROWSER_TOKEN_RE.fullmatch(
            normalized_browser_token
        ):
            normalized_browser_token = secrets.token_urlsafe(32)
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = pkce_challenge(verifier)
        timestamp = now_seconds()
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                DELETE FROM pending_authorizations
                WHERE expires_at <= ? OR consumed_at IS NOT NULL
                """,
                (timestamp,),
            )
            connection.execute(
                """
                INSERT INTO pending_authorizations (
                    state_digest,
                    browser_token_digest,
                    code_verifier,
                    return_to,
                    created_at,
                    expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    sha256_text(state),
                    sha256_text(normalized_browser_token),
                    verifier,
                    normalized_return,
                    timestamp,
                    timestamp + PENDING_LIFETIME_SECONDS,
                ),
            )
            connection.execute(
                """
                DELETE FROM pending_authorizations
                WHERE rowid IN (
                    SELECT rowid
                    FROM pending_authorizations
                    ORDER BY created_at DESC, rowid DESC
                    LIMIT -1 OFFSET ?
                )
                """,
                (MAX_PENDING_AUTHORIZATIONS,),
            )
            connection.commit()
        query = urlparse.urlencode(
            {
                "response_type": "code",
                "client_id": CLIENT_ID,
                "redirect_uri": configured_redirect_uri(),
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        return {
            "state": state,
            "browserToken": normalized_browser_token,
            "authorizationUrl": (
                f"{authorization_endpoint()}?{query}"
            ),
            "returnTo": normalized_return,
            "expiresAt": (
                timestamp + PENDING_LIFETIME_SECONDS
            ),
        }

    def consume_authorization(
        self,
        state: str,
        *,
        browser_token: str,
    ) -> dict:
        if (
            not STATE_RE.fullmatch(str(state or ""))
            or not PENDING_BROWSER_TOKEN_RE.fullmatch(
                str(browser_token or "")
            )
        ):
            raise TtrpgAuthenticationError(
                "SSO callback is invalid"
            )
        timestamp = now_seconds()
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT
                    state_digest,
                    browser_token_digest,
                    code_verifier,
                    return_to,
                    expires_at,
                    consumed_at
                FROM pending_authorizations
                WHERE state_digest = ?
                """,
                (sha256_text(state),),
            ).fetchone()
            if (
                row is None
                or row["consumed_at"] is not None
                or int(row["expires_at"]) <= timestamp
                or not hmac.compare_digest(
                    str(row["browser_token_digest"]),
                    sha256_text(browser_token),
                )
            ):
                connection.rollback()
                raise TtrpgAuthenticationError(
                    "SSO callback is invalid or expired"
                )
            connection.execute(
                """
                UPDATE pending_authorizations
                SET consumed_at = ?
                WHERE state_digest = ?
                """,
                (timestamp, str(row["state_digest"])),
            )
            connection.commit()
        return {
            "codeVerifier": str(row["code_verifier"]),
            "returnTo": str(row["return_to"]),
        }

    def create_session(self, principal: dict) -> tuple[str, dict]:
        owner_id = principal.get("id")
        username = str(principal.get("username") or "")
        role = str(principal.get("role") or "")
        email_verified = principal.get("emailVerified")
        issuer = str(principal.get("issuer") or "")
        service_id = str(principal.get("serviceId") or "")
        subscription_status = str(
            principal.get("subscriptionStatus") or ""
        )
        plan_id = str(principal.get("planId") or "")
        if (
            isinstance(owner_id, bool)
            or not isinstance(owner_id, int)
            or owner_id < 0
            or not username
            or len(username) > 320
            or role not in {"user", "administrator"}
            or not isinstance(email_verified, bool)
            or issuer != configured_issuer()
            or service_id != SERVICE_ID
            or subscription_status != "active"
            or not PLAN_ID_RE.fullmatch(plan_id)
        ):
            raise TtrpgAuthenticationError(
                "central identity is invalid"
            )
        token_id = secrets.token_urlsafe(12)
        token_secret = secrets.token_urlsafe(32)
        token = (
            f"{SESSION_TOKEN_PREFIX}"
            f"{token_id}.{token_secret}"
        )
        timestamp = now_seconds()
        expires = timestamp + SESSION_LIFETIME_SECONDS
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                DELETE FROM browser_sessions
                WHERE expires_at <= ? OR revoked_at IS NOT NULL
                """,
                (timestamp,),
            )
            connection.execute(
                """
                INSERT INTO browser_sessions (
                    token_id,
                    token_digest,
                    owner_id,
                    username,
                    role,
                    email_verified,
                    issuer,
                    service_id,
                    plan_id,
                    created_at,
                    expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    token_id,
                    sha256_text(token),
                    owner_id,
                    username,
                    role,
                    1 if email_verified else 0,
                    issuer,
                    service_id,
                    plan_id,
                    timestamp,
                    expires,
                ),
            )
            connection.execute(
                """
                DELETE FROM browser_sessions
                WHERE rowid IN (
                    SELECT rowid
                    FROM browser_sessions
                    WHERE owner_id = ?
                    ORDER BY created_at DESC, rowid DESC
                    LIMIT -1 OFFSET ?
                )
                """,
                (owner_id, MAX_SESSIONS_PER_OWNER),
            )
            connection.commit()
        return token, {
            "id": owner_id,
            "username": username,
            "emailVerified": email_verified,
            "role": role,
            "serviceId": service_id,
            "subscriptionStatus": subscription_status,
            "planId": plan_id,
            "expiresAt": expires,
        }

    @staticmethod
    def _token_id(token: str) -> str:
        raw = str(token or "")
        if not raw.startswith(SESSION_TOKEN_PREFIX):
            return ""
        remainder = raw.removeprefix(SESSION_TOKEN_PREFIX)
        token_id, separator, secret = remainder.partition(".")
        if (
            not separator
            or not SESSION_ID_RE.fullmatch(token_id)
            or not SESSION_SECRET_RE.fullmatch(secret)
        ):
            return ""
        return token_id

    def authenticate_session(
        self,
        token: str,
    ) -> dict | None:
        token_id = self._token_id(token)
        if not token_id:
            return None
        timestamp = now_seconds()
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT
                    token_digest,
                    owner_id,
                    username,
                    role,
                    email_verified,
                    issuer,
                    service_id,
                    plan_id,
                    expires_at,
                    revoked_at
                FROM browser_sessions
                WHERE token_id = ?
                """,
                (token_id,),
            ).fetchone()
        if (
            row is None
            or row["revoked_at"] is not None
            or int(row["expires_at"]) <= timestamp
            or str(row["issuer"]) != configured_issuer()
            or str(row["service_id"]) != SERVICE_ID
            or not PLAN_ID_RE.fullmatch(
                str(row["plan_id"])
            )
            or not hmac.compare_digest(
                str(row["token_digest"]),
                sha256_text(token),
            )
        ):
            return None
        return {
            "id": int(row["owner_id"]),
            "username": str(row["username"]),
            "emailVerified": bool(row["email_verified"]),
            "role": str(row["role"]),
            "serviceId": str(row["service_id"]),
            "subscriptionStatus": "active",
            "planId": str(row["plan_id"]),
            "expiresAt": int(row["expires_at"]),
        }

    def revoke_session(self, token: str) -> None:
        token_id = self._token_id(token)
        if not token_id:
            return
        timestamp = now_seconds()
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT token_digest
                FROM browser_sessions
                WHERE token_id = ? AND revoked_at IS NULL
                """,
                (token_id,),
            ).fetchone()
            if (
                row is not None
                and hmac.compare_digest(
                    str(row["token_digest"]),
                    sha256_text(token),
                )
            ):
                connection.execute(
                    """
                    UPDATE browser_sessions
                    SET revoked_at = ?
                    WHERE token_id = ?
                    """,
                    (timestamp, token_id),
                )
            connection.commit()


def principal_from_environ(
    store: TtrpgAuthStore,
    environ: dict,
) -> dict | None:
    return store.authenticate_session(
        cookie_session_token(environ)
    )


def _read_json_response(
    request: urlrequest.Request,
) -> dict:
    try:
        timeout = float(
            os.environ.get(
                "KMQDB_TTRPG_SSO_TIMEOUT_SECONDS"
            )
            or NETWORK_TIMEOUT_SECONDS
        )
    except ValueError as failure:
        raise TtrpgAuthUnavailableError(
            "central identity timeout is invalid"
        ) from failure
    if not 0 < timeout <= 60:
        raise TtrpgAuthUnavailableError(
            "central identity timeout is invalid"
        )
    with _NO_REDIRECT_OPENER.open(
        request,
        timeout=timeout,
    ) as response:
        if response.geturl() != request.full_url:
            raise TtrpgAuthUnavailableError(
                "central identity endpoint redirected unexpectedly"
            )
        raw = response.read(MAX_IDENTITY_RESPONSE_BYTES + 1)
    if len(raw) > MAX_IDENTITY_RESPONSE_BYTES:
        raise TtrpgAuthUnavailableError(
            "central identity response is too large"
        )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as failure:
        raise TtrpgAuthUnavailableError(
            "central identity response is invalid"
        ) from failure
    if not isinstance(payload, dict):
        raise TtrpgAuthUnavailableError(
            "central identity response is invalid"
        )
    return payload


def fetch_jwks(*, force: bool = False) -> dict:
    issuer = configured_issuer()
    timestamp = time.monotonic()
    with _JWK_CACHE_LOCK:
        cached = _JWK_CACHE.get(issuer)
        if (
            not force
            and cached is not None
            and cached[0] > timestamp
        ):
            return cached[1]
    request = urlrequest.Request(
        jwks_endpoint(),
        method="GET",
        headers={
            "Accept": "application/json",
            "User-Agent": "KMQDB-TTRPG-SSO/1",
        },
    )
    payload = _read_json_response(request)
    if not isinstance(payload.get("keys"), list):
        raise TtrpgAuthUnavailableError(
            "central signing-key response is invalid"
        )
    with _JWK_CACHE_LOCK:
        _JWK_CACHE[issuer] = (timestamp + 300, payload)
    return payload


def verify_identity_token(
    token: str,
    jwks: dict,
    *,
    timestamp: int | None = None,
) -> dict:
    parts = str(token or "").split(".")
    if len(parts) != 3:
        raise TtrpgAuthenticationError(
            "central identity token is invalid"
        )
    try:
        header = json.loads(b64url_decode(parts[0]))
        claims = json.loads(b64url_decode(parts[1]))
        signature = b64url_decode(parts[2])
    except (
        UnicodeDecodeError,
        ValueError,
        json.JSONDecodeError,
    ) as failure:
        raise TtrpgAuthenticationError(
            "central identity token is invalid"
        ) from failure
    if (
        not isinstance(header, dict)
        or not isinstance(claims, dict)
        or header.get("alg") != "EdDSA"
        or header.get("typ") != "JWT"
        or not isinstance(header.get("kid"), str)
    ):
        raise TtrpgAuthenticationError(
            "central identity token is invalid"
        )
    keys = jwks.get("keys")
    if not isinstance(keys, list):
        raise TtrpgAuthenticationError(
            "central signing keys are invalid"
        )
    matches = [
        key
        for key in keys
        if (
            isinstance(key, dict)
            and key.get("kid") == header["kid"]
            and key.get("kty") == "OKP"
            and key.get("crv") == "Ed25519"
            and key.get("alg") == "EdDSA"
            and key.get("use") == "sig"
            and isinstance(key.get("x"), str)
        )
    ]
    if len(matches) != 1:
        raise TtrpgAuthenticationError(
            "central signing key is unavailable"
        )
    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            b64url_decode(matches[0]["x"])
        )
        public_key.verify(
            signature,
            f"{parts[0]}.{parts[1]}".encode("ascii"),
        )
    except (InvalidSignature, TypeError, ValueError) as failure:
        raise TtrpgAuthenticationError(
            "central identity signature is invalid"
        ) from failure
    current = int(
        now_seconds() if timestamp is None else timestamp
    )
    try:
        issued_at = int(claims["iat"])
        expires_at = int(claims["exp"])
        owner_id = int(str(claims["sub"]))
    except (KeyError, TypeError, ValueError) as failure:
        raise TtrpgAuthenticationError(
            "central identity claims are invalid"
        ) from failure
    if (
        str(owner_id) != str(claims.get("sub"))
        or owner_id < 0
        or claims.get("iss") != configured_issuer()
        or claims.get("aud") != CLIENT_ID
        or claims.get("service") != SERVICE_ID
        or claims.get("subscription_status") != "active"
        or not isinstance(claims.get("plan"), str)
        or not PLAN_ID_RE.fullmatch(claims["plan"])
        or issued_at > current + IDENTITY_CLOCK_SKEW_SECONDS
        or expires_at
        <= current - IDENTITY_CLOCK_SKEW_SECONDS
        or expires_at <= issued_at
        or (
            expires_at - issued_at
            > IDENTITY_TOKEN_MAX_LIFETIME_SECONDS
        )
        or not isinstance(claims.get("jti"), str)
        or not claims["jti"]
        or not isinstance(claims.get("username"), str)
        or not claims["username"]
        or len(claims["username"]) > 320
        or claims.get("role") not in {"user", "administrator"}
        or not isinstance(claims.get("email_verified"), bool)
    ):
        raise TtrpgAuthenticationError(
            "central identity claims are invalid"
        )
    return {
        "id": owner_id,
        "username": str(claims["username"]),
        "emailVerified": bool(claims["email_verified"]),
        "role": str(claims["role"]),
        "issuer": str(claims["iss"]),
        "serviceId": str(claims["service"]),
        "subscriptionStatus": str(
            claims["subscription_status"]
        ),
        "planId": str(claims["plan"]),
    }


def exchange_identity(
    *,
    code: str,
    code_verifier: str,
) -> dict:
    if not CODE_RE.fullmatch(str(code or "")):
        raise TtrpgAuthenticationError(
            "SSO authorization code is invalid"
        )
    body = urlparse.urlencode(
        {
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": code,
            "redirect_uri": configured_redirect_uri(),
            "code_verifier": code_verifier,
        }
    ).encode("ascii")
    request = urlrequest.Request(
        token_endpoint(),
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": (
                "application/x-www-form-urlencoded"
            ),
            "User-Agent": "KMQDB-TTRPG-SSO/1",
        },
    )
    try:
        payload = _read_json_response(request)
    except urlerror.HTTPError as failure:
        if 400 <= int(failure.code) < 500:
            raise TtrpgAuthenticationError(
                "SSO authorization code is invalid"
            ) from failure
        raise TtrpgAuthUnavailableError(
            "central identity service is unavailable"
        ) from failure
    except (
        OSError,
        TimeoutError,
        urlerror.URLError,
    ) as failure:
        raise TtrpgAuthUnavailableError(
            "central identity service is unavailable"
        ) from failure
    token = payload.get("identity_token")
    if (
        payload.get("token_type")
        != "urn:kmqdb:identity-token"
        or not isinstance(token, str)
    ):
        raise TtrpgAuthUnavailableError(
            "central identity response is invalid"
        )
    try:
        jwks = fetch_jwks()
        try:
            return verify_identity_token(token, jwks)
        except TtrpgAuthenticationError as first_failure:
            refreshed = fetch_jwks(force=True)
            try:
                return verify_identity_token(
                    token,
                    refreshed,
                )
            except TtrpgAuthenticationError:
                raise first_failure
    except (
        OSError,
        TimeoutError,
        urlerror.URLError,
    ) as failure:
        raise TtrpgAuthUnavailableError(
            "central identity service is unavailable"
        ) from failure
