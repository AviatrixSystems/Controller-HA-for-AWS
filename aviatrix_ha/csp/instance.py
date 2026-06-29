""" CSP APis related to instances"""

import base64

import boto3
import botocore
from types_boto3_ec2.client import EC2Client
from types_boto3_ec2.type_defs import InstanceTypeDef

from aviatrix_ha.errors.exceptions import AvxError


def get_controller_instance(
    ec2_client: EC2Client, instance_name: str, inst_id: str = "", priv_ip: str = ""
) -> tuple[str | None, InstanceTypeDef]:
    """Return the controller instance to manage, or an error if it is unclear.

    inst_id, when set, is an authoritative identifier and is used directly. On
    failover the ASG tells us (via the SNS event) the exact instance it just
    launched; that is passed here so we restore onto the new controller rather
    than guessing from the Name tag. We must NOT fall back to a previously
    recorded instance id, because at failover that points at the old, now
    terminated controller - selecting it makes the restore step think the
    controller is "already saved" and skip restoring.

    Without inst_id we find the controller by its Name tag. The Name tag is not
    unique: an account can have several running instances with the same Name
    tag. The user-supplied private IP (unique within a VPC) is used to choose
    between such matches; it only narrows multiple matches and never discards a
    single match. If the tag cannot be resolved to exactly one instance, a
    descriptive error is returned instead of guessing.
    """
    try:
        reservations = ec2_client.describe_instances(
            Filters=[
                {"Name": "instance-state-name", "Values": ["running"]},
                {"Name": "tag:Name", "Values": [instance_name]},
            ]
        )["Reservations"]

        # A Name tag can match instances across multiple reservations (each launch is
        # its own reservation), so flatten before counting
        instances = [inst for res in reservations for inst in res.get("Instances", [])]

        if len(instances) > 1 and priv_ip:
            instances = [
                inst for inst in instances if inst.get("PrivateIpAddress") == priv_ip
            ] or instances

        if len(instances) == 1:
            return None, instances[0]

        if inst_id:
            print(f"Looking up controller by instance id {inst_id}")
            instance = ec2_client.describe_instances(InstanceIds=[inst_id])[
                "Reservations"
            ][0]["Instances"][0]
            return None, instance

        if not instances:
            raise AvxError(
                f"No running controller instance found with Name tag "
                f"'{instance_name}'."
            )
        ids = ", ".join(i["InstanceId"] for i in instances)
        raise AvxError(
            f"Found {len(instances)} running instances with Name tag "
            f"'{instance_name}': {ids}. HA cannot determine which instance to "
            f"manage. Please ensure the controller Name tag is unique or provide "
            f"the correct controller private IP."
        )
    except Exception as err:
        inst_id_err = " or inst id %s" % inst_id if inst_id else ""
        describe_err = "Can't find Controller instance with name tag %s%s. %s" % (
            instance_name,
            inst_id_err,
            str(err),
        )
        print(describe_err)
        return describe_err, {}


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
