# Deploy runbook — production account (Account A)

Manual CLI walkthrough of the same architecture Terraform builds. Run the steps
in order; each ends with a verification you should see pass before moving on.

Roughly 45 minutes, most of it waiting on DKIM and ACM validation.

---

## Step 0 — Shell setup

```bash
export AWS_PROFILE=prod            # the account with SES production access
export AWS_REGION=ap-south-1       # MUST be the region production access was granted in
export ROOT_DOMAIN=ohteapea.com
export API_DOMAIN=api.ohteapea.com
export MAIL_FROM=mail.ohteapea.com
export ACCT=$(aws sts get-caller-identity --query Account --output text)
echo "account=$ACCT region=$AWS_REGION"
```

Confirm `$ACCT` is the production account before continuing.

---

## Step 1 — Confirm SES production access in this region

```bash
aws sesv2 get-account --query '{Production:ProductionAccessEnabled,Max24h:SendQuota.Max24HourSend,Rate:SendQuota.MaxSendRate,Enabled:SendingEnabled}'
```

Expect `Production: true` and a `Max24h` well above 200. If you see `false` or
`200`, you are in the wrong region — production access is granted per region.
Stop and re-export `AWS_REGION`.

---

## Step 2 — Domain identity and DNS

### 2a. Inspect existing DNS first

```bash
export ZONE_ID=$(aws route53 list-hosted-zones-by-name --dns-name "$ROOT_DOMAIN." --query "HostedZones[?Name=='$ROOT_DOMAIN.'].Id | [0]" --output text | cut -d/ -f3)
echo "zone=$ZONE_ID"
```

```bash
dig +short TXT $ROOT_DOMAIN; dig +short TXT _dmarc.$ROOT_DOMAIN; dig +short MX $ROOT_DOMAIN
```

**If `dig TXT $ROOT_DOMAIN` already returns a `v=spf1 ...` string, do not add a
second one.** Edit the existing record to insert `include:amazonses.com` before
the `~all`. Two SPF records is a permanent-error condition and breaks all your
mail, existing and new.

Likewise if `_dmarc` already exists, leave it — skip 2e.

### 2b. Create the identity

```bash
aws sesv2 create-email-identity --email-identity "$ROOT_DOMAIN" --dkim-signing-attributes NextSigningKeyLength=RSA_2048_BIT
```

Already verified from earlier work? `ConflictException` here is fine — move on.

### 2c. Publish the three DKIM CNAMEs

```bash
aws sesv2 get-email-identity --email-identity "$ROOT_DOMAIN" --query 'DkimAttributes.Tokens' --output text | tr '\t' '\n' | while read t; do printf '{"Changes":[{"Action":"UPSERT","ResourceRecordSet":{"Name":"%s._domainkey.%s","Type":"CNAME","TTL":600,"ResourceRecords":[{"Value":"%s.dkim.amazonses.com"}]}}]}' "$t" "$ROOT_DOMAIN" "$t" > /tmp/dkim.json; aws route53 change-resource-record-sets --hosted-zone-id "$ZONE_ID" --change-batch file:///tmp/dkim.json --query 'ChangeInfo.Status'; done
```

### 2d. Custom MAIL FROM (keeps bounce reputation off the apex)

```bash
aws sesv2 put-email-identity-mail-from-attributes --email-identity "$ROOT_DOMAIN" --mail-from-domain "$MAIL_FROM" --behavior-on-mx-failure USE_DEFAULT_VALUE
```

```bash
printf '{"Changes":[{"Action":"UPSERT","ResourceRecordSet":{"Name":"%s","Type":"MX","TTL":600,"ResourceRecords":[{"Value":"10 feedback-smtp.%s.amazonses.com"}]}},{"Action":"UPSERT","ResourceRecordSet":{"Name":"%s","Type":"TXT","TTL":600,"ResourceRecords":[{"Value":"\\"v=spf1 include:amazonses.com ~all\\""}]}}]}' "$MAIL_FROM" "$AWS_REGION" "$MAIL_FROM" > /tmp/mailfrom.json && aws route53 change-resource-record-sets --hosted-zone-id "$ZONE_ID" --change-batch file:///tmp/mailfrom.json
```

