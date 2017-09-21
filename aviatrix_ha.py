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
    controller_instanceobj = client.describe_instances(Filters=[{'Name': 'instance-state-name', 'Values': ['running']},
                        {'Name': 'tag:Name','Values': [INSTANCE_TAG]}])['Reservations'][0]['Instances'][0]

    if cf_request:
        responseStatus = 'SUCCESS'
        responseData = {}
        if event['RequestType'] == 'Create':
            lambda_client = boto3.client('lambda')
            lambda_client.update_function_configuration(FunctionName=context.function_name,
                                                    Environment={'Variables': {'EIP': os.environ['EIP'], 
                                                    'ASG_NAME': event['ResourceProperties'].get("ASG_NAME")
                                                    }})
            assign_eip(client, controller_instanceobj)
        sendResponse(event, context, "SUCCESS", responseData)
    elif scheduled_event:        
        duplicate_ami(client, controller_instanceobj, context)
    elif sns_event:
        assign_eip(client, controller_instanceobj)

def assign_eip(client, controller_instanceobj):
    EIP = os.environ['EIP']
    eip_alloc_id = client.describe_addresses(PublicIps=[EIP]).get('Addresses')[0].get('AllocationId')
    client.associate_address(AllocationId=eip_alloc_id,
                                     InstanceId=controller_instanceobj['InstanceId'])
    print("Assigned elastic IP")

def duplicate_ami(client, controller_instanceobj, context):
    delete_image_n_snapshot(client)
    new_ami = register_new_image(client, controller_instanceobj, context)
    update_autoscaling_conf(new_ami, controller_instanceobj, context)

def delete_image_n_snapshot(client):
    try:
        old_image = client.describe_images(
            Filters=[{'Name': 'name','Values': [AMI_NAME]}],Owners=['self'])['Images'][0]['ImageId']
    except:
        print("No older backup AMI found")
        return
    client.deregister_image(ImageId=old_image)
    for snapshot in client.describe_snapshots(OwnerIds=['self'])['Snapshots']:
        if re.match(r".*for ({0}) from.*".format(old_image), snapshot['Description']):
            client.delete_snapshot(SnapshotId=snapshot['SnapshotId'])
    print("Deleted older image and snapshot.")


def register_new_image(client, controller_instanceobj, context):
    # Register new AMI from Aviatrix controller instance.
    if controller_instanceobj['NetworkInterfaces'][0]['Association']['IpOwnerId'] != 'amazon':
        EIP = controller_instanceobj['NetworkInterfaces'][0]['Association']['PublicIp']
        lambda_client = boto3.client('lambda')
        lambda_client.update_function_configuration(FunctionName=context.function_name,
                                                    Environment={'Variables': {'EIP': EIP, 
                                                    'ASG_NAME': os.environ['ASG_NAME']
                                                    }})
    image = client.create_image(
        InstanceId=controller_instanceobj['InstanceId'],
        Description='Aviatrix controller backup AMI created from active ec2 instance',
        Name=AMI_NAME,
        NoReboot=True
    )
    print("Registered new image.")
    return image['ImageId']

def update_autoscaling_conf(new_ami, controller_instanceobj, context):
    ASG_NAME = os.environ['ASG_NAME']
    asg_client = boto3.client('autoscaling')
    timeStamp = time.time()
    timeStampString = datetime.datetime.fromtimestamp(timeStamp).strftime('%Y-%m-%d  %H-%M-%S')
    newLaunchConfigName = LC_NAME+timeStampString
    asg_client.create_launch_configuration(
            InstanceId = controller_instanceobj['InstanceId'],
            LaunchConfigurationName=newLaunchConfigName,
            ImageId= new_ami)
    asg = asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=[ASG_NAME]).get('AutoScalingGroups')
    old_lc = asg[0]['LaunchConfigurationName']
    print(old_lc)
    response = asg_client.update_auto_scaling_group(AutoScalingGroupName = ASG_NAME,
            LaunchConfigurationName = newLaunchConfigName)
    #Delete old launch configuration
    asg_client.delete_launch_configuration(LaunchConfigurationName=old_lc)
    print('Updated Autoscaling Launch configuration')

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

