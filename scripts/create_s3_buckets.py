"""
Create S3 buckets for Lambda deployment

Prerequisites:
    Configure AWS credentials using one of:
    - Environment variables: export AWS_ACCESS_KEY_ID=xxx AWS_SECRET_ACCESS_KEY=yyy
    - AWS credentials file: ~/.aws/credentials
    - AWS profile: export AWS_PROFILE=<profile>
    - IAM role (if running on EC2/Lambda/ECS)

Usage:
    # Create buckets in specific regions
    poetry run python3 scripts/create_s3_buckets.py --regions us-east-1 us-west-2

    # Create buckets in all regions
    poetry run python3 scripts/create_s3_buckets.py
"""
import argparse
import boto3
import botocore
from botocore.exceptions import ClientError, NoCredentialError, WaiterError


# NB: Avoid S3 Bucket Name Squatting - all buckets are pre-created manually.
# When AWS releases new regions:
#   1. Add region to this dict
#   2. Run: poetry run python3 scripts/create_s3_buckets.py --regions <new-region>
#   3. Commit changes to git
LAMBDA_BUCKETS = {
    "us-east-1": "aviatrix-lambda-us-east-1",
    "us-east-2": "aviatrix-lambda-us-east-2",
    "us-west-1": "aviatrix-lambda-us-west-1",
    "us-west-2": "aviatrix-lambda-us-west-2",
    "af-south-1": "aviatrix-lambda-af-south-1",
    "ap-east-1": "aviatrix-lambda-ap-east-1",
    "ap-northeast-1": "aviatrix-lambda-ap-northeast-1",
    "ap-northeast-2": "aviatrix-lambda-ap-northeast-2",
    "ap-northeast-3": "aviatrix-lambda-ap-northeast-3",
    "ap-south-1": "aviatrix-lambda-ap-south-1",
    "ap-south-2": "aviatrix-lambda-ap-south-2",
    "ap-southeast-1": "aviatrix-lambda-ap-southeast-1",
    "ap-southeast-2": "aviatrix-lambda-ap-southeast-2",
    "ap-southeast-3": "aviatrix-lambda-ap-southeast-3",
    "ap-southeast-4": "aviatrix-lambda-ap-southeast-4",
    "ap-southeast-5": "aviatrix-lambda-ap-southeast-5",
    "ap-southeast-6": "aviatrix-lambda-ap-southeast-6",
    "ap-southeast-7": "aviatrix-lambda-ap-southeast-7",
    "ca-central-1": "aviatrix-lambda-ca-central-1",
    "ca-west-1": "aviatrix-lambda-ca-west-1",
    "eu-central-1": "aviatrix-lambda-eu-central-1",
    "eu-central-2": "aviatrix-lambda-eu-central-2",
    "eu-north-1": "aviatrix-lambda-eu-north-1",
    "eu-south-1": "aviatrix-lambda-eu-south-1",
    "eu-south-2": "aviatrix-lambda-eu-south-2",
    "eu-west-1": "aviatrix-lambda-eu-west-1",
    "eu-west-2": "aviatrix-lambda-eu-west-2",
    "eu-west-3": "aviatrix-lambda-eu-west-3",
    "il-central-1": "aviatrix-lambda-il-central-1",
    "me-central-1": "aviatrix-lambda-me-central-1",
    "me-south-1": "aviatrix-lambda-me-south-1",
    "mx-central-1": "aviatrix-lambda-mx-central-1",
    "sa-east-1": "aviatrix-lambda-sa-east-1",
    # If AWS releases new regions, please update here.
}


def create_bucket(
    s3_client: botocore.client.BaseClient, bucket_name: str, region: str
) -> bool:
    """Create s3 bucket if not exists in the region"""
    try:
        if region == "us-east-1":
            s3_client.create_bucket(Bucket=bucket_name)
        else:
            s3_client.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={"LocationConstraint": region},
            )
        print(f"Bucket {bucket_name} created")
        # Wait for bucket to be ready
        waiter = s3_client.get_waiter("bucket_exists")
        waiter.wait(Bucket=bucket_name, WaiterConfig={"Delay": 2, "MaxAttempts": 10})
        print(f"Bucket {bucket_name} is ready")
        return True
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code in ["BucketAlreadyExists", "BucketAlreadyOwnedByYou"]:
            return True
        return False
    except WaiterError as e:
        print(f"Bucket {bucket_name} is not ready after waiting: {e}")
        return False


def configure_bucket_with_public_access(
    s3_client: botocore.client.BaseClient, bucket_name: str
):
    """Set bucket/object policy"""
    try:
        s3_client.put_public_access_block(
            Bucket=bucket_name,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": False,  # Allow public ACLs on specific object
                "IgnorePublicAcls": False,
                "BlockPublicPolicy": True,  # Don't make whole bucket public
                "RestrictPublicBuckets": True,
            },
        )
        print(f"Configured Block Public Access for {bucket_name}")
    except ClientError as e:
        print(f"Failed to configure Block Public Access: {e}")

    # Make sure new bucket allows ACLs
    try:
        s3_client.put_bucket_ownership_controls(
            Bucket=bucket_name,
            OwnershipControls={"Rules": [{"ObjectOwnership": "BucketOwnerPreferred"}]},
        )
        print(f"Enabled ACLs for {bucket_name}")
    except ClientError as e:
        print(f"Failed to enable ACLs: {e}")


def main():
    """Pre-create all S3 buckets for the Lambda deployment"""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--regions", nargs="+", help="Specific regions to create buckets in"
    )
    args = parser.parse_args()

    regions_to_create_bucket = list(LAMBDA_BUCKETS.keys())
    if args.regions:
        regions_to_create_bucket = args.regions

    # Create Lambda buckets
    for region in regions_to_create_bucket:
        if region not in LAMBDA_BUCKETS:
            print(f"Warning: Region {region} not in LAMBDA_BUCKETS, skipping")
            continue

        bucket_name = LAMBDA_BUCKETS[region]
        s3_client = boto3.client("s3", region_name=region)

        if create_bucket(s3_client, bucket_name, region):
            configure_bucket_with_public_access(s3_client, bucket_name)


if __name__ == "__main__":
    main()