This subdomain is new, so there is no merge hazard here.

### 2e. DMARC — only if none exists (see 2a)

```bash
printf '{"Changes":[{"Action":"CREATE","ResourceRecordSet":{"Name":"_dmarc.%s","Type":"TXT","TTL":600,"ResourceRecords":[{"Value":"\\"v=DMARC1; p=none; rua=mailto:dmarc@%s; fo=1\\""}]}}]}' "$ROOT_DOMAIN" "$ROOT_DOMAIN" > /tmp/dmarc.json && aws route53 change-resource-record-sets --hosted-zone-id "$ZONE_ID" --change-batch file:///tmp/dmarc.json
```

`p=none` is deliberate — it observes without rejecting. Tighten later.

### 2f. Verify (5–15 min)

```bash
aws sesv2 get-email-identity --email-identity "$ROOT_DOMAIN" --query '{Verified:VerifiedForSendingStatus,Dkim:DkimAttributes.Status,MailFrom:MailFromAttributes.MailFromDomainStatus}'
```

Wait for `Verified: true`, `Dkim: SUCCESS`, `MailFrom: SUCCESS`.

---

## Step 3 — Configuration set

```bash
aws sesv2 create-configuration-set --configuration-set-name email-api --delivery-options TlsPolicy=REQUIRE --reputation-options ReputationMetricsEnabled=true --sending-options SendingEnabled=true --suppression-options SuppressedReasons=BOUNCE,COMPLAINT
```

---

## Step 4 — DynamoDB tables

```bash
aws dynamodb create-table --table-name email-api-keys --attribute-definitions AttributeName=key_hash,AttributeType=S --key-schema AttributeName=key_hash,KeyType=HASH --billing-mode PAY_PER_REQUEST --sse-specification Enabled=true
```

```bash
aws dynamodb create-table --table-name email-api-idempotency --attribute-definitions AttributeName=pk,AttributeType=S --key-schema AttributeName=pk,KeyType=HASH --billing-mode PAY_PER_REQUEST --sse-specification Enabled=true
```

```bash
aws dynamodb wait table-exists --table-name email-api-keys && aws dynamodb wait table-exists --table-name email-api-idempotency && aws dynamodb update-time-to-live --table-name email-api-idempotency --time-to-live-specification "Enabled=true,AttributeName=expires_at"
```

---

## Step 5 — IAM roles

```bash
printf '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' > /tmp/trust.json && for r in email-api-mailer email-api-authorizer; do aws iam create-role --role-name $r --assume-role-policy-document file:///tmp/trust.json --query Role.Arn --output text; aws iam attach-role-policy --role-name $r --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole; done
```

Mailer policy. The `ses:FromAddress` condition is the hard backstop — even a
corrupted key row cannot send as an address outside this list.

```bash
cat > /tmp/mailer-policy.json <<JSON
{"Version":"2012-10-17","Statement":[
 {"Sid":"SendThroughOurIdentityOnly","Effect":"Allow","Action":"ses:SendEmail",
  "Resource":["arn:aws:ses:$AWS_REGION:$ACCT:identity/$ROOT_DOMAIN",
              "arn:aws:ses:$AWS_REGION:$ACCT:configuration-set/email-api"],
  "Condition":{"StringEquals":{"ses:FromAddress":[
    "noreply@$ROOT_DOMAIN","alerts@$ROOT_DOMAIN",
    "billing@$ROOT_DOMAIN","support@$ROOT_DOMAIN"]}}},
 {"Effect":"Allow","Action":["dynamodb:PutItem","dynamodb:DeleteItem"],
  "Resource":"arn:aws:dynamodb:$AWS_REGION:$ACCT:table/email-api-idempotency"}]}
JSON
aws iam put-role-policy --role-name email-api-mailer --policy-name email-api-mailer --policy-document file:///tmp/mailer-policy.json
```

