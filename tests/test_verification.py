import re
import sqlite3
from unittest import mock

import pytest

from rag.auth import AuthError, AuthService, Pending, Session
from rag.mailer import ConsoleMailer, MailError, SmtpMailer, mailer_from_env

SECRET = "a-test-secret-that-is-long-enough"
BASE = "https://demo.example"


class Clock:
    def __init__(self):
        self.now = 1_700_000_000.0

    def __call__(self):
        return self.now


class Outbox:
    """Collects the emails instead of sending them."""

    def __init__(self):
        self.sent = []
        self.fail = False

    def send(self, to, subject, body):
        if self.fail:
            raise MailError("smtp down")
        self.sent.append((to, subject, body))

    def token(self, index=-1):
        return re.search(r"token=([\w\-.=]+)", self.sent[index][2]).group(1)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def box():
    return Outbox()


@pytest.fixture
def auth(tmp_path, clock, box):
    return AuthService(str(tmp_path / "auth.sqlite"), SECRET, clock=clock, require_verification=True, mailer=box)


def signup(auth, email="ada@example.com", password="longenough1", address="1.1.1.1"):
    return auth.signup(email, password, address, BASE)


def test_signup_waits_for_the_email_and_sends_one_link(auth, box):
    result = signup(auth, "  Ada@Example.com ")
    assert result == Pending("ada@example.com")
    assert len(box.sent) == 1
    to, subject, body = box.sent[0]
    assert to == "ada@example.com" and "Confirm your email" in subject
    assert f"{BASE}/#/verify?token=" in body and "24 hours" in body and "longenough1" not in body


def test_an_unconfirmed_account_cannot_sign_in(auth):
    signup(auth)
    with pytest.raises(AuthError) as error:
        auth.login("ada@example.com", "longenough1", "1.1.1.1")
    assert error.value.status == 403 and "Confirm your email" in error.value.message
    with pytest.raises(AuthError) as wrong:                                   # a wrong password never hints the account exists
        auth.login("ada@example.com", "not-the-password", "1.1.1.1")
    assert wrong.value.status == 401


def test_the_link_confirms_the_account_and_signs_in(auth, box):
    signup(auth)
    session = auth.verify(box.token())
    assert session.kind == "user" and session.email == "ada@example.com"
    assert auth.login("ada@example.com", "longenough1", "1.1.1.1").subject == session.subject
    assert auth.read(auth.issue(session)) == session


def test_a_link_works_once(auth, box):
    signup(auth)
    token = box.token()
    auth.verify(token)
    with pytest.raises(AuthError) as error:
        auth.verify(token)
    assert error.value.status == 409 and "already used" in error.value.message


def test_forged_and_wrong_links_are_refused(auth, box):
    signup(auth)
    token = box.token()
    payload, signature = token.split(".")
    for bad in ["", "nonsense", f"{payload}.{signature[:-2]}xx", f"{payload}x.{signature}", None]:
        with pytest.raises(AuthError) as error:
            auth.verify(bad)
        assert error.value.status == 400
    session_token = auth.issue(Session("guest", "g:1"))                        # a session cookie is not a confirmation link
    with pytest.raises(AuthError) as error:
        auth.verify(session_token)
    assert error.value.status == 400


def test_links_expire(auth, box, clock):
    signup(auth)
    token = box.token()
    clock.now += 25 * 3600
    with pytest.raises(AuthError) as error:
        auth.verify(token)
    assert error.value.status == 410 and "expired" in error.value.message


def test_signing_up_again_while_pending_replaces_the_password_and_the_old_link(auth, box):
    signup(auth, password="firstpassword1")
    old = box.token()
    signup(auth, password="secondpassword2")
    assert len(box.sent) == 2
    with pytest.raises(AuthError) as error:
        auth.verify(old)
    assert error.value.status == 410 and "replaced" in error.value.message
    auth.verify(box.token())
    assert auth.login("ada@example.com", "secondpassword2", "1.1.1.1")
    with pytest.raises(AuthError):
        auth.login("ada@example.com", "firstpassword1", "1.1.1.1")


def test_a_confirmed_address_cannot_be_taken_again(auth, box):
    signup(auth)
    auth.verify(box.token())
    with pytest.raises(AuthError) as error:
        signup(auth, password="otherpassword3")
    assert error.value.status == 409


def test_resend_gives_a_fresh_link_and_retires_the_old_one(auth, box, clock):
    signup(auth)
    old = box.token()
    clock.now += 61
    auth.resend("ada@example.com", "1.1.1.1", BASE)
    assert len(box.sent) == 2
    with pytest.raises(AuthError):
        auth.verify(old)
    assert auth.verify(box.token()).email == "ada@example.com"


