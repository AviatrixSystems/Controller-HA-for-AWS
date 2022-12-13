import json
import os
import time
import uuid

import boto3
import botocore

from csp.instance import is_controller_termination_protected
from csp.keypair import validate_keypair
from csp.lambda_c import update_env_dict
from csp.subnets import validate_subnets
from csp.target_group import get_target_group_arns
from errors.exceptions import AvxError


def setup_ha(ami_id, inst_type, inst_id, key_name, sg_list, context,
             attach_instance=True, controller_instance_obj=None):
    """ Setup HA """
    print("HA config ami_id %s, inst_type %s, inst_id %s, key_name %s, sg_list %s, "
          "attach_instance %s" % (ami_id, inst_type, inst_id, key_name, sg_list, attach_instance))
    lt_name = lc_name = asg_name = sns_topic = os.environ.get('AVIATRIX_TAG')
    # AMI_NAME = LC_NAME
    # ami_id = client.describe_images(
    #     Filters=[{'Name': 'name','Values':
    #  [AMI_NAME]}],Owners=['self'])['Images'][0]['ImageId']
    asg_client = boto3.client('autoscaling')
    lambda_client = boto3.client('lambda')
    sub_list = os.environ.get('SUBNETLIST')
    val_subnets = validate_subnets(sub_list.split(","))
    print("Valid subnets %s" % val_subnets)
    if key_name:
        validate_keypair(key_name)
    bld_map = []
    try:
        tags = json.loads(os.environ.get('TAGS'))
    except ValueError:
        tags = [{'Key': 'Name', 'Value': asg_name, 'PropagateAtLaunch': True}]
    else:
        if not tags:
            tags = [{'Key': 'Name', 'Value': asg_name, 'PropagateAtLaunch': True}]
        for tag in tags:
            tag['PropagateAtLaunch'] = True

    disks = json.loads(os.environ.get('DISKS'))
    if disks:
        for disk in disks:
            disk_config = {"Ebs": {"VolumeSize": disk["Size"],
                                   "VolumeType": disk['VolumeType'],
                                   "DeleteOnTermination": disk['DeleteOnTermination'],
                                   "Encrypted": disk["Encrypted"],
                                   "Iops": disk.get("Iops", '')},
                           'DeviceName': '/dev/sda1'}
            if not disk_config["Ebs"]["Iops"]:
                del disk_config["Ebs"]["Iops"]
            bld_map.append(disk_config)
    print("Block device configuration", bld_map)
    if not bld_map:
        print("bld map is empty")
        raise AvxError("Could not find any disks attached to the controller")
    ec2_client = boto3.client('ec2')
    iam_arn = os.environ.get('IAM_ARN')
    monitoring = os.environ.get('MONITORING', 'disabled') == 'enabled'

    if inst_id:
        print("Setting launch config from instance")
        asg_client.create_launch_configuration(
            LaunchConfigurationName=lc_name,
            ImageId=ami_id,
            InstanceId=inst_id,
            BlockDeviceMappings=bld_map,
            UserData="# Ignore"
        )
        bld_cp = []
        for disk in bld_map:
            bld_cp.append(disk(disk))
            bld_cp[-1]['VolumeSize'] = bld_cp[-1].pop('Size')

        target_group_arns = get_target_group_arns(inst_id)
        if target_group_arns:
            update_env_dict(lambda_client, context,
                            {'TARGET_GROUP_ARNS': json.dumps(target_group_arns)})
        disable_api_term = is_controller_termination_protected(inst_id)
        if disable_api_term:
            update_env_dict(lambda_client, context,
                            {'DISABLE_API_TERMINATION': "True"})
        try:
            ec2_client.create_launch_template(
                LaunchTemplateName=lt_name,
                LaunchTemplateData={
                    # 'KernelId':  '',
                    'EbsOptimized': controller_instance_obj.get('EbsOptimized', False),
                    'IamInstanceProfile': iam_arn,
                    'BlockDeviceMappings': bld_cp,
                    'ImageId': ami_id,
                    'InstanceType':  controller_instance_obj['InstanceType'],
                    # 'NetworkInterfaces'
                    'KeyName': key_name,
                    'Monitoring': {"Enabled": monitoring},
                    # Placement, (az info) # RamDiskId
                    'DisableApiTermination': disable_api_term,
                    # InstanceInitiatedShutdownBehavior,
                    'UserData': "# Ignore",
                    'TagSpecifications': [{'ResourceType': 'instance',
                                           'Tags': os.environ.get('TAGS', '[]')}],
                    'SecurityGroups': sg_list
                    # ElasticGpuSpecifications # ElasticInferenceAccelerators # SecurityGroupIds
                    # SecurityGroups(specified in asg) # InstanceMarketOptions(spot)
                    # CreditSpecification # CpuOptions # CapacityReservationSpecification
                    # LicenseSpecifications # HibernationOptions # MetadataOptions # EnclaveOptions
                    # InstanceRequirements # PrivateDnsNameOptions # MaintenanceOptions
                    # DisableApiStop
                }
            )
        except Exception as err:
            print(str(err))
    else:
        print("Setting launch config from environment")

        kw_args = {
            "LaunchConfigurationName": lc_name,
            "ImageId": ami_id,
            "InstanceType": inst_type,
            "SecurityGroups": sg_list,
            "KeyName": key_name,
            "AssociatePublicIpAddress": True,
            "InstanceMonitoring": {"Enabled": monitoring},
            "BlockDeviceMappings": bld_map,
            "UserData": "# Ignore",
            "IamInstanceProfile": iam_arn,
        }
        if not key_name:
            del kw_args["KeyName"]
        if not iam_arn:
            del kw_args["IamInstanceProfile"]
        if not bld_map:
            del kw_args["BlockDeviceMappings"]

        asg_client.create_launch_configuration(**kw_args)

        # check if target groups are still valid
        old_target_group_arns = json.loads(os.environ.get('TARGET_GROUP_ARNS', '[]'))
        target_group_arns = []
        elb_client = boto3.client('elbv2')
        for target_group_arn in old_target_group_arns:
            try:
                elb_client.describe_target_health(
                    TargetGroupArn=target_group_arn)
            except elb_client.exceptions.TargetGroupNotFoundException:
                pass
            else:
                target_group_arns.append(target_group_arn)
        if len(old_target_group_arns) != len(target_group_arns):
            update_env_dict(lambda_client, context,
                            {'TARGET_GROUP_ARNS': json.dumps(target_group_arns)})
    print(f"Target group arns list {target_group_arns}")
    tries = 0
    while tries < 3:
        try:
            print("Trying to create ASG")
            asg_client.create_auto_scaling_group(
                AutoScalingGroupName=asg_name,
                LaunchConfigurationName=lc_name,
                MinSize=0,
                MaxSize=1,
                DesiredCapacity=0 if attach_instance else 1,
                TargetGroupARNs=target_group_arns,
                VPCZoneIdentifier=val_subnets,
                Tags=tags
            )
        except botocore.exceptions.ClientError as err:
            if "AlreadyExists" in str(err):
                print("ASG already exists")
                if "pending delete" in str(err):
                    print("Pending delete. Trying again in 10 secs")
                    time.sleep(10)
            else:
                raise
        else:
            break

    print('Created ASG')
    if attach_instance:
        asg_client.attach_instances(InstanceIds=[inst_id],
                                    AutoScalingGroupName=asg_name)
    sns_client = boto3.client('sns')
    sns_topic_arn = sns_client.create_topic(Name=sns_topic).get('TopicArn')
    os.environ['TOPIC_ARN'] = sns_topic_arn
    print('Created SNS topic %s' % sns_topic_arn)
    update_env_dict(lambda_client, context, {'TOPIC_ARN': sns_topic_arn})
    lambda_fn_arn = lambda_client.get_function(
        FunctionName=context.function_name).get('Configuration').get('FunctionArn')
    sns_client.subscribe(TopicArn=sns_topic_arn,
                         Protocol='lambda',
                         Endpoint=lambda_fn_arn).get('SubscriptionArn')
    if os.environ.get('NOTIF_EMAIL'):
        try:
            sns_client.subscribe(TopicArn=sns_topic_arn,
                                 Protocol='email',
                                 Endpoint=os.environ.get('NOTIF_EMAIL'))
        except botocore.exceptions.ClientError as err:
            print("Could not add email notification %s" % str(err))
    else:
        print("Not adding email notification")
    lambda_client.add_permission(FunctionName=context.function_name,
                                 StatementId=str(uuid.uuid4()),
                                 Action='lambda:InvokeFunction',
                                 Principal='sns.amazonaws.com',
                                 SourceArn=sns_topic_arn)
    print('SNS topic: Added lambda subscription.')
    asg_client.put_notification_configuration(
        AutoScalingGroupName=asg_name,
        NotificationTypes=['autoscaling:EC2_INSTANCE_LAUNCH',
                           'autoscaling:EC2_INSTANCE_LAUNCH_ERROR'],
        TopicARN=sns_topic_arn)
    print('Attached ASG')
