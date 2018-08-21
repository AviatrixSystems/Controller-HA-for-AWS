""" Push script for lambda files
use as ACCESS_KEY=xxxx SECRET_KEY=yyyy python push_to_s3.py
"""
from __future__ import print_function
from botocore.exceptions import ClientError
import boto3
import os
import traceback

try:
    ACCESS_KEY = os.environ['ACCESS_KEY']
    SECRET_KEY = os.environ['SECRET_KEY']
except KeyError:
    print("use as ACCESS_KEY=xxxx SECRET_KEY=yyyy python push_to_s3.py")

BUCKET_PREFIX = "aviatrix-lambda-"
LAMBDA_ZIP_FILE = 'aviatrix_ha.zip'

CFT_BUCKET_NAME = "aviatrix-cloudformation-templates"
CFT_BUCKET_REGION = "us-west-2"
CFT_FILE_NAME = "aviatrix-aws-existing-controller-ha.json"


def push_cft_s3():
    """ push CFT to S3"""
    print(" Pushing CFT")
    s3_ = boto3.client('s3', aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY,
                       region_name=CFT_BUCKET_REGION)
    try:
        s3_.upload_file(CFT_FILE_NAME, CFT_BUCKET_NAME, CFT_FILE_NAME,
                        ExtraArgs={'ACL': 'public-read'})
    except ClientError:
        print(traceback.format_exc())
    print("Pushed CFT")


def push_lambda_file_s3():
    """ push lambda file to each region"""
    ec2_ = boto3.client('ec2', aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY,
                        region_name='us-west-1')
    regions = [reg['RegionName'] for reg in ec2_.describe_regions()['Regions']]

    for region in regions:
        print (region)
        bucket_name = BUCKET_PREFIX + region
        s3_ = boto3.client('s3', aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY,
                           region_name=region)

        # # Buckets are already created now
        # try:
        #     if region == 'us-east-1':
        #         s3_.create_bucket(Bucket=bucket_name)
        #     else:
        #         s3_.create_bucket(Bucket=bucket_name,
        #                           CreateBucketConfiguration={'LocationConstraint': region})
        # except ClientError as err:
        #     if "BucketAlreadyOwnedByYou" in str(err):
        #         pass
        #     else:
        #         print traceback.format_exc()

        try:
            s3_.upload_file(LAMBDA_ZIP_FILE, bucket_name, LAMBDA_ZIP_FILE,
                            ExtraArgs={'ACL': 'public-read'})
        except ClientError:
            print (traceback.format_exc())
        print ("pushed successfully to " + region)


if __name__ == '__main__':
    push_cft_s3()
    push_lambda_file_s3()