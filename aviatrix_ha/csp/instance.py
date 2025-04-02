""" CSP APis related to instances"""

import base64
from typing import Any

import boto3
import botocore
from types_boto3_ec2.client import EC2Client
from types_boto3_ec2.type_defs import InstanceTypeDef


def get_controller_instance(
    ec2_client: EC2Client, instance_name: str, inst_id: str
) -> tuple[str | None, InstanceTypeDef]:
    """Find the controller instance based on name or id"""
    controller_instanceobj: InstanceTypeDef = {}
    describe_err = None
    try:
        try:
            controller_instanceobj = ec2_client.describe_instances(
                Filters=[
                    {"Name": "instance-state-name", "Values": ["running"]},
                    {"Name": "tag:Name", "Values": [instance_name]},
                ]
            )["Reservations"][0]["Instances"][0]
        except IndexError:
            if inst_id:
                print(
                    "Can't find Controller instance with name tag %s, "
                    "trying with inst id %s" % (instance_name, inst_id)
                )
                controller_instanceobj = ec2_client.describe_instances(
                    InstanceIds=[inst_id]
                )["Reservations"][0]["Instances"][0]
            else:
                raise
    except Exception as err:
        inst_id_err = " or inst id %s" % inst_id if inst_id else ""
        describe_err = "Can't find Controller instance with name tag %s%s. %s" % (
            instance_name,
            inst_id_err,
            str(err),
        )
        print(describe_err)

    return describe_err, controller_instanceobj


def enable_t2_unlimited(client: EC2Client, inst_id: str) -> None:
    """Modify instance credit to unlimited for T2"""
    print("Enabling T2 unlimited for %s" % inst_id)
    try:
        client.modify_instance_credit_specification(
            ClientToken=inst_id,
            InstanceCreditSpecifications=[
                {"InstanceId": inst_id, "CpuCredits": "unlimited"}
            ],
        )
    except botocore.exceptions.ClientError as err:
        print(str(err))


def is_controller_termination_protected(inst_id: str) -> bool:
    """Check if the controller instance has API termination protection"""
    try:
        enabled = boto3.client("ec2").describe_instance_attribute(
            Attribute="disableApiTermination", InstanceId=inst_id
        )["DisableApiTermination"]["Value"]
        print(
            "Controller termination protection is {}enabled".format(
                "" if enabled else "not "
            )
        )
        return enabled
    except Exception as err:
        print(str(err))
    return False


def verify_iam(controller_instanceobj: InstanceTypeDef) -> bool:
    """Verify IAM roles"""
    print("Verifying IAM roles ")
    iam_arn = controller_instanceobj.get("IamInstanceProfile", {}).get("Arn", "")
    if not iam_arn:
        return False
    return True


def get_user_data(
    ec2_client: EC2Client, controller_instanceobj: InstanceTypeDef
) -> str:
    try:
        user_data = ec2_client.describe_instance_attribute(
            InstanceId=controller_instanceobj["InstanceId"], Attribute="userData"
        )["UserData"]["Value"]
        user_data = base64.b64decode(user_data).decode("utf-8")
        return user_data
    except Exception as err:
        print(str(err))
    return ""
