import json
import os
from typing import Any

import botocore
from types_boto3_ec2.client import EC2Client
from types_boto3_ec2.type_defs import InstanceTypeDef, TagTypeDef
from types_boto3_lambda.client import LambdaClient

from aviatrix_ha.errors.exceptions import AvxError


def wait_function_update_successful(
    lambda_client: LambdaClient, function_name: str, raise_err: bool = False
) -> None:
    """Wait until get_function_configuration LastUpdateStatus=Successful"""
    # https://aws.amazon.com/blogs/compute/coming-soon-expansion-of-aws-lambda-states-to-all-functions/
    try:
        waiter = lambda_client.get_waiter("function_updated")
        print(f"Waiting for function update to be successful: {function_name}")
        waiter.wait(FunctionName=function_name)
        print(f"{function_name} update state is successful")
    except botocore.exceptions.WaiterError as err:
        print(str(err))
        if raise_err:
            raise AvxError(str(err)) from err


def get_lambda_tags(lambda_client: LambdaClient, arn: str) -> list[TagTypeDef]:
    """Get tags for the lambda function"""
    try:
        response = lambda_client.list_tags(Resource=arn)
        tags = response.get("Tags", {})
        print(f"Tags: {tags}")
    except botocore.exceptions.ClientError as err:
        raise AvxError(str(err)) from err
    return [
        {"Key": key, "Value": value}
        for key, value in tags.items()
        if not key.startswith("aws:")
    ]


def set_environ(
    client: EC2Client,
    lambda_client: LambdaClient,
    controller_instanceobj: InstanceTypeDef,
    context: Any,
    eip: str = "",
) -> None:
    """Sets Environment variables"""
    use_eip = os.environ.get("USE_EIP", "True")
    # First default USE_EIP to True if unset, will be corrected while validating EIP
    if not eip or use_eip == "False":
        # From cloud formation. EIP is not known at this point. So get from controller inst
        eni = controller_instanceobj["NetworkInterfaces"][0]
        try:
            eip = eni["Association"]["PublicIp"]
        except KeyError:  # No public IP is available. Only supported in private mode
            if os.environ.get("API_PRIVATE_ACCESS", "False") == "True":
                use_eip = "False"
                eip = ""
                print("Skipping EIP for Private Mode")
            else:
                print("Could not get public IP while setting env")
                raise AvxError(
                    "A public IP/EIP was not found. An Elastic IP Address is required"
                    "for controller HA to function correctly in public mode"
                )
    else:
        eip = os.environ.get("EIP", "")
    sns_topic_arn = os.environ.get("TOPIC_ARN", "")
    inst_id = controller_instanceobj["InstanceId"]
    ami_id = controller_instanceobj["ImageId"]
    vpc_id = controller_instanceobj["VpcId"]
    inst_type = controller_instanceobj["InstanceType"]
    keyname = controller_instanceobj.get("KeyName", "")
    ctrl_subnet = controller_instanceobj["SubnetId"]
    if controller_instanceobj["NetworkInterfaces"]:
        priv_ip = controller_instanceobj["NetworkInterfaces"][0]["PrivateIpAddress"]
    else:
        priv_ip = ""
    iam_arn = controller_instanceobj.get("IamInstanceProfile", {}).get("Arn", "")
    user_data = str(controller_instanceobj.get("UserData", ""))
    mon_bool = (
        controller_instanceobj.get("Monitoring", {}).get("State", "disabled")
        != "disabled"
    )
    monitoring = "enabled" if mon_bool else "disabled"
    tags = controller_instanceobj.get("Tags", [])
    ebs_opt = str(bool(controller_instanceobj.get("EbsOptimized", False)))
    tags_stripped = []
    for tag in tags:
        key = tag.get("Key", "")
        # Tags starting with aws: is reserved
        if not key.startswith("aws:"):
            tags_stripped.append(tag)

    disks = []
    for volume in controller_instanceobj.get("BlockDeviceMappings", []):
        ebs = volume.get("Ebs", {})
        if ebs.get("Status", "detached") in ["attached", "in-use"]:
            vol_id = ebs["VolumeId"]
            vol = client.describe_volumes(VolumeIds=[vol_id])["Volumes"][0]
            disks.append(
                {
                    "VolumeId": vol_id,
                    "DeleteOnTermination": ebs.get("DeleteOnTermination"),
                    "VolumeType": vol["VolumeType"],
                    "Size": vol["Size"],
                    "Iops": vol.get("Iops", ""),
                    "Encrypted": vol["Encrypted"],
                }
            )

    env_dict: dict[str, str] = {
        "EIP": eip,
        "USE_EIP": use_eip,
        "AMI_ID": ami_id,
        "VPC_ID": vpc_id,
        "INST_TYPE": inst_type,
        "KEY_NAME": keyname,
        "CTRL_SUBNET": ctrl_subnet,
        "AVIATRIX_TAG": os.environ.get("AVIATRIX_TAG", ""),
        "API_PRIVATE_ACCESS": os.environ.get("API_PRIVATE_ACCESS", "False"),
        "PRIV_IP": priv_ip,
        # priv_ip is used to lookup the backup. As the controller is migrated
        # the priv_ip will change, but we need to know the original priv_ip to
        # find the backup.
        #
        # This function is called once during initial CFT setup, when
        # os.environ.get("PRIV_IP") is None, and then every time the ASG
        # creates a new controller, when os.environ.get("PRIV_IP") will
        # contain the previous private IP.
        "OLD_PRIV_IP": os.environ.get("PRIV_IP") or priv_ip,
        "INST_ID": inst_id,
        "SUBNETLIST": os.environ.get("SUBNETLIST", ""),
        "S3_BUCKET_BACK": os.environ.get("S3_BUCKET_BACK", ""),
        "S3_BUCKET_REGION": os.environ.get("S3_BUCKET_REGION", ""),
        "TOPIC_ARN": sns_topic_arn,
        "NOTIF_EMAIL": os.environ.get("NOTIF_EMAIL", ""),
        "IAM_ARN": iam_arn,
        "MONITORING": monitoring,
        "DISKS": json.dumps(disks),
        "TAGS": json.dumps(tags_stripped),
        "TMP_SG_GRP": os.environ.get("TMP_SG_GRP", ""),
        "TMP_SG_RULE": os.environ.get("TMP_SG_RULE", ""),
        "AWS_ROLE_APP_NAME": os.environ.get("AWS_ROLE_APP_NAME", ""),
        "AWS_ROLE_EC2_NAME": os.environ.get("AWS_ROLE_EC2_NAME", ""),
        "TARGET_GROUP_ARNS": os.environ.get("TARGET_GROUP_ARNS", "[]"),
        "DISABLE_API_TERMINATION": os.environ.get("DISABLE_API_TERMINATION", "False"),
        "SERVICE_URL": os.environ.get("SERVICE_URL", ""),
        "EBS_OPT": ebs_opt,
        "USER_DATA": user_data,
        # 'AVIATRIX_USER_BACK': os.environ.get('AVIATRIX_USER_BACK'),
        # 'AVIATRIX_PASS_BACK': os.environ.get('AVIATRIX_PASS_BACK'),
    }
    print("Setting environment %s" % env_dict)

    wait_function_update_successful(lambda_client, context.function_name)
    lambda_client.update_function_configuration(
        FunctionName=context.function_name, Environment={"Variables": env_dict}
    )
    os.environ.update(env_dict)


