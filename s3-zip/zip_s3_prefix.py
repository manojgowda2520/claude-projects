"""Download s3://webapps.mobil80.com/LANDINGPAGE/DEV/ and zip it locally.

Usage:
    python zip_s3_prefix.py            # creates LANDINGPAGE-DEV.zip next to this script
    python zip_s3_prefix.py --upload   # also uploads the zip to s3://webapps.mobil80.com/LANDINGPAGE/LANDINGPAGE-DEV.zip
"""
import os
import sys
import zipfile

import boto3

BUCKET = "webapps.mobil80.com"
PREFIX = "LANDINGPAGE/DEV/"
HERE = os.path.dirname(os.path.abspath(__file__))
ZIP_PATH = os.path.join(HERE, "LANDINGPAGE-DEV.zip")
UPLOAD_KEY = "LANDINGPAGE/LANDINGPAGE-DEV.zip"


def main():
    s3 = boto3.client("s3")
    paginator = s3.get_paginator("list_objects_v2")

    count = total = 0
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for page in paginator.paginate(Bucket=BUCKET, Prefix=PREFIX):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith("/"):  # folder placeholder objects
                    continue
                arcname = "DEV/" + key[len(PREFIX):]
                body = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
                zf.writestr(arcname, body)
                count += 1
                total += obj["Size"]
                print(f"  + {arcname} ({obj['Size']:,} bytes)")

    if count == 0:
        os.remove(ZIP_PATH)
        sys.exit(f"No objects found under s3://{BUCKET}/{PREFIX}")

    print(f"\n{count} files, {total / 1024 / 1024:.2f} MB raw -> {ZIP_PATH} "
          f"({os.path.getsize(ZIP_PATH) / 1024 / 1024:.2f} MB zipped)")

    if "--upload" in sys.argv:
        s3.upload_file(ZIP_PATH, BUCKET, UPLOAD_KEY)
        print(f"Uploaded to s3://{BUCKET}/{UPLOAD_KEY}")


if __name__ == "__main__":
    main()