def test_resend_is_limited_and_reveals_nothing(auth, box, clock):
    signup(auth)
    auth.resend("ada@example.com", "1.1.1.1", BASE)                           # within a minute: quietly nothing new
    assert len(box.sent) == 1
    auth.resend("nobody@example.com", "1.1.1.1", BASE)                        # no such account: same quiet answer
    auth.verify(box.token())
    auth.resend("ada@example.com", "1.1.1.1", BASE)                           # already confirmed: same quiet answer
    assert len(box.sent) == 1
    with pytest.raises(AuthError) as error:                                   # but one address can't ask forever
        for _ in range(12):
            auth.resend("x@example.com", "9.9.9.9", BASE)
    assert error.value.status == 429


def test_a_failed_send_is_reported_and_the_account_stays_pending(auth, box):
    box.fail = True
    with pytest.raises(AuthError) as error:
        signup(auth)
    assert error.value.status == 502 and "couldn't send" in error.value.message
    box.fail = False
    assert signup(auth) == Pending("ada@example.com")                          # trying again works
    assert len(box.sent) == 1


def test_without_verification_signup_signs_in_as_before(tmp_path):
    auth = AuthService(str(tmp_path / "a.sqlite"), SECRET)
    session = auth.signup("ada@example.com", "longenough1", "1.1.1.1")
    assert isinstance(session, Session) and auth.login("ada@example.com", "longenough1", "1.1.1.1")


def test_turning_verification_on_locks_out_unconfirmed_old_accounts_and_their_sessions(tmp_path, box):
    path = str(tmp_path / "a.sqlite")
    before = AuthService(path, SECRET)                                         # verification off: ada signs up and is signed in
    token = before.issue(before.signup("ada@example.com", "longenough1", "1.1.1.1"))
    assert before.read(token) is not None
    after = AuthService(path, SECRET, require_verification=True, mailer=box)
    assert after.read(token) is not None                                       # signed up while verification was off: counts as confirmed


def test_an_old_database_without_the_new_columns_is_upgraded(tmp_path, box):
    path = str(tmp_path / "old.sqlite")
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, pw_hash TEXT NOT NULL, created_at REAL NOT NULL)")
    from rag.auth import hash_password
    conn.execute("INSERT INTO users (email, pw_hash, created_at) VALUES (?, ?, ?)", ("old@example.com", hash_password("longenough1"), 1.0))
    conn.commit()
    conn.close()
    auth = AuthService(path, SECRET, require_verification=True, mailer=box)
    with pytest.raises(AuthError) as error:                                    # an account made before verification existed was never confirmed
        auth.login("old@example.com", "longenough1", "1.1.1.1")
    assert error.value.status == 403
    auth.resend("old@example.com", "1.1.1.1", BASE)
    assert auth.verify(box.token()).email == "old@example.com"
    assert auth.login("old@example.com", "longenough1", "1.1.1.1")


# ---- the mailers ----

def test_console_mailer_prints_the_message(capsys):
    ConsoleMailer().send("a@b.co", "Hello", "the link is here")
    out = capsys.readouterr().out
    assert "a@b.co" in out and "the link is here" in out and "not sent" in out


def test_smtp_mailer_uses_starttls_and_logs_in():
    with mock.patch("rag.mailer.smtplib.SMTP") as smtp:
        client = smtp.return_value
        SmtpMailer("smtp.example.com", 587, "user", "pw", "noreply@example.com").send("to@x.co", "Subject", "Body")
    smtp.assert_called_once_with("smtp.example.com", 587, timeout=10.0)
    client.starttls.assert_called_once()
    client.login.assert_called_once_with("user", "pw")
    sent = client.send_message.call_args.args[0]
    assert sent["To"] == "to@x.co" and sent["From"] == "noreply@example.com" and sent["Subject"] == "Subject"


def test_smtp_mailer_ssl_mode_and_failures():
    with mock.patch("rag.mailer.smtplib.SMTP_SSL") as ssl_smtp:
        SmtpMailer("smtp.example.com", 465, "u", "p", security="ssl").send("to@x.co", "S", "B")
    ssl_smtp.assert_called_once()
    import smtplib
    with mock.patch("rag.mailer.smtplib.SMTP", side_effect=smtplib.SMTPConnectError(421, "no")):
        with pytest.raises(MailError):
            SmtpMailer("smtp.example.com", user="u", password="p").send("to@x.co", "S", "B")
    with mock.patch("rag.mailer.smtplib.SMTP", side_effect=OSError("unreachable")):
        with pytest.raises(MailError):
            SmtpMailer("smtp.example.com", user="u", password="p").send("to@x.co", "S", "B")


def test_mailer_settings_are_checked_and_read_from_the_environment():
    assert isinstance(mailer_from_env({}), ConsoleMailer)
    configured = mailer_from_env({"SMTP_HOST": "smtp.example.com", "SMTP_PORT": "2525", "SMTP_USER": "u@example.com", "SMTP_PASSWORD": "p"})
    assert isinstance(configured, SmtpMailer) and configured.port == 2525 and configured.sender == "u@example.com"
    with pytest.raises(ValueError):
        SmtpMailer("smtp.example.com")                                          # no sender address
    with pytest.raises(ValueError):
        SmtpMailer("smtp.example.com", user="u@example.com", security="carrier-pigeon")
