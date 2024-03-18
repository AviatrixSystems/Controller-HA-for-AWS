import boto3
import botocore

from aviatrix_ha.errors.exceptions import AvxError


def validate_keypair(key_name):
    """Validates Keypairs"""
    try:
        client = boto3.client("ec2")
        response = client.describe_key_pairs()
    except botocore.exceptions.ClientError as err:
        raise AvxError(str(err)) from err
    key_aws_list = [key["KeyName"] for key in response["KeyPairs"]]
    if key_name not in key_aws_list:
        print("Key does not exist. Creating")
        try:
            client = boto3.client("ec2")
            client.create_key_pair(KeyName=key_name)
        except botocore.exceptions.ClientError as err:
            raise AvxError(str(err)) from err
    else:
        print("Key exists")