```bash
cat > /tmp/authz-policy.json <<JSON
{"Version":"2012-10-17","Statement":[
 {"Effect":"Allow","Action":"dynamodb:GetItem",
  "Resource":"arn:aws:dynamodb:$AWS_REGION:$ACCT:table/email-api-keys"}]}
JSON
aws iam put-role-policy --role-name email-api-authorizer --policy-name email-api-authorizer --policy-document file:///tmp/authz-policy.json
```

---

## Step 6 — Package and create the Lambdas

Run from the repo root.

```bash
(cd src/mailer && zip -q -r /tmp/mailer.zip handler.py) && (cd src/authorizer && zip -q -r /tmp/authorizer.zip handler.py) && ls -la /tmp/mailer.zip /tmp/authorizer.zip
```

IAM role propagation lags a few seconds — if `create-function` fails with an
assume-role error, wait 10s and re-run it.

```bash
aws lambda create-function --function-name email-api-mailer --runtime python3.12 --handler handler.handler --role arn:aws:iam::$ACCT:role/email-api-mailer --zip-file fileb:///tmp/mailer.zip --timeout 15 --memory-size 512 --environment "Variables={IDEMPOTENCY_TABLE=email-api-idempotency,CONFIG_SET=email-api,ROOT_DOMAIN=$ROOT_DOMAIN}"
```

```bash
aws lambda create-function --function-name email-api-authorizer --runtime python3.12 --handler handler.handler --role arn:aws:iam::$ACCT:role/email-api-authorizer --zip-file fileb:///tmp/authorizer.zip --timeout 5 --memory-size 256 --environment "Variables={KEYS_TABLE=email-api-keys}"
```

```bash
export MAILER_ARN=$(aws lambda get-function --function-name email-api-mailer --query Configuration.FunctionArn --output text); export AUTHZ_ARN=$(aws lambda get-function --function-name email-api-authorizer --query Configuration.FunctionArn --output text); echo "$MAILER_ARN"; echo "$AUTHZ_ARN"
```

### Smoke-test the mailer directly, before any API exists

This bypasses API Gateway and proves SES, IAM and the handler all work.
Replace `YOUR_INBOX@example.com` with a real address you can check.

```bash
cat > /tmp/direct.json <<JSON
{"requestContext":{"requestId":"local-test",
  "authorizer":{"lambda":{"tenant":"alerts",
    "allowed_from":"alerts@$ROOT_DOMAIN","max_recipients":"5"}}},
 "body":"{\"to\":[\"YOUR_INBOX@example.com\"],\"subject\":\"email-api smoke test\",\"text\":\"Sent directly via Lambda invoke.\"}"}
JSON
aws lambda invoke --function-name email-api-mailer --payload fileb:///tmp/direct.json /tmp/out.json && cat /tmp/out.json
```

Expect `"statusCode": 202` and an email within a minute. **Do not proceed past a
failure here** — everything downstream assumes this works.

---

## Step 7 — HTTP API, authorizer, route

```bash
export API_ID=$(aws apigatewayv2 create-api --name email-api --protocol-type HTTP --query ApiId --output text) && echo "api=$API_ID"
```

```bash
export INTEG_ID=$(aws apigatewayv2 create-integration --api-id $API_ID --integration-type AWS_PROXY --integration-uri $MAILER_ARN --payload-format-version 2.0 --timeout-in-millis 20000 --query IntegrationId --output text) && echo "integration=$INTEG_ID"
```

```bash
export AUTHZ_ID=$(aws apigatewayv2 create-authorizer --api-id $API_ID --name api-key --authorizer-type REQUEST --identity-source '$request.header.x-api-key' --authorizer-uri "arn:aws:apigateway:$AWS_REGION:lambda:path/2015-03-31/functions/$AUTHZ_ARN/invocations" --authorizer-payload-format-version 2.0 --enable-simple-responses --authorizer-result-ttl-in-seconds 300 --query AuthorizerId --output text) && echo "authorizer=$AUTHZ_ID"
```

