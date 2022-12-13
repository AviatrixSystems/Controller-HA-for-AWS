import os

import boto3
import botocore

from errors.exceptions import AvxError
VERSION_PREFIX = "UserConnect-"


def retrieve_controller_version(version_file):
    """ Get the controller version from backup file"""
    print("Retrieving version from file " + str(version_file))
    s3c = boto3.client('s3', region_name=os.environ['S3_BUCKET_REGION'])
    try:
        with open('/tmp/version_ctrlha.txt', 'wb') as data:
            s3c.download_fileobj(os.environ.get('S3_BUCKET_BACK'), version_file,
                                 data)
    except botocore.exceptions.ClientError as err:
        if err.response['Error']['Code'] == "404":
            print("The object does not exist.")
            raise AvxError("The cloudx version file does not exist") from err
        raise
    if not os.path.exists('/tmp/version_ctrlha.txt'):
        raise AvxError("Unable to open version file")
    with open("/tmp/version_ctrlha.txt") as fileh:
        buf = fileh.read()
    print("Retrieved version " + str(buf))
    if not buf:
        raise AvxError("Version file is empty")
    print("Parsing version")
    if buf.startswith(VERSION_PREFIX):
        buf = buf[len(VERSION_PREFIX):]
    try:
        ver_list = buf.split(".")
        ctrl_version = ".".join(ver_list[:-1])
        ctrl_version_with_build = ".".join(ver_list)
    except (KeyboardInterrupt, IndexError, ValueError) as err:
        raise AvxError("Could not decode version") from err
    print("Parsed version sucessfully {} and {}".format(
        ctrl_version, ctrl_version_with_build))
    return ctrl_version, ctrl_version_with_build


