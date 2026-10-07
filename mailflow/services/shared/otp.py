"""OTP generation, hashing and verification.

Design notes, because the failure modes here are subtle:

* A 6-digit code has a million possibilities. A plain SHA-256 of it is
  reversible by brute force in milliseconds on any laptop, so codes are stored
  as an HMAC keyed with a server-side secret. Someone who dumps the table still
  cannot recover a code.
* The request id is mixed into the MAC, so two accounts issuing the same code
  produce different digests and one stored digest cannot be replayed elsewhere.
* Comparison is constant-time. A byte-by-byte compare leaks the code through
  timing given enough attempts.
* Codes are never returned, logged, or written anywhere but the MAC.
"""

import hashlib
import hmac
import os
import secrets

# Rotating this invalidates every outstanding code, which is the correct
# behaviour if it is ever suspected of leaking.
_SECRET = os.environ["OTP_SECRET"].encode()

MIN_LENGTH = 4
MAX_LENGTH = 8
DEFAULT_LENGTH = 6

DEFAULT_TTL_SECONDS = 600
MIN_TTL_SECONDS = 60
MAX_TTL_SECONDS = 3600

MAX_ATTEMPTS = 5

# OTP-bombing controls, per recipient per account.
RESEND_COOLDOWN_SECONDS = 60
MAX_SENDS_PER_WINDOW = 3
RATE_WINDOW_SECONDS = 600


def generate_code(length=DEFAULT_LENGTH):
    """A cryptographically random numeric code, zero-padded."""
    length = max(MIN_LENGTH, min(int(length), MAX_LENGTH))
    return str(secrets.randbelow(10 ** length)).zfill(length)


def digest(request_id, code):
    return hmac.new(_SECRET,
                    ("%s:%s" % (request_id, code)).encode(),
                    hashlib.sha256).hexdigest()


def matches(request_id, code, stored_digest):
    return hmac.compare_digest(digest(request_id, code), stored_digest)


def recipient_key(account_id, email):
    """Rate-limit key. The address is hashed so the table holds no plaintext
    recipient list that would be worth stealing."""
    h = hashlib.sha256(email.strip().lower().encode()).hexdigest()[:32]
    return "%s#%s" % (account_id, h)


def clamp_ttl(seconds):
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return DEFAULT_TTL_SECONDS
    return max(MIN_TTL_SECONDS, min(seconds, MAX_TTL_SECONDS))


DEFAULT_SUBJECT = "Your verification code"

DEFAULT_HTML = """\
<div style="font:15px/1.6 -apple-system,system-ui,sans-serif;color:#1a1a19;max-width:440px">
  <p>Use this code to continue:</p>
  <p style="font:600 34px/1 ui-monospace,Menlo,monospace;letter-spacing:.14em;
            margin:22px 0;color:#111">{code}</p>
  <p style="color:#6b6b68;font-size:13px">
    This code expires in {minutes} minutes. If you did not request it, ignore this email.
  </p>
</div>"""

DEFAULT_TEXT = """\
Use this code to continue: {code}

It expires in {minutes} minutes. If you did not request it, ignore this email.
"""


def render(code, ttl_seconds, brand=None):
    """Body for the OTP email. `brand` prefixes the subject so the recipient
    sees the customer's name rather than ours."""
    minutes = max(1, ttl_seconds // 60)
    subject = DEFAULT_SUBJECT if not brand else "%s — %s" % (brand, DEFAULT_SUBJECT)
    return (subject,
            DEFAULT_HTML.format(code=code, minutes=minutes),
            DEFAULT_TEXT.format(code=code, minutes=minutes))
