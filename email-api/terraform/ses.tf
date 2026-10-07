# ---------------------------------------------------------------------------
# Sending identity. Production access is already granted on this account, so
# this only has to establish domain authentication (DKIM/SPF/DMARC).
# ---------------------------------------------------------------------------

resource "aws_sesv2_email_identity" "root" {
  email_identity = var.root_domain

  dkim_signing_attributes {
    next_signing_key_length = "RSA_2048_BIT"
  }

  configuration_set_name = aws_sesv2_configuration_set.main.configuration_set_name
}

resource "aws_route53_record" "dkim" {
  count   = 3
  zone_id = data.aws_route53_zone.root.zone_id
  name    = "${aws_sesv2_email_identity.root.dkim_signing_attributes[0].tokens[count.index]}._domainkey.${var.root_domain}"
  type    = "CNAME"
  ttl     = 600
  records = ["${aws_sesv2_email_identity.root.dkim_signing_attributes[0].tokens[count.index]}.dkim.amazonses.com"]
}

# Custom MAIL FROM: bounces are attributed to mail.ohteapea.com, not the apex.
resource "aws_sesv2_email_identity_mail_from_attributes" "root" {
  email_identity         = aws_sesv2_email_identity.root.email_identity
  mail_from_domain       = "${var.mail_from_subdomain}.${var.root_domain}"
  behavior_on_mx_failure = "USE_DEFAULT_VALUE"
}

resource "aws_route53_record" "mail_from_mx" {
  zone_id = data.aws_route53_zone.root.zone_id
  name    = "${var.mail_from_subdomain}.${var.root_domain}"
  type    = "MX"
  ttl     = 600
  records = ["10 feedback-smtp.${var.region}.amazonses.com"]
}

resource "aws_route53_record" "mail_from_spf" {
  zone_id = data.aws_route53_zone.root.zone_id
  name    = "${var.mail_from_subdomain}.${var.root_domain}"
  type    = "TXT"
  ttl     = 600
  records = ["v=spf1 include:amazonses.com ~all"]
}

resource "aws_route53_record" "root_spf" {
  zone_id = data.aws_route53_zone.root.zone_id
  name    = var.root_domain
  type    = "TXT"
  ttl     = 600
  records = ["v=spf1 include:amazonses.com ~all"]
}

# Start at p=none, watch the aggregate reports for a couple of weeks, then
# tighten to quarantine and finally reject.
resource "aws_route53_record" "dmarc" {
  zone_id = data.aws_route53_zone.root.zone_id
  name    = "_dmarc.${var.root_domain}"
  type    = "TXT"
  ttl     = 600
  records = ["v=DMARC1; p=none; rua=mailto:dmarc@${var.root_domain}; fo=1"]
}

# ---------------------------------------------------------------------------
# Configuration set: per-message event stream, used for bounce/complaint alarms.
# Account-level suppression for bounces and complaints is on by default, so no
# custom suppression handler is needed.
# ---------------------------------------------------------------------------

resource "aws_sesv2_configuration_set" "main" {
  configuration_set_name = "email-api"

  delivery_options {
    tls_policy = "REQUIRE"
  }

  reputation_options {
    reputation_metrics_enabled = true
  }

  sending_options {
    sending_enabled = true
  }

  suppression_options {
    suppressed_reasons = ["BOUNCE", "COMPLAINT"]
  }
}

resource "aws_cloudwatch_log_group" "ses_events" {
  name              = "/aws/ses/email-api-events"
  retention_in_days = 30
}

resource "aws_sesv2_configuration_set_event_destination" "cw" {
  configuration_set_name = aws_sesv2_configuration_set.main.configuration_set_name
  event_destination_name = "cloudwatch"

  event_destination {
    enabled              = true
    matching_event_types = ["SEND", "DELIVERY", "BOUNCE", "COMPLAINT", "REJECT", "RENDERING_FAILURE"]

    cloud_watch_destination {
      dimension_configuration {
        default_dimension_value = "none"
        dimension_name          = "tenant"
        dimension_value_source  = "MESSAGE_TAG"
      }
    }
  }
}
