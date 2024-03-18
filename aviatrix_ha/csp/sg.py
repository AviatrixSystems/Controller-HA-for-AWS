import os

import botocore

from aviatrix_ha.errors.exceptions import AvxError


def restore_security_group_access(client, sg_id):
    """Remove 0.0.0.0/0 rule in previously added security group"""
    try:
        client.revoke_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 443,
                    "ToPort": 443,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                }
            ],
        )
    except botocore.exceptions.ClientError as err:
        if "InvalidPermission.NotFound" not in str(err) and "InvalidGroup" not in str(
            err
        ):
            print(str(err))


def temp_add_security_group_access(client, controller_instanceobj, api_private_access):
    """Temporarily add 0.0.0.0/0 rule in one security group"""
    sgs = [sg_["GroupId"] for sg_ in controller_instanceobj["SecurityGroups"]]
    if api_private_access == "True":
        return True, sgs[0]

    if not sgs:
        raise AvxError("No security groups were attached to controller")
    try:
        client.authorize_security_group_ingress(
            GroupId=sgs[0],
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 443,
                    "ToPort": 443,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                }
            ],
        )
    except botocore.exceptions.ClientError as err:
        if "InvalidPermission.Duplicate" in str(err):
            return True, sgs[0]
        print(str(err))
        raise
    return False, sgs[0]


def create_new_sg(client):
    """Creates a new security group"""
    instance_name = os.environ.get("AVIATRIX_TAG")
    vpc_id = os.environ.get("VPC_ID")
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
    try:
        client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 443,
                    "ToPort": 443,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                },
                {
                    "IpProtocol": "tcp",
                    "FromPort": 80,
                    "ToPort": 80,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                },
            ],
        )
    except botocore.exceptions.ClientError as err:
        if "InvalidGroup.Duplicate" in str(err) or "InvalidPermission.Duplicate" in str(
            err
        ):
            pass
        else:
            raise AvxError(str(err)) from err
    return sg_id