```bash
aws apigatewayv2 create-route --api-id $API_ID --route-key 'POST /v1/send' --target "integrations/$INTEG_ID" --authorization-type CUSTOM --authorizer-id $AUTHZ_ID
```

```bash
aws apigatewayv2 create-stage --api-id $API_ID --stage-name '$default' --auto-deploy --default-route-settings 'ThrottlingRateLimit=25,ThrottlingBurstLimit=50'
```

Let API Gateway invoke both functions:

```bash
aws lambda add-permission --function-name email-api-mailer --statement-id apigw-invoke --action lambda:InvokeFunction --principal apigateway.amazonaws.com --source-arn "arn:aws:execute-api:$AWS_REGION:$ACCT:$API_ID/*/*"
```

```bash
aws lambda add-permission --function-name email-api-authorizer --statement-id apigw-invoke-authorizer --action lambda:InvokeFunction --principal apigateway.amazonaws.com --source-arn "arn:aws:execute-api:$AWS_REGION:$ACCT:$API_ID/authorizers/$AUTHZ_ID"
```

```bash
export RAW_URL="https://$API_ID.execute-api.$AWS_REGION.amazonaws.com" && echo "$RAW_URL/v1/send"
```

### Verify auth rejects before it accepts

```bash
curl -s -o /dev/null -w 'no-key:%{http_code}\n' -X POST "$RAW_URL/v1/send" -H 'content-type: application/json' -d '{}'; curl -s -o /dev/null -w 'bad-key:%{http_code}\n' -X POST "$RAW_URL/v1/send" -H 'x-api-key: garbage' -H 'content-type: application/json' -d '{}'
```

Both must be `401`. A `500` means the authorizer is erroring — check the
`/aws/lambda/email-api-authorizer` log group.

---

## Step 8 — Issue a key and send end to end

```bash
python scripts/issue_key.py --region $AWS_REGION --tenant alerts --allowed-from alerts@ohteapea.com --description "first key, manual test"
```

```bash
export EMAIL_API_KEY='<paste the key printed above>'
```

```bash
curl -sS -X POST "$RAW_URL/v1/send" -H "x-api-key: $EMAIL_API_KEY" -H 'content-type: application/json' -d '{"to":["YOUR_INBOX@example.com"],"subject":"email-api live","text":"End to end through API Gateway.","idempotencyKey":"first-test-001"}'
```

Expect `202` with a `messageId`. Run the identical command a second time — it
must return `{"status":"duplicate"}` and send nothing. That confirms
idempotency is working.

---

## Step 9 — Custom domain api.ohteapea.com

```bash
export CERT_ARN=$(aws acm request-certificate --domain-name "$API_DOMAIN" --validation-method DNS --query CertificateArn --output text) && echo "$CERT_ARN"
```

The validation record takes ~30s to appear in the describe output:

```bash
aws acm describe-certificate --certificate-arn $CERT_ARN --query 'Certificate.DomainValidationOptions[0].ResourceRecord' > /tmp/cv.json && cat /tmp/cv.json
```

```bash
python -c "import json;r=json.load(open('/tmp/cv.json'));print(json.dumps({'Changes':[{'Action':'UPSERT','ResourceRecordSet':{'Name':r['Name'],'Type':r['Type'],'TTL':60,'ResourceRecords':[{'Value':r['Value']}]}}]}))" > /tmp/certval.json && aws route53 change-resource-record-sets --hosted-zone-id "$ZONE_ID" --change-batch file:///tmp/certval.json
```

```bash
aws acm wait certificate-validated --certificate-arn $CERT_ARN && echo validated
```

```bash
aws apigatewayv2 create-domain-name --domain-name "$API_DOMAIN" --domain-name-configurations "CertificateArn=$CERT_ARN,EndpointType=REGIONAL,SecurityPolicy=TLS_1_2"
```