def update_env_dict(
    lambda_client: LambdaClient, context: Any, replace_dict: dict[str, str]
) -> None:
    """Update particular variables in the Environment variables in lambda"""
    env_dict: dict[str, str] = {
        "EIP": os.environ.get("EIP", ""),
        "USE_EIP": os.environ.get("USE_EIP", ""),
        "AMI_ID": os.environ.get("AMI_ID", ""),
        "VPC_ID": os.environ.get("VPC_ID", ""),
        "INST_TYPE": os.environ.get("INST_TYPE", ""),
        "KEY_NAME": os.environ.get("KEY_NAME", ""),
        "CTRL_SUBNET": os.environ.get("CTRL_SUBNET", ""),
        "AVIATRIX_TAG": os.environ.get("AVIATRIX_TAG", ""),
        "API_PRIVATE_ACCESS": os.environ.get("API_PRIVATE_ACCESS", "False"),
        "PRIV_IP": os.environ.get("PRIV_IP", ""),
        "OLD_PRIV_IP": os.environ.get("OLD_PRIV_IP", ""),
        "INST_ID": os.environ.get("INST_ID", ""),
        "SUBNETLIST": os.environ.get("SUBNETLIST", ""),
        "S3_BUCKET_BACK": os.environ.get("S3_BUCKET_BACK", ""),
        "S3_BUCKET_REGION": os.environ.get("S3_BUCKET_REGION", ""),
        "TOPIC_ARN": os.environ.get("TOPIC_ARN", ""),
        "NOTIF_EMAIL": os.environ.get("NOTIF_EMAIL", ""),
        "IAM_ARN": os.environ.get("IAM_ARN", ""),
        "MONITORING": os.environ.get("MONITORING", ""),
        "DISKS": os.environ.get("DISKS", ""),
        "TAGS": os.environ.get("TAGS", "[]"),
        "TMP_SG_GRP": os.environ.get("TMP_SG_GRP", ""),
        "TMP_SG_RULE": os.environ.get("TMP_SG_RULE", ""),
        "AWS_ROLE_APP_NAME": os.environ.get("AWS_ROLE_APP_NAME", ""),
        "AWS_ROLE_EC2_NAME": os.environ.get("AWS_ROLE_EC2_NAME", ""),
        "TARGET_GROUP_ARNS": os.environ.get("TARGET_GROUP_ARNS", "[]"),
        "DISABLE_API_TERMINATION": os.environ.get("DISABLE_API_TERMINATION", "False"),
        "SERVICE_URL": os.environ.get("SERVICE_URL", ""),
        "EBS_OPT": os.environ.get("EBS_OPT", "False"),
        "USER_DATA": os.environ.get("USER_DATA", ""),
        # 'AVIATRIX_USER_BACK': os.environ.get('AVIATRIX_USER_BACK'),
        # 'AVIATRIX_PASS_BACK': os.environ.get('AVIATRIX_PASS_BACK'),
    }
    env_dict.update(replace_dict)
    os.environ.update(replace_dict)

    wait_function_update_successful(lambda_client, context.function_name)
    lambda_client.update_function_configuration(
        FunctionName=context.function_name, Environment={"Variables": env_dict}
    )
    print("Updated environment dictionary")
