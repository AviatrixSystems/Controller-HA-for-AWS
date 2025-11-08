""" Push script for lambda files

Prerequisites:
    Configure AWS credentials using one of:
    - Environment variables: export AWS_ACCESS_KEY_ID=xxx AWS_SECRET_ACCESS_KEY=yyy
    - AWS credentials file: ~/.aws/credentials
    - AWS profile: export AWS_PROFILE=<profile>
    - IAM role (if running on EC2/Lambda/ECS)

Usage:
    make push       # push production build
    make push_dev   # push dev build
"""
import argparse
import os
import traceback
import threading
import zipfile

import requests
import boto3
from botocore.exceptions import ClientError

from aviatrix_ha.common.constants import DEV_FLAG


BUCKET_PREFIX = "aviatrix-lambda-"
LAMBDA_ZIP_FILE = "bin/aviatrix_ha_v3.zip"
LAMBDA_ZIP_DEV_FILE_STR = "aviatrix_ha_v3_dev.zip"

CFT_BUCKET_NAME = "aviatrix-cloudformation-templates"
CFT_BUCKET_REGION = "us-west-2"
CFT_FILE_NAME = "cft/aviatrix-aws-existing-controller-ha-v3.json"


def _validate_inputs(args: argparse.Namespace):
    if args.dev:
        print("Pushing CFT to dev bucket")
        with open(args.cft_file, "r", encoding="utf-8") as fileh:
            if LAMBDA_ZIP_DEV_FILE_STR not in fileh.read():
                raise Exception(f"{LAMBDA_ZIP_DEV_FILE_STR} not found in lambda in CFT")
        with zipfile.ZipFile(
            args.lambda_zip_file, "r", zipfile.ZIP_DEFLATED
        ) as zip_file:
            if DEV_FLAG not in zip_file.namelist():
                raise Exception(
                    f"Please add the dev flag file {DEV_FLAG} in {args.lambda_zip_file}"
                )
    else:
        with open(args.cft_file, "r", encoding="utf-8") as fileh:
            if LAMBDA_ZIP_DEV_FILE_STR in fileh.read():
                raise Exception(
                    f"{LAMBDA_ZIP_DEV_FILE_STR} found in lambda in CFT. Not pushing"
                )
        with zipfile.ZipFile(
            args.lambda_zip_file, "r", zipfile.ZIP_DEFLATED
        ) as zip_file:
            if DEV_FLAG in zip_file.namelist():
                raise Exception(
                    f"Please remove the dev flag file {DEV_FLAG} in {args.lambda_zip_file}"
                )


def push_cft_s3(args: argparse.Namespace):
    """Push CFT to S3"""
    print(" Pushing CFT")
    _validate_inputs(args)
    s3_ = boto3.client(
        "s3",
        region_name=CFT_BUCKET_REGION,
    )
    dst_file = os.path.basename(args.cft_file)
    try:
        s3_.upload_file(
            args.cft_file, CFT_BUCKET_NAME, dst_file, ExtraArgs={"ACL": "public-read"}
        )
    except ClientError:
        print(traceback.format_exc())

    # Validate file push
    url = f"https://{CFT_BUCKET_NAME}.s3.amazonaws.com/{dst_file}"
    try:
        requests.get(url, timeout=60)
    except requests.RequestException:
        print("Validation failed for CFT")
    print("Pushed CFT")


def push_lambda_file_s3(args: argparse.Namespace):
    """Push lambda file to each region"""
    ec2_ = boto3.client(
        "ec2",
        region_name="us-west-1",
    )
    regions = [reg["RegionName"] for reg in ec2_.describe_regions()["Regions"]]

    threads = [
        threading.Thread(target=push_lambda_file_in_region, args=[args, region])
        for region in regions
    ]
    for thread in threads:
        thread.start()

    # Wait for all threads to finish
    for thread in threads:
        thread.join()


def push_lambda_file_in_region(args: argparse.Namespace, region: str):
    """Push"""
    bucket_name = BUCKET_PREFIX + region
    s3_ = boto3.client(
        "s3",
        region_name=region,
    )

    print(f"Pushing lambda in {region}")

    dst_file = os.path.basename(args.lambda_zip_file)

    try:
        s3_.upload_file(
            args.lambda_zip_file,
            bucket_name,
            dst_file,
            ExtraArgs={"ACL": "public-read"},
        )
    except ClientError:
        print(traceback.format_exc())

    # Validate file push
    url = f"https://{bucket_name}.s3.amazonaws.com/{dst_file}"
    try:
        requests.get(url, timeout=60)
    except requests.RequestException:
        print(f"Lambda zip validation failed for {region}")
        return
    print(f"pushed successfully to {region}")


def main():
    """Copy CFT and Lambda files to S3"""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--lambda_zip_file", default=LAMBDA_ZIP_FILE, help="Lambda zip file path"
    )
    parser.add_argument(
        "--cft_file", default=CFT_FILE_NAME, help="CFT template file path"
    )
    parser.add_argument("--dev", action="store_true")
    args = parser.parse_args()

    push_cft_s3(args)
    push_lambda_file_s3(args)


if __name__ == "__main__":
    main()
