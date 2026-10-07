# ---------------------------------------------------------------------------
# Dashboard: private S3 bucket behind CloudFront, served at app.ohteapea.com.
# CloudFront certificates must live in us-east-1 regardless of the API region.
# ---------------------------------------------------------------------------

provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}

resource "aws_s3_bucket" "web" {
  bucket = "mailflow-web-${local.account_id}"
}

resource "aws_s3_bucket_public_access_block" "web" {
  bucket                  = aws_s3_bucket.web.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_cloudfront_origin_access_control" "web" {
  name                              = "mailflow-web"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_acm_certificate" "web" {
  provider          = aws.us_east_1
  domain_name       = var.app_domain
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "web_cert" {
  for_each = {
    for d in aws_acm_certificate.web.domain_validation_options :
    d.domain_name => { name = d.resource_record_name, type = d.resource_record_type, value = d.resource_record_value }
  }
  zone_id         = data.aws_route53_zone.root.zone_id
  name            = each.value.name
  type            = each.value.type
  records         = [each.value.value]
  ttl             = 60
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "web" {
  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.web.arn
  validation_record_fqdns = [for r in aws_route53_record.web_cert : r.fqdn]
}

resource "aws_cloudfront_distribution" "web" {
  enabled             = true
  default_root_object = "index.html"
  aliases             = [var.app_domain]
  price_class         = "PriceClass_All"

  origin {
    domain_name              = aws_s3_bucket.web.bucket_regional_domain_name
    origin_id                = "s3"
    origin_access_control_id = aws_cloudfront_origin_access_control.web.id
  }

  default_cache_behavior {
    target_origin_id       = "s3"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    # AWS managed CachingOptimized.
    cache_policy_id = "658327ea-f89d-4fab-a63d-7e88639e58f6"
  }

  # The SPA reads ?code= on the OAuth callback, so unknown paths must return
  # index.html rather than a 404.
  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
  }

  restrictions {
    geo_restriction { restriction_type = "none" }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.web.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }
}

data "aws_iam_policy_document" "web_bucket" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.web.arn}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.web.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "web" {
  bucket = aws_s3_bucket.web.id
  policy = data.aws_iam_policy_document.web_bucket.json
}

resource "aws_route53_record" "web" {
  zone_id = data.aws_route53_zone.root.zone_id
  name    = var.app_domain
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.web.domain_name
    zone_id                = aws_cloudfront_distribution.web.hosted_zone_id
    evaluate_target_health = false
  }
}

# Generated so the SPA never hardcodes ids that terraform owns.
resource "aws_s3_object" "config" {
  bucket       = aws_s3_bucket.web.id
  key          = "config.js"
  content_type = "application/javascript"
  cache_control = "no-cache"
  content = <<-JS
    window.MF_CONFIG = {
      apiBase: "https://${var.api_domain}",
      region: "${var.region}",
      cognitoDomain: "https://${aws_cognito_user_pool_domain.main.domain}.auth.${var.region}.amazoncognito.com",
      clientId: "${aws_cognito_user_pool_client.web.id}",
      redirectUri: "https://${var.app_domain}/",
    };
  JS
}

resource "aws_s3_object" "index" {
  bucket        = aws_s3_bucket.web.id
  key           = "index.html"
  content_type  = "text/html"
  cache_control = "no-cache"
  source        = "${path.module}/../../web/index.html"
  etag          = filemd5("${path.module}/../../web/index.html")
}
