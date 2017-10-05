from __future__ import print_function

import boto3
import re
import json
import datetime
import time
import os
import uuid

import json
from urllib2 import HTTPError, build_opener, HTTPHandler, Request

print('Loading function')

INSTANCE_TAG = 'AviatrixController'
AMI_NAME = 'AviatrixController'
LC_NAME = 'AviatrixController'
SNS_TOPIC = 'AviatrixController'

def lambda_handler(event, context):
    scheduled_event = False
    sns_event = False
    
    # This lambda function will serve 3 kinds of requests:
    # cf_request - Request from cloud formation to attach/delete elastic ip.
    # scheduled_event - Request to update AMI(delete old, create new) every 12 hours.
    # sns_event - Request from sns to attach elastic ip to new instance created after controller failover.
    try:
        cf_request = event.get("StackId", None)
    except:
        pass
    try:
        scheduled_event = event.get("detail-type") == "Scheduled Event"
    except:
        pass
    try:
        sns_event = event.get("Records")[0].get("EventSource") == "aws:sns"
    except:
        pass

    client = boto3.client('ec2')
    try:
        controller_instanceobj = client.describe_instances(Filters=[{'Name': 'instance-state-name', 'Values': ['running']},
                        {'Name': 'tag:Name','Values': [INSTANCE_TAG]}])['Reservations'][0]['Instances'][0]
    except:
        # While deleting cloud formation template, this lambda function will be called
        # to delete AssignEIP resource. If controller instance is not present then cloud formation will be stuck in deletion.
        # So just pass in that case.
        if cf_request and event.get("RequestType",None) == 'Delete':
            pass
        else:
            return
    if cf_request:
        responseStatus = 'SUCCESS'
        responseData = {}
        if event['RequestType'] == 'Create':
            lambda_client = boto3.client('lambda')

            # Add autoscaling group name to lambda environment, will be used later.
            lambda_client.update_function_configuration(FunctionName=context.function_name,
                                                    Environment={'Variables': {'EIP': os.environ.get('EIP'),
                                                    'ASG_NAME': event['ResourceProperties'].get("ASG_NAME")
                                                    }})
            assign_eip(client, controller_instanceobj)
        #Return SUCCESS in both Create and Delete cases.
        sendResponse(event, context, "SUCCESS", responseData)
    elif scheduled_event:
        update_ami(client, controller_instanceobj, context)
    elif sns_event:
        assign_eip(client, controller_instanceobj)

def assign_eip(client, controller_instanceobj):
    EIP = os.environ.get('EIP')
    eip_alloc_id = client.describe_addresses(PublicIps=[EIP]).get('Addresses')[0].get('AllocationId')
    client.associate_address(AllocationId=eip_alloc_id,
                                     InstanceId=controller_instanceobj['InstanceId'])
    print("Assigned elastic IP")

# For incremental snapshotting, delete older(current) image, but keep the snapshot.
# Now create a new image from instance, which will use already present snapshot for incremental snaphotting.
# This will be faster. Once new image is created, we can delete older snapshot.
def update_ami(client, controller_instanceobj, context):
    old_ami = delete_old_image(client)
    new_ami = register_new_image(client, controller_instanceobj, context)
    if new_ami:
        # Delete older snapshot only when new ami has been created. Otherwise keep it just in case.
        delete_old_snapshot(client, old_ami)
        update_autoscaling_conf(new_ami, controller_instanceobj, context)

def delete_old_image(client):
    try:
        old_ami = client.describe_images(
            Filters=[{'Name': 'name','Values': [AMI_NAME]}],Owners=['self'])['Images'][0]['ImageId']
    except:
        print("No older backup AMI found")
        return
    client.deregister_image(ImageId=old_ami)
    print("Deleted old image.")
    return old_ami

def delete_old_snapshot(client, old_ami):
    if old_ami is None:
        return
    snap_id = get_snapshot_from_ami(client, old_ami)
    if snap_id:
        client.delete_snapshot(SnapshotId=snap_id)
        print("Deleted old snapshot.")

def get_snapshot_from_ami(client, ami_id):
    for snapshot in client.describe_snapshots(OwnerIds=['self'])['Snapshots']:
        if re.match(r".*for ({0}) from.*".format(ami_id), snapshot['Description']):
            return snapshot['SnapshotId']

