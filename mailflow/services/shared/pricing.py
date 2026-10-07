"""Credits and pricing.

One credit sends one email. Credits are integers - never floats, never a
currency amount at rest. Money only appears when a pack is purchased, and is
stored in cents for the same reason.
"""

# $10 per 10,000 emails is the headline rate: 0.1 cent per email.
RATE_CENTS_PER_1000 = 100

PACKS = [
    {"id": "p10", "credits": 10_000, "cents": 1_000, "label": "$10"},
    {"id": "p45", "credits": 50_000, "cents": 4_500, "label": "$45", "save": "10% off"},
    {"id": "p160", "credits": 200_000, "cents": 16_000, "label": "$160", "save": "20% off"},
]

# Granted on signup so a new account can try the API before paying.
SIGNUP_GRANT = 200

# What each operation costs. Verification is free - charging for it would push
# customers to cache codes themselves, which is the thing we are selling them
# out of doing.
COST = {
    "send": 1,
    "otp_send": 1,
    "otp_verify": 0,
}


def get_pack(pack_id):
    for p in PACKS:
        if p["id"] == pack_id:
            return p
    return None


def credits_to_usd(credits):
    return round(credits * RATE_CENTS_PER_1000 / 1000 / 100, 2)
