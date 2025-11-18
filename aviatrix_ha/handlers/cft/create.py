import base64
import json
import logging
import os
import time
from typing import Any
import uuid

from aviatrix_ha.handlers.cft.delete import delete_launch_template
import boto3
import botocore
from types_boto3_ec2.literals import InstanceTypeType
from types_boto3_ec2.type_defs import (
    LaunchTemplateBlockDeviceMappingRequestTypeDef,
    RequestLaunchTemplateDataTypeDef,
)
import yaml

from aviatrix_ha.csp.instance import is_controller_termination_protected
from aviatrix_ha.csp.keypair import validate_keypair
from aviatrix_ha.csp.lambda_c import get_lambda_tags, update_env_dict
from aviatrix_ha.csp.subnets import validate_subnets
from aviatrix_ha.csp.target_group import get_target_group_arns
from aviatrix_ha.errors.exceptions import AvxError


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _update_user_data(user_data: str) -> str:
    if not user_data or not user_data.startswith("#cloud-config\n"):
        return user_data

    try:
        data = yaml.safe_load(user_data)
    except yaml.YAMLError as exc:
        logger.exception("Failed to parse user data [%s]: %s", user_data, exc)
        return user_data

    if "avx-controller" in data:
        data["avx-controller"][
            "avx-controller-version-url"
        ] = f"{os.environ.get('SERVICE_URL')}controller_version"

    return f"#cloud-config\n{yaml.dump(data)}"


def _create_or_update_asg(
    asg_client,
    asg_name: str,
    lt_name: str,
    target_group_arns: list[str],
    val_subnets: str,
    unique_tags: dict,
    attach_instance: bool,
    inst_id: str | None,
    is_update: bool = False,
) -> None:
    """Create new ASG or update existing ASG with new launch template"""
    if is_update:
        print(f"Updating existing ASG: {asg_name} with new launch template")
        try:
            asg_client.update_auto_scaling_group(
                AutoScalingGroupName=asg_name,
                LaunchTemplate={"LaunchTemplateName": lt_name, "Version": "$Latest"},
            )
            print(f"ASG {asg_name} updated with new launch template")
            return
        except asg_client.exceptions.AutoScalingGroupNotFoundException:
            print(f"ASG {asg_name} not found, creating new one")

    # Create new ASG
    tries = 0
    while tries < 3:
        try:
            print(f"Trying to create ASG: {asg_name}")
            asg_client.create_auto_scaling_group(
                AutoScalingGroupName=asg_name,
                LaunchTemplate={"LaunchTemplateName": lt_name, "Version": "$Latest"},
                MinSize=0,
                MaxSize=1,
                DesiredCapacity=0 if attach_instance else 1,
                TargetGroupARNs=target_group_arns,
                VPCZoneIdentifier=val_subnets,
                Tags=list(unique_tags.values()),
            )
            print(f"Created ASG: {asg_name}")
            break
        except botocore.exceptions.ClientError as err:
            if "AlreadyExists" in str(err):
                if "pending delete" in str(err):
                    print("ASG pending delete. Trying again in 10 secs")
                    tries += 1
                    time.sleep(10)
                else:
                    print(f"ASG {asg_name} already exists")
                    # Update it instead
                    asg_client.update_auto_scaling_group(
                        AutoScalingGroupName=asg_name,
                        LaunchTemplate={
                            "LaunchTemplateName": lt_name,
                            "Version": "$Latest",
                        },
                    )
                    print(f"Updated existing ASG: {asg_name}")
                    break
            else:
                raise

    # Attach instance if needed
    if attach_instance and inst_id:
        asg_client.attach_instances(
            InstanceIds=[inst_id], AutoScalingGroupName=asg_name
        )
        print(f"Attached instance {inst_id} to ASG")