```bash
aws apigatewayv2 create-api-mapping --api-id $API_ID --domain-name "$API_DOMAIN" --stage '$default'
```

```bash
aws apigatewayv2 get-domain-name --domain-name "$API_DOMAIN" --query 'DomainNameConfigurations[0].{Target:ApiGatewayDomainName,Zone:HostedZoneId}' > /tmp/dn.json && python -c "import json,os;d=json.load(open('/tmp/dn.json'));print(json.dumps({'Changes':[{'Action':'UPSERT','ResourceRecordSet':{'Name':os.environ['API_DOMAIN'],'Type':'A','AliasTarget':{'DNSName':d['Target'],'HostedZoneId':d['Zone'],'EvaluateTargetHealth':False}}}]}))" > /tmp/apidns.json && aws route53 change-resource-record-sets --hosted-zone-id "$ZONE_ID" --change-batch file:///tmp/apidns.json
```

Final check, once DNS propagates (1–2 min):

```bash
curl -sS -X POST "https://$API_DOMAIN/v1/send" -H "x-api-key: $EMAIL_API_KEY" -H 'content-type: application/json' -d '{"to":["YOUR_INBOX@example.com"],"subject":"live on api.ohteapea.com","text":"Done."}'
```

---

## Step 10 — Alarms, before you hand out keys

SES pauses an account whose bounce rate exceeds 5% or complaint rate 0.1%. You
want to know before Amazon tells you.

```bash
aws cloudwatch put-metric-alarm --alarm-name ses-bounce-rate --namespace AWS/SES --metric-name Reputation.BounceRate --statistic Average --period 900 --evaluation-periods 1 --threshold 0.03 --comparison-operator GreaterThanThreshold --treat-missing-data notBreaching
```

```bash
aws cloudwatch put-metric-alarm --alarm-name ses-complaint-rate --namespace AWS/SES --metric-name Reputation.ComplaintRate --statistic Average --period 900 --evaluation-periods 1 --threshold 0.001 --comparison-operator GreaterThanThreshold --treat-missing-data notBreaching
```

Attach an SNS topic to both with `--alarm-actions` so they actually reach you.

---

## Handing access to another account

Nothing to configure on your side. Issue that team a key, they store it in
their own Secrets Manager or SSM Parameter Store, and they call the endpoint.
No IAM trust, no VPC peering, no policy edit in Account A.

```python
import json, os, urllib.request

req = urllib.request.Request(
    "https://api.ohteapea.com/v1/send",
    data=json.dumps({"to": ["ops@example.com"], "subject": "hi", "text": "there"}).encode(),
    headers={"content-type": "application/json", "x-api-key": os.environ["EMAIL_API_KEY"]},
    method="POST")
print(json.load(urllib.request.urlopen(req, timeout=10)))
```

No SDK and no Lambda layer — `urllib` is in every runtime.

---

## Rollback

```bash
aws apigatewayv2 delete-api --api-id $API_ID; aws lambda delete-function --function-name email-api-mailer; aws lambda delete-function --function-name email-api-authorizer; aws dynamodb delete-table --table-name email-api-keys; aws dynamodb delete-table --table-name email-api-idempotency
```

Delete the custom domain separately (`aws apigatewayv2 delete-domain-name
--domain-name $API_DOMAIN`).

Leave the SES identity and the apex DNS records alone — removing the apex SPF
or MX records affects mail delivery for the whole domain, not just this API.

---

## Moving to Terraform afterwards

Once this is working by hand, `terraform/` in this repo builds the identical
stack. To adopt what you created manually instead of duplicating it, import the
key resources rather than applying onto a clean state:

```bash
cd terraform && terraform import aws_apigatewayv2_api.main $API_ID && terraform import aws_lambda_function.mailer email-api-mailer && terraform import aws_dynamodb_table.api_keys email-api-keys
```

Then run `terraform plan` and reconcile the diff before the first apply.