def register_new_image(client, controller_instanceobj, context):
    if controller_instanceobj['NetworkInterfaces'][0]['Association']['IpOwnerId'] != 'amazon':
        EIP = controller_instanceobj['NetworkInterfaces'][0]['Association']['PublicIp']
        lambda_client = boto3.client('lambda')
        lambda_client.update_function_configuration(FunctionName=context.function_name,
                                                    Environment={'Variables': {'EIP': EIP, 
                                                    'ASG_NAME': os.environ.get('ASG_NAME'),
                                                    'SUBNETLIST': os.environ.get('SUBNETLIST',"")
                                                    }})
    ssm_client = boto3.client('ssm')

    # Send SSM message to controller instance, which will freeze controller and create new ami from controller instance.
    ssm_cmd = ssm_client.send_command(InstanceIds=[controller_instanceobj['InstanceId']],
                            DocumentName='AWS-RunShellScript',
                            Comment='Demo run Aviatrix HA3',
                            TimeoutSeconds=30,
                            Parameters={"commands":["mongolock=`mongo --eval \"db.fsyncLock()\"`","sync","for target in $(findmnt -nlo TARGET -t ext4); do fsfreeze -f $target; done","instance=`curl -s http://169.254.169.254/latest/meta-data/instance-id`","region=`curl -s 169.254.169.254/latest/meta-data/placement/availability-zone`","region=${region%?}","aws ec2 create-image --instance-id $instance --description \"Aviatrix controller backup AMI created from active ec2 instance\" --name \"AviatrixController\" --region $region --no-reboot","for target in $(findmnt -nlo TARGET -t ext4); do fsfreeze -u $target; done","mongounlock=`mongo --eval \"printjson(db.fsyncUnlock())\"`"]})

    ssm_cmdid = ssm_cmd.get('Command').get('CommandId')
    print(ssm_cmdid)
    time.sleep(10)
    ssm_response = ssm_client.list_command_invocations(
        CommandId=ssm_cmdid,
        InstanceId=controller_instanceobj['InstanceId'],
        Details=True)

    try:
        response = ssm_response.get('CommandInvocations')[0].get('CommandPlugins')[0].get('Output')
        ami_id = 'ami-'+re.search('ami-(.*)"', response).group(1)
    except:
        return None
    else:
        print("Registered new image.")
        return ami_id

def update_autoscaling_conf(new_ami, controller_instanceobj, context):
    ASG_NAME = os.environ.get('ASG_NAME')
    asg_client = boto3.client('autoscaling')
    timeStamp = time.time()
    timeStampString = datetime.datetime.fromtimestamp(timeStamp).strftime('%Y-%m-%d  %H-%M-%S')
    newLaunchConfigName = LC_NAME+timeStampString
    asg_client.create_launch_configuration(
            InstanceId = controller_instanceobj['InstanceId'],
            LaunchConfigurationName=newLaunchConfigName,
            ImageId= new_ami)
    asg = asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=[ASG_NAME]).get('AutoScalingGroups')
    if not asg:
        create_autoscaling_conf(asg_client, controller_instanceobj, newLaunchConfigName, context)
        return

    old_lc = asg[0]['LaunchConfigurationName']
    print(old_lc)
    response = asg_client.update_auto_scaling_group(AutoScalingGroupName = ASG_NAME,
            LaunchConfigurationName = newLaunchConfigName)
    #Delete old launch configuration
    asg_client.delete_launch_configuration(LaunchConfigurationName=old_lc)
    print('Updated Autoscaling Launch configuration')

def create_autoscaling_conf(asg_client, controller_instanceobj, newLaunchConfigName, context):
    ASG_NAME = os.environ.get('ASG_NAME')
    asg_client.create_auto_scaling_group(AutoScalingGroupName = ASG_NAME,
        LaunchConfigurationName=newLaunchConfigName,
        MinSize=0,
        MaxSize=1,
        VPCZoneIdentifier=os.environ.get('SUBNETLIST'),
        Tags=[{'Key': 'Name','Value': ASG_NAME, 'PropagateAtLaunch': True}]
    )
    print('Created ASG')
    asg_client.attach_instances(InstanceIds=[controller_instanceobj['InstanceId']], AutoScalingGroupName=ASG_NAME)
    sns_client = boto3.client('sns')
    sns_topic_arn = sns_client.create_topic(Name=SNS_TOPIC).get('TopicArn')
    lambda_client = boto3.client('lambda')
    lambda_fn_arn = lambda_client.get_function(FunctionName=context.function_name).get('Configuration').get('FunctionArn')
    sns_client.subscribe(TopicArn=sns_topic_arn,Protocol='lambda',Endpoint=lambda_fn_arn).get('SubscriptionArn')
    response = lambda_client.add_permission(FunctionName=context.function_name, StatementId=str(uuid.uuid4()),
                                    Action='lambda:InvokeFunction',
                                    Principal='sns.amazonaws.com',SourceArn=sns_topic_arn)
    response = asg_client.put_notification_configuration(AutoScalingGroupName=ASG_NAME,
                    NotificationTypes=['autoscaling:EC2_INSTANCE_LAUNCH'],
                    TopicARN=sns_topic_arn)
    print('Attached ASG')

# Send response to cloud formation template for custom resource creation by cloud formation
def sendResponse(event, context, response_status, reason=None, response_data=None, physical_resource_id=None):
    response_data = response_data or {}
    response_body = json.dumps(
        {
            'Status': response_status,
            'Reason': reason or "See the details in CloudWatch Log Stream: " + context.log_stream_name,
            'PhysicalResourceId': physical_resource_id or context.log_stream_name,
            'StackId': event['StackId'],
            'RequestId': event['RequestId'],
            'LogicalResourceId': event['LogicalResourceId'],
            'Data': response_data
        }
    )
    opener = build_opener(HTTPHandler)
    request = Request(event['ResponseURL'], data=response_body)
    request.add_header('Content-Type', '')
    request.add_header('Content-Length', len(response_body))
    request.get_method = lambda: 'PUT'
    try:
        response = opener.open(request)
        print("Status code: {}".format(response.getcode()))
        print("Status message: {}".format(response.msg))
        return True
    except HTTPError as exc:
        print("Failed executing HTTP request: {}".format(exc.code))
        return False
