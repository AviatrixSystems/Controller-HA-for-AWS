import os
import time

import boto3
import botocore

from aviatrix_ha.errors.exceptions import AvxError

VERSION_PREFIX = "UserConnect-"
MAXIMUM_BACKUP_AGE = 24 * 3600 * 3  # 3 days
AWS_US_EAST_REGION = "us-east-1"


def retrieve_controller_version(version_file):
    """Get the controller version from backup file"""
    print("Retrieving version from file " + str(version_file))
    s3c = boto3.client("s3", region_name=os.environ["S3_BUCKET_REGION"])
    try:
        with open("/tmp/version_ctrlha.txt", "wb") as data:
            s3c.download_fileobj(os.environ.get("S3_BUCKET_BACK"), version_file, data)
    except botocore.exceptions.ClientError as err:
        if err.response["Error"]["Code"] == "404":
            print("The object does not exist.")
            raise AvxError("The cloudx version file does not exist") from err
        raise
    if not os.path.exists("/tmp/version_ctrlha.txt"):
        raise AvxError("Unable to open version file")
    with open("/tmp/version_ctrlha.txt") as fileh:
        buf = fileh.read()
    print("Retrieved version " + str(buf))
    if not buf:
        raise AvxError("Version file is empty")
    print("Parsing version")
    if buf.startswith(VERSION_PREFIX):
        buf = buf[len(VERSION_PREFIX) :]
    try:
        ver_list = buf.split(".")
        ctrl_version = ".".join(ver_list[:-1])
        ctrl_version_with_build = ".".join(ver_list)
    except (KeyboardInterrupt, IndexError, ValueError) as err:
        raise AvxError("Could not decode version") from err
    print(
        "Parsed version sucessfully {} and {}".format(
            ctrl_version, ctrl_version_with_build
        )
    )
    return ctrl_version, ctrl_version_with_build


def verify_bucket():
    """Verify S3 and controller account credentials"""
    print("Verifying bucket")
    try:
        s3_client = boto3.client("s3")
        resp = s3_client.get_bucket_location(Bucket=os.environ.get("S3_BUCKET_BACK"))
    except Exception as err:
        print("S3 bucket used for backup is not " "valid. %s" % str(err))
        return False, ""
    try:
        bucket_region = resp["LocationConstraint"]

        # Buckets in Region us-east-1 have a LocationConstraint of null
        if bucket_region is None:
            print(f"Bucket region is None. Setting to {AWS_US_EAST_REGION}")
            bucket_region = AWS_US_EAST_REGION
    except KeyError:
        print(
            "Key LocationConstraint not found in get_bucket_location response %s" % resp
        )
        return False, ""

    print("S3 bucket is valid.")
    return True, bucket_region


def verify_backup_file(controller_instanceobj):
    """Verify if s3 file exists"""
    print("Verifying Backup file")
    try:
        s3c = boto3.client("s3", region_name=os.environ["S3_BUCKET_REGION"])
        priv_ip = controller_instanceobj["NetworkInterfaces"][0]["PrivateIpAddress"]
        version_file = "CloudN_" + priv_ip + "_save_cloudx_version.txt"
        retrieve_controller_version(version_file)
        s3_file = "CloudN_" + priv_ip + "_save_cloudx_config.enc"
        try:
            with open("/tmp/tmp.enc", "wb") as data:
                s3c.download_fileobj(os.environ.get("S3_BUCKET_BACK"), s3_file, data)
        except botocore.exceptions.ClientError as err:
            if err.response["Error"]["Code"] == "404":
                print("The object %s does not exist." % s3_file)
                return False, ""
            print(str(err))
            return False, ""
    except Exception as err:
        print("Verify Backup failed %s" % str(err))
        return False, ""
    else:
        return True, s3_file


def is_backup_file_is_recent(backup_file):
    """Check if backup file is not older than MAXIMUM_BACKUP_AGE"""
    try:
        s3c = boto3.client("s3", region_name=os.environ["S3_BUCKET_REGION"])
        try:
            file_obj = s3c.get_object(
                Key=backup_file, Bucket=os.environ.get("S3_BUCKET_BACK")
            )
        except botocore.exceptions.ClientError as err:
            print(str(err))
            return False
        age = time.time() - file_obj["LastModified"].timestamp()
        if age < MAXIMUM_BACKUP_AGE:
            print("Succesfully validated Backup file age")
            return True
        print(
            f"File age {age} is older than the maximum allowed value of {MAXIMUM_BACKUP_AGE}"
        )
        return False
    except Exception as err:
        print(f"Checking backup file age failed due to {str(err)}")
        return False