def _create_launch_template(
    ec2_client,
    lt_name: str,
    ami_id: str,
    inst_type: str,
    key_name: str,
    sg_list: list[str],
    user_data: str,
    bld_map: list,
    iam_arn: str,
    monitoring: bool,
    ebz_optimized: bool,
    disable_api_term: bool,
    unique_tags: dict,
    cf_tags: list,
) -> None:
    cloud_init = _update_user_data(user_data).encode("utf-8")

    lt_data: RequestLaunchTemplateDataTypeDef = {
        "EbsOptimized": ebz_optimized,
        "IamInstanceProfile": {"Arn": iam_arn},
        "BlockDeviceMappings": bld_map,
        "ImageId": ami_id,
        "InstanceType": inst_type,
        "KeyName": key_name,
        "Monitoring": {"Enabled": monitoring},
        "DisableApiTermination": disable_api_term,
        "TagSpecifications": [
            {"ResourceType": "instance", "Tags": list(unique_tags.values())}
        ],
        "SecurityGroupIds": sg_list,
        "UserData": base64.b64encode(cloud_init).decode("utf-8"),
        # # Unused and unsupported parameters
        # Placement, (az info) # RamDiskId # 'NetworkInterfaces' # 'KernelId':  '',
        # 'SecurityGroups': sg_list  # for non-default VPC only SG is supported by AWS
        # ElasticGpuSpecifications # ElasticInferenceAccelerators
        # InstanceInitiatedShutdownBehavior # DisableApiStop
        # 'UserData': "'IyBJZ25vcmU='",# base64.b64encode("# Ignore".encode()).decode()
        # SecurityGroups(specified in asg) # InstanceMarketOptions(spot)
        # CreditSpecification # CpuOptions # CapacityReservationSpecification
        # LicenseSpecifications # HibernationOptions # MetadataOptions # EnclaveOptions
        # InstanceRequirements # PrivateDnsNameOptions # MaintenanceOptions
    }

    if not key_name:
        lt_data.pop("KeyName")

    ec2_client.create_launch_template(
        LaunchTemplateName=lt_name,
        LaunchTemplateData=lt_data,
        TagSpecifications=(
            []
            if not cf_tags
            else [{"ResourceType": "launch-template", "Tags": cf_tags}]
        ),
    )
    print("Created launch template")


def _setup_sns_notifications(
    sns_client,
    lambda_client,
    asg_client,
    sns_topic: str,
    asg_name: str,
    context: Any,
    cf_tags: list,
    skip_if_exists: bool = False,
) -> str:
    """Setup SNS topic, subscriptions, and ASG notifications"""
    if skip_if_exists:
        # For updates, topic already exists
        sns_topic_arn = os.environ.get("TOPIC_ARN")
        if sns_topic_arn and sns_topic_arn != "N/A":
            print(f"Using existing SNS topic: {sns_topic_arn}")
            return sns_topic_arn

    sns_topic_arn = sns_client.create_topic(Name=sns_topic, Tags=cf_tags)["TopicArn"]
    print(f"Created SNS topic: {sns_topic_arn}")

    lambda_fn_arn = lambda_client.get_function(FunctionName=context.function_name)[
        "Configuration"
    ]["FunctionArn"]

    print(f"Subscribing Lambda to SNS topic")
    sns_client.subscribe(
        TopicArn=sns_topic_arn, Protocol="lambda", Endpoint=lambda_fn_arn
    )

    # Subscribe email if configured
    if os.environ.get("NOTIF_EMAIL"):
        try:
            sns_client.subscribe(
                TopicArn=sns_topic_arn,
                Protocol="email",
                Endpoint=os.environ["NOTIF_EMAIL"],
            )
            print(f"Subscribed email to SNS topic")
        except botocore.exceptions.ClientError as err:
            print(f"Could not add email notification: {err}")

    # Add Lambda permission
    try:
        lambda_client.add_permission(
            FunctionName=context.function_name,
            StatementId=str(uuid.uuid4()),
            Action="lambda:InvokeFunction",
            Principal="sns.amazonaws.com",
            SourceArn=sns_topic_arn,
        )
        print("Added Lambda permission for SNS")
    except lambda_client.exceptions.ResourceConflictException:
        print("Lambda permission already exists")

    # Configure ASG notifications
    asg_client.put_notification_configuration(
        AutoScalingGroupName=asg_name,
        NotificationTypes=[
            "autoscaling:EC2_INSTANCE_LAUNCH",
            "autoscaling:EC2_INSTANCE_LAUNCH_ERROR",
        ],
        TopicARN=sns_topic_arn,
    )
    print("Configured ASG notifications")

    return sns_topic_arn


