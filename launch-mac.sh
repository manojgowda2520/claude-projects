#!/usr/bin/env bash
# One-shot: allocate a Mac Dedicated Host, launch it, and open a VNC tunnel.
# Usage:  ./launch-mac.sh [region] [instance-type]
set -euo pipefail

REGION="${1:-us-east-1}"
ITYPE="${2:-mac2.metal}"
KEY_NAME="manoj"
KEY_FILE="manoj.pem"
SG_NAME="mac-build"
VOL_GB=200
TAG="shipaton-mac"

export AWS_DEFAULT_REGION="$REGION"
say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

[ -f "$KEY_FILE" ] || { echo "Missing $KEY_FILE in $(pwd)"; exit 1; }

VNC_PASS="$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 14)"

say "Finding latest arm64 macOS Sequoia AMI"
AMI=$(aws ec2 describe-images --owners amazon \
  --filters "Name=name,Values=amzn-ec2-macos-15*" "Name=architecture,Values=arm64_mac" \
  --query "reverse(sort_by(Images,&CreationDate))[0].ImageId" --output text)
[ "$AMI" != "None" ] || { echo "No arm64 Sequoia AMI found in $REGION"; exit 1; }
echo "AMI: $AMI"

say "Checking which AZs offer $ITYPE"
AZS=$(aws ec2 describe-instance-type-offerings --location-type availability-zone \
  --filters "Name=instance-type,Values=$ITYPE" \
  --query "InstanceTypeOfferings[].Location" --output text)
[ -n "$AZS" ] || { echo "$ITYPE not offered in $REGION"; exit 1; }
echo "Candidates: $AZS"

say "Allocating Dedicated Host (trying each AZ until one has capacity)"
HOST_ID=""
for AZ in $AZS; do
  echo "  trying $AZ ..."
  if HOST_ID=$(aws ec2 allocate-hosts --instance-type "$ITYPE" --availability-zone "$AZ" \
      --auto-placement on --quantity 1 \
      --tag-specifications "ResourceType=dedicated-host,Tags=[{Key=Name,Value=$TAG}]" \
      --query "HostIds[0]" --output text 2>/dev/null); then
    echo "  allocated $HOST_ID in $AZ"; break
  fi
  HOST_ID=""
done
[ -n "$HOST_ID" ] || { echo "No Mac capacity in any AZ of $REGION. Try another region."; exit 1; }

say "Resolving default subnet in $AZ"
SUBNET=$(aws ec2 describe-subnets --filters "Name=availability-zone,Values=$AZ" \
  "Name=default-for-az,Values=true" --query "Subnets[0].SubnetId" --output text)
if [ "$SUBNET" = "None" ]; then
  SUBNET=$(aws ec2 describe-subnets --filters "Name=availability-zone,Values=$AZ" \
    --query "Subnets[0].SubnetId" --output text)
fi
[ "$SUBNET" != "None" ] || { echo "No subnet in $AZ"; exit 1; }
VPC=$(aws ec2 describe-subnets --subnet-ids "$SUBNET" --query "Subnets[0].VpcId" --output text)

say "Security group (SSH from this IP only)"
MYIP=$(curl -s https://checkip.amazonaws.com)
SG=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$SG_NAME" \
  "Name=vpc-id,Values=$VPC" --query "SecurityGroups[0].GroupId" --output text 2>/dev/null || echo None)
if [ "$SG" = "None" ]; then
  SG=$(aws ec2 create-security-group --group-name "$SG_NAME" --vpc-id "$VPC" \
    --description "Mac build box" --query GroupId --output text)
fi
aws ec2 authorize-security-group-ingress --group-id "$SG" --protocol tcp --port 22 \
  --cidr "${MYIP}/32" >/dev/null 2>&1 || true
echo "SG: $SG  (allows ${MYIP}/32)"

say "Launching instance"
USERDATA=$(cat <<EOF
#!/bin/bash
dscl . -passwd /Users/ec2-user '$VNC_PASS'
launchctl enable system/com.apple.screensharing
launchctl load -w /System/Library/LaunchDaemons/com.apple.screensharing.plist
diskutil apfs resizeContainer disk0s2 0 || true
EOF
)
IID=$(aws ec2 run-instances --image-id "$AMI" --instance-type "$ITYPE" \
  --key-name "$KEY_NAME" --security-group-ids "$SG" --subnet-id "$SUBNET" \
  --associate-public-ip-address --disable-api-termination \
  --placement "Tenancy=host,HostId=$HOST_ID" \
  --block-device-mappings "[{\"DeviceName\":\"/dev/sda1\",\"Ebs\":{\"VolumeSize\":$VOL_GB,\"VolumeType\":\"gp3\"}}]" \
  --user-data "$USERDATA" \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$TAG}]" \
  --query "Instances[0].InstanceId" --output text)
echo "Instance: $IID"

say "Waiting for boot (Macs take ~5-10 min on first launch)"
aws ec2 wait instance-status-ok --instance-ids "$IID"

IP=$(aws ec2 describe-instances --instance-ids "$IID" \
  --query "Reservations[0].Instances[0].PublicIpAddress" --output text)

cat <<EOF

===================================================================
  READY

  Instance : $IID
  Host     : $HOST_ID   ($AZ)
  Public IP: $IP
  VNC user : ec2-user
  VNC pass : $VNC_PASS

  1) Open the tunnel (leave this running):
       ssh -i $KEY_FILE -L 5900:localhost:5900 ec2-user@$IP

  2) Point any VNC client at:   localhost:5900
     (Windows: RealVNC Viewer, TigerVNC, or TightVNC)

  Install Xcode once connected:
       brew install xcodesorg/made/xcodes && xcodes install --latest

  TEARDOWN - both steps required:
       aws ec2 modify-instance-attribute --instance-id $IID --no-disable-api-termination
       aws ec2 terminate-instances --instance-ids $IID
       aws ec2 release-hosts --host-ids $HOST_ID
===================================================================
EOF
