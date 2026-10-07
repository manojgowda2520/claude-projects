"""Cognito custom-auth triggers - passwordless email OTP login.

One function serves all three triggers, dispatched on triggerSource:

    DefineAuthChallenge          decides what happens next
    CreateAuthChallenge          generates the code and emails it
    VerifyAuthChallengeResponse  checks what the user typed

The code lives only in Cognito's encrypted session between Create and Verify -
we never store it. `privateChallengeParameters` is not returned to the client;
`publicChallengeParameters` is, so nothing secret goes in there.
"""

import os
import secrets

import boto3

import otp as otplib

ses = boto3.client("sesv2")

FROM_ADDRESS = os.environ["FROM_ADDRESS"]
CONFIG_SET = os.environ["CONFIG_SET"]
TTL_SECONDS = 600
MAX_ATTEMPTS = 3


def define(event):
    session = event["request"]["session"]
    resp = event["response"]

    if event["request"].get("userNotFound"):
        resp["failAuthentication"] = True
        resp["issueTokens"] = False
        return event

    if session and session[-1].get("challengeResult"):
        # Correct code - hand over the tokens.
        resp["issueTokens"] = True
        resp["failAuthentication"] = False
        return event

    if len(session) >= MAX_ATTEMPTS:
        resp["issueTokens"] = False
        resp["failAuthentication"] = True
        return event

    resp["challengeName"] = "CUSTOM_CHALLENGE"
    resp["issueTokens"] = False
    resp["failAuthentication"] = False
    return event


def create(event):
    session = event["request"]["session"]

    # Reuse the same code across retries within one session, so a typo does not
    # invalidate the code already sitting in the user's inbox.
    previous = next((s for s in reversed(session)
                     if s.get("challengeMetadata", "").startswith("CODE-")), None)
    if previous:
        code = previous["challengeMetadata"][5:]
    else:
        code = otplib.generate_code(6)
        _send(event["request"]["userAttributes"].get("email"), code)

    event["response"]["privateChallengeParameters"] = {"code": code}
    event["response"]["publicChallengeParameters"] = {"email": _mask(
        event["request"]["userAttributes"].get("email", ""))}
    event["response"]["challengeMetadata"] = "CODE-" + code
    return event


def verify(event):
    expected = event["request"]["privateChallengeParameters"]["code"]
    given = (event["request"].get("challengeAnswer") or "").strip()
    # Constant-time: a byte-wise compare leaks the code through timing.
    event["response"]["answerCorrect"] = secrets.compare_digest(expected, given)
    return event


def _mask(email):
    name, _, domain = email.partition("@")
    if len(name) <= 2:
        return name[:1] + "***@" + domain
    return name[:2] + "***@" + domain


def _send(email, code):
    subject, html, text = otplib.render(code, TTL_SECONDS, brand="Mailflow")
    ses.send_email(
        FromEmailAddress=FROM_ADDRESS,
        Destination={"ToAddresses": [email]},
        Content={"Simple": {
            "Subject": {"Data": "Your Mailflow sign-in code", "Charset": "UTF-8"},
            "Body": {"Html": {"Data": html, "Charset": "UTF-8"},
                     "Text": {"Data": text, "Charset": "UTF-8"}}}},
        ConfigurationSetName=CONFIG_SET,
        EmailTags=[{"Name": "kind", "Value": "login"}])


_ROUTES = {
    "DefineAuthChallenge_Authentication": define,
    "CreateAuthChallenge_Authentication": create,
    "VerifyAuthChallengeResponse_Authentication": verify,
}


def handler(event, context):
    fn = _ROUTES.get(event.get("triggerSource"))
    # Unknown triggers are returned unchanged; failing here would break sign-in.
    return fn(event) if fn else event
