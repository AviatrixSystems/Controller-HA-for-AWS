import os
from typing import Any

import botocore
from types_boto3_ec2.client import EC2Client
from types_boto3_ec2.type_defs import InstanceTypeDef

from aviatrix_ha.errors.exceptions import AvxError

BLOCKED_RULE_TAG = "avx:ha-blocked-rule"


def disable_open_sg_rules(client: EC2Client, instance_id: str) -> list[dict[str, Any]]:
    """Disable open security group if exists.

    We use the modify_security_group_rules API to change the CIDR from
    0.0.0.0/0 to 0.0.0.0/32 for all open security group rules. This is done
    "in-place" to preserve any metadata (description, tags, etc) that might be
    preexisting on the rule.
    """
    modified_rules: list[dict[str, Any]] = []
    try:
        dirsp = client.describe_instances(InstanceIds=[instance_id])
        sgs = dirsp["Reservations"][0]["Instances"][0].get("SecurityGroups", [])
        dsgrrsp = client.describe_security_group_rules(
            Filters=[
                {
                    "Name": "group-id",
                    "Values": [sg["GroupId"] for sg in sgs],
                }
            ]
        )
        for sgr in dsgrrsp.get("SecurityGroupRules", []):
            if sgr["IsEgress"]:
                continue
            if (
                sgr["IpProtocol"] != "tcp"
                or sgr["FromPort"] > 443
                or sgr["ToPort"] < 443
            ):
                continue

            cidr = sgr.get("CidrIpv4")
            if not cidr or cidr != "0.0.0.0/0":
                continue

            client.modify_security_group_rules(
                GroupId=sgr["GroupId"],
                SecurityGroupRules=[
                    {
                        "SecurityGroupRuleId": sgr["SecurityGroupRuleId"],
                        "SecurityGroupRule": {
                            "IpProtocol": sgr["IpProtocol"],
                            "FromPort": sgr["FromPort"],
                            "ToPort": sgr["ToPort"],
                            "CidrIpv4": "0.0.0.0/32",
                        },
                    }
                ],
            )
            client.create_tags(
                Resources=[sgr["SecurityGroupRuleId"]],
                Tags=[
                    {
                        "Key": BLOCKED_RULE_TAG,
                        "Value": "true",
                    }
                ],
            )
    except botocore.exceptions.ClientError as err:
        raise AvxError(str(err)) from err
    return modified_rules


def enable_open_sg_rules(client: EC2Client, instance_id: str) -> list[dict[str, Any]]:
    """Re-enable any previously disabled open SG rules."""
    modified_rules: list[dict[str, Any]] = []
    try:
        dirsp = client.describe_instances(InstanceIds=[instance_id])
        sgs = dirsp["Reservations"][0]["Instances"][0].get("SecurityGroups", [])
        dsgrrsp = client.describe_security_group_rules(
            Filters=[
                {
                    "Name": "tag-key",
                    "Values": [BLOCKED_RULE_TAG],
                },
                {
                    "Name": "group-id",
                    "Values": [sg["GroupId"] for sg in sgs],
                },
            ],
        )
        print(f"Found security groups to be restored: {dsgrrsp['SecurityGroupRules']}")
        for sgr in dsgrrsp["SecurityGroupRules"]:
            client.modify_security_group_rules(
                GroupId=sgr["GroupId"],
                SecurityGroupRules=[
                    {
                        "SecurityGroupRuleId": sgr["SecurityGroupRuleId"],
                        "SecurityGroupRule": {
                            "IpProtocol": sgr["IpProtocol"],
                            "FromPort": sgr["FromPort"],
                            "ToPort": sgr["ToPort"],
                            "CidrIpv4": "0.0.0.0/0",
                        },
                    }
                ],
            )
            client.delete_tags(
                Resources=[sgr["SecurityGroupRuleId"]],
                Tags=[
                    {
                        "Key": BLOCKED_RULE_TAG,
                    }
                ],
            )
    except botocore.exceptions.ClientError as err:
        raise AvxError(str(err)) from err
    return modified_rules


def remove_temp_security_group_access(
    client: EC2Client, sg_id: str, sgr_id: str
) -> None:
    """Remove SG rule with ${lambda_ip}/32 in previously added security group"""
    try:
        client.revoke_security_group_ingress(
            GroupId=sg_id,
            SecurityGroupRuleIds=[sgr_id],
        )
    except botocore.exceptions.ClientError as err:
        if "InvalidPermission.NotFound" not in str(err) and "InvalidGroup" not in str(
            err
        ):
            print(str(err))


def temp_add_security_group_access(
    client: EC2Client,
    controller_instanceobj: InstanceTypeDef,
    lambda_ip: str,
    api_private_access: str | None,
) -> tuple[bool, str, str]:
    """
    Temporarily add ${lambda_ip}/32 rule in one security group
    If the current security group reach rule limitation,
    try with the next security group to add that rule
    """
    sgs = [sg_["GroupId"] for sg_ in controller_instanceobj["SecurityGroups"]]
    if not sgs:
        raise AvxError("No security groups were attached to controller")

    if api_private_access == "True":
        return True, sgs[0], ""

    for sg in sgs:
        try:
            rsp = client.authorize_security_group_ingress(
                GroupId=sg,
                IpPermissions=[
                    {
                        "IpProtocol": "tcp",
                        "FromPort": 443,
                        "ToPort": 443,
                        "IpRanges": [
                            {
                                "CidrIp": f"{lambda_ip}/32",
                                "Description": "Lambda access for Aviatrix HA",
                            }
                        ],
                    }
                ],
            )
            return False, sg, rsp["SecurityGroupRules"][0]["SecurityGroupRuleId"]
        except botocore.exceptions.ClientError as err:
            if "InvalidPermission.Duplicate" in str(err):
                print(f"Rule already exists in security group {sg}")
                return True, sg, ""
            if "RulesPerSecurityGroupLimitExceeded" in str(err):
                # rule limit exceeds, try next SG until we find a slot.
                print(
                    f"The maximum number of rules per security group has been reached for sg {sg}, trying the next sg..."
                )
                continue
            print(str(err))
            raise

    raise AvxError(
        "All SGs are full, please create a new SG to add rule for lambda access during HA event"
    )


def create_new_sg(client: EC2Client) -> str:
    """Creates a new security group"""
    instance_name = os.environ.get("AVIATRIX_TAG", "")
    vpc_id = os.environ.get("VPC_ID", "")
    try:
        resp = client.create_security_group(
            Description="Aviatrix Controller", GroupName=instance_name, VpcId=vpc_id
        )
        sg_id = resp["GroupId"]
    except (botocore.exceptions.ClientError, KeyError) as err:
        if "InvalidGroup.Duplicate" in str(err):
            rsp = client.describe_security_groups(GroupNames=[instance_name])
            sg_id = rsp["SecurityGroups"][0]["GroupId"]
        else:
            raise AvxError(str(err)) from err
    return sg_id