def setup_ha(
    ami_id: str,
    inst_type: InstanceTypeType,
    inst_id: str | None,
    key_name: str,
    sg_list: list[str],
    context: Any,
    user_data: str,
    attach_instance: bool = True,
    is_update: bool = False,
) -> None:
    """Setup HA"""
    print(
        "HA config ami_id %s, inst_type %s, inst_id %s, key_name %s, sg_list %s, "
        "attach_instance %s"
        % (ami_id, inst_type, inst_id, key_name, sg_list, attach_instance)
    )

    lt_name = asg_name = sns_topic = os.environ.get("AVIATRIX_TAG", "")

    # Step 0: Validation and vars preparation
    sub_list = os.environ.get("SUBNETLIST", "")
    val_subnets = validate_subnets(sub_list.split(","))
    print("Valid subnets %s" % val_subnets)
    if key_name:
        validate_keypair(key_name)

    # Prepare tags
    try:
        tags = json.loads(os.environ.get("TAGS", ""))
    except ValueError:
        print("Setting tags based on Name")
        tags = [{"Key": "Name", "Value": asg_name, "PropagateAtLaunch": True}]
    else:
        if not tags:
            tags = [{"Key": "Name", "Value": asg_name, "PropagateAtLaunch": True}]
        for tag in tags:
            tag["PropagateAtLaunch"] = True

    # Prepare disks
    bld_map = []
    disks = json.loads(os.environ.get("DISKS", ""))
    if disks:
        for disk in disks:
            disk_config: LaunchTemplateBlockDeviceMappingRequestTypeDef = {
                "Ebs": {
                    "VolumeSize": disk["Size"],
                    "VolumeType": disk["VolumeType"],
                    "DeleteOnTermination": disk["DeleteOnTermination"],
                    "Encrypted": disk["Encrypted"],
                    "Iops": disk.get("Iops", ""),
                },
                "DeviceName": "/dev/sda1",
            }
            if not disk_config["Ebs"]["Iops"]:
                del disk_config["Ebs"]["Iops"]
            if disk_config["Ebs"]["VolumeType"] not in ["gp3", "io1", "io2"]:
                # IOPs can only be specified for the above types. For the others, it is read-only
                del disk_config["Ebs"]["Iops"]
            bld_map.append(disk_config)

    print("Block device configuration", bld_map)
    if not bld_map:
        print("bld map is empty")
        raise AvxError("Could not find any disks attached to the controller")

    # Instance configuration
    lambda_client = boto3.client("lambda")
    iam_arn = os.environ.get("IAM_ARN", "")
    monitoring = os.environ.get("MONITORING", "disabled") == "enabled"
    ebz_optimized = os.environ.get("EBS_OPT", "False") == "True"
    if inst_id:
        print("Setting launch template from instance")

        target_group_arns = get_target_group_arns(inst_id)
        if target_group_arns:
            update_env_dict(
                lambda_client,
                context,
                {"TARGET_GROUP_ARNS": json.dumps(target_group_arns)},
            )
        disable_api_term = is_controller_termination_protected(inst_id)
        if disable_api_term:
            update_env_dict(lambda_client, context, {"DISABLE_API_TERMINATION": "True"})
    else:
        print("Setting launch template from environment")

        # check if target groups are still valid
        old_target_group_arns = json.loads(os.environ.get("TARGET_GROUP_ARNS", "[]"))
        target_group_arns = []
        elb_client = boto3.client("elbv2")
        for target_group_arn in old_target_group_arns:
            try:
                elb_client.describe_target_health(TargetGroupArn=target_group_arn)
            except elb_client.exceptions.TargetGroupNotFoundException:
                pass
            else:
                target_group_arns.append(target_group_arn)
        if len(old_target_group_arns) != len(target_group_arns):
            update_env_dict(
                lambda_client,
                context,
                {"TARGET_GROUP_ARNS": json.dumps(target_group_arns)},
            )
        disable_api_term = os.environ.get("DISABLE_API_TERMINATION", "False") == "True"

    # Prepare tags for resources
    tag_cp = []
    for tag in tags:
        tag_cp.append(dict(tag))
        tag_cp[-1].pop("PropagateAtLaunch", None)

    # Combine controller and CF tags
    cf_tags = get_lambda_tags(lambda_client, context.invoked_function_arn)
    unique_tags = {}
    for tag in tag_cp + cf_tags:
        key_val = (tag["Key"], tag["Value"])
        unique_tags[key_val] = tag

    # Step 1: Delete old launch template if is_update
    if is_update:
        delete_launch_template(lt_name)

    # Step 2: Create launch template
    ec2_client = boto3.client("ec2")
    _create_launch_template(
        ec2_client,
        lt_name,
        ami_id,
        inst_type,
        key_name,
        sg_list,
        user_data,
        bld_map,
        iam_arn,
        monitoring,
        ebz_optimized,
        disable_api_term,
        unique_tags,
        cf_tags,
    )

    # Step 3: Create or Update ASG
    asg_client = boto3.client("autoscaling")
    _create_or_update_asg(
        asg_client,
        asg_name,
        lt_name,
        target_group_arns,
        val_subnets,
        unique_tags,
        attach_instance,
        inst_id,
        is_update=is_update,
    )

    # Step 4: Setup SNS notifications
    sns_client = boto3.client("sns")
    sns_topic_arn = _setup_sns_notifications(
        sns_client,
        lambda_client,
        asg_client,
        sns_topic,
        asg_name,
        context,
        cf_tags,
        skip_if_exists=is_update,
    )
    os.environ["TOPIC_ARN"] = sns_topic_arn
    if not is_update:
        print("Created SNS topic %s" % sns_topic_arn)
    else:
        print("Using existing SNS topic: %s" % sns_topic_arn)
    update_env_dict(lambda_client, context, {"TOPIC_ARN": sns_topic_arn})

    print("HA Setup completed successfully")
