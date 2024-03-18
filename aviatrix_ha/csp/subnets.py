import os

import boto3
import botocore

from aviatrix_ha.errors.exceptions import AvxError


def validate_subnets(subnet_list):
    """Validates subnets"""
    vpc_id = os.environ.get("VPC_ID")
    if not vpc_id:
        print("New creation. Assuming subnets are valid as selected from CFT")
        return ",".join(subnet_list)
    try:
        client = boto3.client("ec2")
        response = client.describe_subnets(
            Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
        )
    except botocore.exceptions.ClientError as err:
        raise AvxError(str(err)) from err
    sub_aws_list = [sub["SubnetId"] for sub in response["Subnets"]]
    sub_list_new = [sub for sub in subnet_list if sub.strip() in sub_aws_list]
    if not sub_list_new:
        ctrl_subnet = os.environ.get("CTRL_SUBNET")
        if ctrl_subnet not in sub_aws_list:
            raise AvxError(
                "All subnets %s or controller subnet %s are not found in vpc %s"
            )
        print("All subnets are invalid. Using existing controller subnet")
        return ctrl_subnet
    return ",".join(sub_list_new)
