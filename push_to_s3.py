""" Push script for lambda files
use as ACCESS_KEY=xxxx SECRET_KEY=yyyy python push_to_s3.py
"""
from __future__ import print_function
import os
import sys
import traceback
import threading
import boto3
from botocore.exceptions import ClientError

try:
    ACCESS_KEY = os.environ['ACCESS_KEY']
    SECRET_KEY = os.environ['SECRET_KEY']
except KeyError:
    raise Exception("use as ACCESS_KEY=xxxx SECRET_KEY=yyyy python push_to_s3.py."
                    " For dev add --dev")

BUCKET_PREFIX = "aviatrix-lambda-"
LAMBDA_ZIP_FILE = 'aviatrix_ha.zip'
LAMBDA_ZIP_DST_FILE = 'aviatrix_ha_acc_sec.zip'
LAMBDA_ZIP_DEV_FILE = 'aviatrix_ha_dev.zip'

CFT_BUCKET_NAME = "aviatrix-cloudformation-templates"
CFT_BUCKET_REGION = "us-west-2"
CFT_FILE_NAME = "aviatrix-aws-existing-controller-ha.json"
CFT_DEV_FILE_NAME = "aviatrix-aws-existing-controller-ha-dev.json"
CFT_DST_FILE_NAME = "aviatrix-aws-existing-controller-ha-acc-sec.json"

def push_cft_s3():
    """ Push CFT to S3"""
    print(" Pushing CFT")
    s3_ = boto3.client('s3', aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY,
                       region_name=CFT_BUCKET_REGION)
    dst_file = CFT_DST_FILE_NAME
    try:
        if sys.argv[1] == "--dev":
            print("Pushing CFT to dev bucket")
            dst_file = CFT_DEV_FILE_NAME
    except IndexError:
        pass
    try:
        s3_.upload_file(CFT_FILE_NAME, CFT_BUCKET_NAME, dst_file,
                        ExtraArgs={'ACL': 'public-read'})
    except ClientError:
        print(traceback.format_exc())
    print("Pushed CFT")


def push_lambda_file_s3():
    """ Push lambda file to each region"""
    ec2_ = boto3.client('ec2', aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY,
                        region_name='us-west-1')
    regions = [reg['RegionName'] for reg in ec2_.describe_regions()['Regions']]

    for region in regions:
        print (region)
        threading.Thread(target=push_lambda_file_in_region, args=[region]).start()


def push_lambda_file_in_region(region):
    """ Push"""
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

    dst_file = LAMBDA_ZIP_DST_FILE
    try:
        if sys.argv[1] == "--dev":
            print ("Pushing to dev bucket")
            dst_file = LAMBDA_ZIP_DEV_FILE
    except IndexError:
        pass

    try:
        s3_.upload_file(LAMBDA_ZIP_FILE, bucket_name, dst_file, ExtraArgs={'ACL': 'public-read'})
    except ClientError:
        print (traceback.format_exc())
    print ("pushed successfully to " + region)


if __name__ == '__main__':
    push_cft_s3()
    push_lambda_file_s3()
