import pytest

from rag.auth import AuthError, AuthService, Session, Throttle, hash_password, verify_password

SECRET = "a-test-secret-that-is-long-enough"


class Clock:
    def __init__(self, now=1_700_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def auth(tmp_path, clock):
    return AuthService(str(tmp_path / "auth.sqlite"), SECRET, guest_limit=2, user_limit=3, clock=clock)


def test_passwords_are_hashed_salted_and_checked():
    stored = hash_password("correct horse")
    assert "correct horse" not in stored
    assert verify_password("correct horse", stored)
    assert not verify_password("wrong", stored)
    assert hash_password("correct horse") != stored                      # a fresh salt every time
    assert not verify_password("x", "not-a-hash") and not verify_password("x", "scrypt$zz$zz")


def test_signup_then_login(auth):
    session = auth.signup("  Ada@Example.com ", "longenough1", "1.1.1.1")
    assert session.kind == "user" and session.email == "ada@example.com"
    assert auth.login("ada@example.com", "longenough1", "1.1.1.1").subject == session.subject


@pytest.mark.parametrize("email,password,fragment", [
    ("not-an-email", "longenough1", "valid email"),
    ("a@b", "longenough1", "valid email"),
    ("ada@example.com", "short", "password"),
    ("ada@example.com", "x" * 129, "password"),
])
def test_signup_rejects_bad_input(auth, email, password, fragment):
    with pytest.raises(AuthError) as error:
        auth.signup(email, password, "1.1.1.1")
    assert error.value.status == 422 and fragment in error.value.message


def test_duplicate_email_is_refused_even_with_different_case(auth):
    auth.signup("ada@example.com", "longenough1", "1.1.1.1")
    with pytest.raises(AuthError) as error:
        auth.signup("ADA@example.com", "otherpass99", "1.1.1.1")
    assert error.value.status == 409


def test_wrong_password_and_unknown_email_look_the_same(auth):
    auth.signup("ada@example.com", "longenough1", "1.1.1.1")
    messages = set()
    for email, password in [("ada@example.com", "wrongpass1"), ("nobody@example.com", "longenough1")]:
        with pytest.raises(AuthError) as error:
            auth.login(email, password, "1.1.1.1")
        assert error.value.status == 401
        messages.add(error.value.message)
    assert len(messages) == 1                                              # no hint about which emails exist


def test_repeated_failures_lock_that_address_and_email_for_a_while(auth, clock):
    auth.signup("ada@example.com", "longenough1", "1.1.1.1")
    for _ in range(5):
        with pytest.raises(AuthError):
            auth.login("ada@example.com", "wrongpass1", "9.9.9.9")
    with pytest.raises(AuthError) as error:                                # even the right password is refused now
        auth.login("ada@example.com", "longenough1", "9.9.9.9")
    assert error.value.status == 429
    assert auth.login("ada@example.com", "longenough1", "2.2.2.2")         # another address is unaffected
    clock.now += 16 * 60
    assert auth.login("ada@example.com", "longenough1", "9.9.9.9")         # and the lock expires


def test_session_tokens_round_trip_and_reject_tampering(auth):
    user = auth.signup("ada@example.com", "longenough1", "1.1.1.1")
    token = auth.issue(user)
    assert auth.read(token) == user

    payload, signature = token.split(".")
    for forged in [f"{payload}.{signature[:-2]}xx", f"{payload}x.{signature}", payload, "", None, "a.b.c", "."]:
        assert auth.read(forged) is None

    other = AuthService(auth.db_path, "a-different-secret-entirely", clock=auth.clock)
    assert other.read(token) is None                                       # signed with another secret


def test_tokens_expire(auth, clock):
    token = auth.issue(auth.guest("1.1.1.1"))
    clock.now += 6 * 86400
    assert auth.read(token) is not None
    clock.now += 2 * 86400
    assert auth.read(token) is None


def test_a_token_for_a_deleted_user_is_not_a_session(auth):
    user = auth.signup("ada@example.com", "longenough1", "1.1.1.1")
    token = auth.issue(user)
    other = AuthService(str(auth.db_path) + ".new", SECRET, clock=auth.clock)   # a database without that user
    assert other.read(token) is None


def test_the_secret_must_be_long_enough(tmp_path):
    with pytest.raises(ValueError):
        AuthService(str(tmp_path / "a.sqlite"), "short")


def test_guests_have_a_smaller_daily_limit_that_resets(auth, clock):
    guest = auth.guest("1.1.1.1")
    assert auth.remaining(guest) == 2
    auth.consume(guest, "1.1.1.1")
    auth.consume(guest, "1.1.1.1")
    assert auth.remaining(guest) == 0
    with pytest.raises(AuthError) as error:
        auth.consume(guest, "1.1.1.1")
    assert error.value.status == 429 and "free account" in error.value.message
    clock.now += 86400
    assert auth.remaining(guest) == 2


def test_accounts_get_the_larger_limit(auth):
    user = auth.signup("ada@example.com", "longenough1", "1.1.1.1")
    for _ in range(3):
        auth.consume(user, "1.1.1.1")
    with pytest.raises(AuthError) as error:
        auth.consume(user, "1.1.1.1")
    assert error.value.status == 429 and "accounts" in error.value.message


def test_a_failed_question_is_refunded(auth):
    guest = auth.guest("1.1.1.1")
    auth.consume(guest, "1.1.1.1")
    auth.refund(guest, "1.1.1.1")
    assert auth.remaining(guest) == 2
    auth.refund(guest, "1.1.1.1")                                          # never goes below zero used
    assert auth.remaining(guest) == 2


def test_new_guest_sessions_from_one_address_share_a_wider_cap(auth):
    # guest_limit is 2, so one address may ask 2 * 5 = 10 questions a day however many guests it makes
    asked = 0
    with pytest.raises(AuthError):
        for _ in range(20):
            auth.consume(auth.guest("5.5.5.5"), "5.5.5.5")
            asked += 1
    assert asked == 10


def test_throttle_counts_within_its_window(clock):
    throttle = Throttle(2, 60, clock)
    throttle.record("k"); throttle.record("k")
    assert throttle.blocked("k") and not throttle.blocked("other")
    clock.now += 61
    assert not throttle.blocked("k")


def test_session_is_a_plain_value():
    assert Session("guest", "g:1") == Session("guest", "g:1")
