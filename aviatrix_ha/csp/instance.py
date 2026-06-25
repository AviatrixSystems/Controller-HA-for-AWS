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

    The Name tag is not unique: an account can have several running instances
    with the same Name tag (in different VPCs, subnets, or security groups).
    Selecting the first match can pick the wrong controller, and HA then reads
    that controller's backup by its private IP, restoring the wrong backup.

    The private IP (provided by the user at stack creation) is unique within a
    VPC, so it is used to choose between instances that share the Name tag. It
    is only used to choose between multiple matches; it never discards a single
    match. During failover the replacement instance has a new private IP that
    will not equal the provided one, but it is then the only instance with the
    Name tag and is selected.

    Steps:
      1. List running instances with the given Name tag.
      2. If more than one is found, keep only the one whose private IP matches
         priv_ip (if priv_ip is set and matches one of them).
      3. If exactly one instance remains, return it.
      4. Otherwise, if inst_id is set, return that instance. This also finds a
         controller that step 1 misses, for example one that is stopped or
         whose Name tag was changed.
      5. If no single instance can be determined, return a descriptive error.
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
            print(
                f"Name tag '{instance_name}' resolved to {len(instances)} running "
                f"instances; using recorded instance id {inst_id}"
            )
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
