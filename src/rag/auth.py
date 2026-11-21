"""Accounts, guest sessions and daily question limits for the web UI. Standard library only.

  - Passwords are hashed with scrypt and a random salt, and compared in constant time.
  - A session is a signed token in an HttpOnly cookie: kind + subject + expiry, signed with HMAC-SHA256.
    Anyone who changes the token, or lets it expire, is signed out.
  - Every question costs LLM quota, so each person has a daily limit (guests fewer than accounts).
    The count lives in SQLite and survives restarts. A failed question is refunded.
  - Failed sign-ins are throttled per address and email, and sign-ups per address, in memory.
  - With `require_verification`, a new account is "pending" until its owner opens the link emailed to the address,
    so a mistyped or invented address never becomes an account. The link is signed, expires, and works once; asking
    for a new link (or signing up again) invalidates the old one.

Limits of this design, on purpose: no password reset, no sign-in with Google. The
throttles are per process. Behind a proxy, run uvicorn with --proxy-headers so the real client address is seen.
"""

import base64
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from rag.mailer import ConsoleMailer, MailError

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")
MIN_PASSWORD, MAX_PASSWORD = 8, 128
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


class AuthError(Exception):
    """A request the user can fix or must wait out. `status` is the HTTP status to answer with."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass(frozen=True)
class Pending:
    """An account that exists but whose email address has not been confirmed yet."""
    email: str


@dataclass(frozen=True)
class Session:
    kind: str                  # "user" or "guest"
    subject: str               # "u:<id>" or "g:<random>"
    email: str | None = None


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), dklen=32, **_SCRYPT)
        return hmac.compare_digest(digest, bytes.fromhex(digest_hex))
    except ValueError:
        return False


_DUMMY_HASH = hash_password("not-a-real-password")      # so an unknown email costs the same time as a wrong password


class Throttle:
    """At most `limit` events per `window` seconds for each key."""

    def __init__(self, limit: int, window: float, clock=time.time):
        self.limit, self.window, self.clock = limit, window, clock
        self.events: dict[str, deque] = defaultdict(deque)

    def _trim(self, key: str) -> deque:
        q = self.events[key]
        cutoff = self.clock() - self.window
        while q and q[0] <= cutoff:
            q.popleft()
        return q

    def blocked(self, key: str) -> bool:
        return len(self._trim(key)) >= self.limit

    def record(self, key: str) -> None:
        self._trim(key).append(self.clock())

    def reset(self, key: str) -> None:
        self.events.pop(key, None)


class AuthService:
    def __init__(self, db_path: str, secret: str, guest_limit: int = 5, user_limit: int = 30,
                 session_days: int = 7, clock=time.time, require_verification: bool = False, mailer=None,
                 verify_hours: int = 24, resend_seconds: int = 60):
        if len(secret) < 16:
            raise ValueError("the session secret must be at least 16 characters")
        self.db_path, self.secret = db_path, secret.encode()
        self.guest_limit, self.user_limit = guest_limit, user_limit
        self.session_seconds = session_days * 86400
        self.clock = clock
        self.login_failures = Throttle(5, 15 * 60, clock)
        self.signups = Throttle(10, 3600, clock)
        self.guests = Throttle(20, 3600, clock)
        self.resends = Throttle(10, 3600, clock)
        self.require_verification, self.mailer = require_verification, mailer or ConsoleMailer()
        self.verify_hours, self.resend_seconds = verify_hours, resend_seconds
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._db() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, "
                         "pw_hash TEXT NOT NULL, created_at REAL NOT NULL, verified_at REAL, verify_nonce TEXT, last_sent REAL)")
            have = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
            for column, kind in (("verified_at", "REAL"), ("verify_nonce", "TEXT"), ("last_sent", "REAL")):
                if column not in have:                    # a database made before email verification existed
                    conn.execute(f"ALTER TABLE users ADD COLUMN {column} {kind}")
            conn.execute("CREATE TABLE IF NOT EXISTS usage (subject TEXT NOT NULL, day TEXT NOT NULL, "
                         "count INTEGER NOT NULL, PRIMARY KEY (subject, day))")

    # -- storage --------------------------------------------------------------------------------

    def _db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return _Closing(conn)

    def _today(self) -> str:
        return datetime.fromtimestamp(self.clock(), timezone.utc).strftime("%Y-%m-%d")

    # -- tokens ---------------------------------------------------------------------------------

    def _sign(self, payload: bytes) -> str:
        return base64.urlsafe_b64encode(hmac.new(self.secret, payload, hashlib.sha256).digest()).decode().rstrip("=")

    def issue(self, session: Session) -> str:
        body = {"k": session.kind, "s": session.subject, "e": int(self.clock()) + self.session_seconds}
        payload = base64.urlsafe_b64encode(json.dumps(body, separators=(",", ":")).encode()).decode().rstrip("=")
        return f"{payload}.{self._sign(payload.encode())}"

    def _unpack(self, token: str | None) -> dict | None:
        """The signed contents of a token, or None if it is missing, malformed or its signature is wrong."""
        if not token or token.count(".") != 1:
            return None
        payload, signature = token.split(".")
        if not hmac.compare_digest(signature, self._sign(payload.encode())):
            return None
        try:
            body = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        except ValueError:
            return None
        return body if isinstance(body, dict) else None

    def _pack(self, body: dict, hours: float) -> str:
        body = {**body, "x": int(self.clock() + hours * 3600)}
        payload = base64.urlsafe_b64encode(json.dumps(body, separators=(",", ":")).encode()).decode().rstrip("=")
        return f"{payload}.{self._sign(payload.encode())}"

    def read(self, token: str | None) -> Session | None:
        """The session a cookie value stands for, or None if it is missing, forged, expired or the user is gone."""
        body = self._unpack(token)
        if body is None:
            return None
        try:
            kind, subject, expires = body["k"], body["s"], body["e"]
        except KeyError:
            return None
        if not isinstance(expires, int) or expires < self.clock() or kind not in ("user", "guest"):
            return None
        if kind == "guest":
            return Session("guest", subject)
        with self._db() as conn:
            row = conn.execute("SELECT email, verified_at FROM users WHERE id = ?", (subject.removeprefix("u:"),)).fetchone()
        if row is None or (self.require_verification and row["verified_at"] is None):
            return None
        return Session("user", subject, row["email"])

    # -- accounts -------------------------------------------------------------------------------

    @staticmethod
    def _check_email(email: str) -> str:
        email = (email or "").strip().lower()
        if len(email) > 254 or not EMAIL_RE.match(email):
            raise AuthError(422, "Enter a valid email address.")
        return email

    @staticmethod
    def _check_password(password: str) -> str:
        if not isinstance(password, str) or not MIN_PASSWORD <= len(password) <= MAX_PASSWORD:
            raise AuthError(422, f"Use a password of {MIN_PASSWORD} to {MAX_PASSWORD} characters.")
        return password

    def signup(self, email: str, password: str, address: str, link_base: str = "") -> "Session | Pending":
        """Create an account. With verification on this returns Pending and emails a confirmation link instead
        of signing the person in."""
        email, password = self._check_email(email), self._check_password(password)
        if self.signups.blocked(address):
            raise AuthError(429, "Too many accounts were created from this address. Try again later.")
        self.signups.record(address)
        now, pw_hash = self.clock(), hash_password(password)
        if not self.require_verification:
            try:
                with self._db() as conn:
                    cursor = conn.execute("INSERT INTO users (email, pw_hash, created_at, verified_at) VALUES (?, ?, ?, ?)",
                                          (email, pw_hash, now, now))
                    user_id = cursor.lastrowid
            except sqlite3.IntegrityError:
                raise AuthError(409, "That email already has an account. Sign in instead.") from None
            return Session("user", f"u:{user_id}", email)

        nonce = secrets.token_urlsafe(9)
        with self._db() as conn:
            row = conn.execute("SELECT id, verified_at FROM users WHERE email = ?", (email,)).fetchone()
            if row is not None and row["verified_at"] is not None:
                raise AuthError(409, "That email already has an account. Sign in instead.")
            if row is not None:    # signing up again while still pending replaces the password and the link
                conn.execute("UPDATE users SET pw_hash = ?, verify_nonce = ?, last_sent = ? WHERE id = ?", (pw_hash, nonce, now, row["id"]))
            else:
                conn.execute("INSERT INTO users (email, pw_hash, created_at, verify_nonce, last_sent) VALUES (?, ?, ?, ?, ?)",
                             (email, pw_hash, now, nonce, now))
        self._send_verification(email, nonce, link_base)
        return Pending(email)

    def _send_verification(self, email: str, nonce: str, link_base: str) -> None:
        token = self._pack({"k": "verify", "m": email, "n": nonce}, self.verify_hours)
        link = f"{link_base.rstrip('/')}/#/verify?token={token}"
        body = (f"Hi,\n\nConfirm your email address to finish creating your RAG Citation Agent account:\n\n{link}\n\n"
                f"The link works for {self.verify_hours} hours and can be used once. If you didn't sign up, you can ignore this email.\n")
        try:
            self.mailer.send(email, "Confirm your email for RAG Citation Agent", body)
        except MailError:
            raise AuthError(502, "We couldn't send the confirmation email. Check the address, or try again in a minute.") from None

    def verify(self, token: str) -> Session:
        """Confirm an email address from its link. Raises AuthError if the link is wrong, old or already used."""
        body = self._unpack(token)
        if body is None or body.get("k") != "verify" or not isinstance(body.get("m"), str) or not isinstance(body.get("x"), int):
            raise AuthError(400, "This confirmation link isn't valid.")
        if body["x"] < self.clock():
            raise AuthError(410, "This confirmation link has expired. Sign up again to get a new one.")
        with self._db() as conn:
            row = conn.execute("SELECT id, verified_at, verify_nonce FROM users WHERE email = ?", (body["m"],)).fetchone()
            if row is None:
                raise AuthError(400, "This confirmation link isn't valid.")
            if row["verified_at"] is not None:
                raise AuthError(409, "This link was already used. Sign in instead.")
            if not row["verify_nonce"] or not hmac.compare_digest(str(row["verify_nonce"]), str(body.get("n", ""))):
                raise AuthError(410, "This link was replaced by a newer one. Use the latest email, or sign up again.")
            conn.execute("UPDATE users SET verified_at = ?, verify_nonce = NULL WHERE id = ?", (self.clock(), row["id"]))
        return Session("user", f"u:{row['id']}", body["m"])

    def resend(self, email: str, address: str, link_base: str = "") -> None:
        """Send a fresh link to an account that is waiting for confirmation. Says nothing about whether the address
        has an account, and sends at most one email a minute per account."""
        email = (email or "").strip().lower()
        if self.resends.blocked(address):
            raise AuthError(429, "Too many requests. Try again later.")
        self.resends.record(address)
        if not self.require_verification:
            return
        nonce = secrets.token_urlsafe(9)
        with self._db() as conn:
            row = conn.execute("SELECT id, verified_at, last_sent FROM users WHERE email = ?", (email,)).fetchone()
            if row is None or row["verified_at"] is not None:
                return
            if row["last_sent"] and self.clock() - row["last_sent"] < self.resend_seconds:
                return
            conn.execute("UPDATE users SET verify_nonce = ?, last_sent = ? WHERE id = ?", (nonce, self.clock(), row["id"]))
        self._send_verification(email, nonce, link_base)

    def login(self, email: str, password: str, address: str) -> Session:
        email = (email or "").strip().lower()
        key = f"{address}|{email}"
        if self.login_failures.blocked(key):
            raise AuthError(429, "Too many failed attempts. Wait a few minutes and try again.")
        with self._db() as conn:
            row = conn.execute("SELECT id, pw_hash, verified_at FROM users WHERE email = ?", (email,)).fetchone()
        ok = verify_password(password if isinstance(password, str) else "", row["pw_hash"] if row else _DUMMY_HASH)
        if not row or not ok:
            self.login_failures.record(key)
            raise AuthError(401, "Incorrect email or password.")
        self.login_failures.reset(key)
        if self.require_verification and row["verified_at"] is None:     # only said after the password was right
            raise AuthError(403, f"Confirm your email first. We sent a link to {email}. Use the button below to get a new one.")
        return Session("user", f"u:{row['id']}", email)

    def guest(self, address: str) -> Session:
        if self.guests.blocked(address):
            raise AuthError(429, "Too many guest sessions from this address. Try again later.")
        self.guests.record(address)
        return Session("guest", f"g:{secrets.token_hex(8)}")

    # -- daily question limit -------------------------------------------------------------------

    def limit_for(self, session: Session) -> int:
        return self.guest_limit if session.kind == "guest" else self.user_limit

    def _used(self, subject: str) -> int:
        with self._db() as conn:
            row = conn.execute("SELECT count FROM usage WHERE subject = ? AND day = ?", (subject, self._today())).fetchone()
        return row["count"] if row else 0

    def remaining(self, session: Session) -> int:
        return max(0, self.limit_for(session) - self._used(session.subject))

    def _take(self, subject: str, limit: int) -> bool:
        with self._db() as conn:
            cursor = conn.execute(
                "INSERT INTO usage (subject, day, count) VALUES (?, ?, 1) "
                "ON CONFLICT (subject, day) DO UPDATE SET count = count + 1 WHERE count < ?",
                (subject, self._today(), limit))
            return cursor.rowcount == 1

    def consume(self, session: Session, address: str) -> None:
        """Count one question, or raise 429 when today's limit is used up.

        Guests are also counted per address, with a wider cap, so clearing cookies for a fresh guest session
        does not give unlimited questions."""
        limit = self.limit_for(session)
        if not self._take(session.subject, limit):
            who = "guests" if session.kind == "guest" else "accounts"
            extra = f" Create a free account for {self.user_limit} a day." if session.kind == "guest" else ""
            raise AuthError(429, f"Daily question limit reached ({limit} a day for {who}).{extra} It resets at midnight UTC.")
        if session.kind == "guest" and not self._take(f"ip:{address}", self.guest_limit * 5):
            self.refund(session, address, address_too=False)
            raise AuthError(429, "Daily question limit reached for this network. It resets at midnight UTC.")

    def refund(self, session: Session, address: str, address_too: bool = True) -> None:
        """Give back a question that failed upstream, so an outage doesn't use up someone's day."""
        subjects = [session.subject] + ([f"ip:{address}"] if session.kind == "guest" and address_too else [])
        with self._db() as conn:
            for subject in subjects:
                conn.execute("UPDATE usage SET count = count - 1 WHERE subject = ? AND day = ? AND count > 0",
                             (subject, self._today()))


class _Closing:
    """A sqlite connection that commits on success and always closes (sqlite3's own `with` doesn't close)."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def __enter__(self) -> sqlite3.Connection:
        return self.conn

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            self.conn.commit() if exc_type is None else self.conn.rollback()
        finally:
            self.conn.close()
