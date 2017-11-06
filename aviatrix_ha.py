from __future__ import print_function

import boto3
import re
import json
import datetime
import time
import os
import uuid
import json
import urllib2
from urllib2 import HTTPError, build_opener, HTTPHandler, Request

import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

print('Loading function')

def lambda_handler(event, context):
    scheduled_event = False
    sns_event = False
    responseData = {}

    # This lambda function will serve 2 kinds of requests:
    # one time request from CFT - Request to setup HA (setup_ha method) made by Cloud formation template.
    # sns_event - Request from sns to attach elastic ip to new instance created after controller failover.
    try:
        cf_request = event.get("StackId", None)
    except:
        print("Not from CFT")
        pass
    try:
        sns_event = event.get("Records")[0].get("EventSource") == "aws:sns"
    except:
        pass
    client = boto3.client('ec2')
    lambda_client = boto3.client('lambda')
    try:
        INSTANCE_NAME = os.environ.get('AVIATRIX_TAG')
        controller_instanceobj = client.describe_instances(Filters=[{'Name': 'instance-state-name', 'Values': ['running']},
                        {'Name': 'tag:Name','Values': [INSTANCE_NAME]}])['Reservations'][0]['Instances'][0]
    except Exception as e:
        print("Can't find Controller instance with name tag %s. %s" % (INSTANCE_NAME, str(e)))
        if cf_request:
            if event.get("RequestType",None) == 'Create':
                sendResponse(event, context, 'Failed', responseData)
            else:
                # While deleting cloud formation template, this lambda function will be called
                # to delete AssignEIP resource. If controller instance is not present,
                # then cloud formation will be stuck in deletion.
                # So just pass in that case.
                pass
        else:
            return

    if cf_request:
        responseStatus = 'SUCCESS'
        if event['RequestType'] == 'Create':
                try:
                    set_environ(client, lambda_client, controller_instanceobj, context)
                    print("Environment variables have been set.")
                except Exception as e:
                    responseStatus = 'FAILED'
                    print("Failed to setup environment variables %s" %str(e))

                if responseStatus == 'SUCCESS' and verify_credentials() == True:
                    print("Verified AWS and controller Credentials")
                    print("Trying to setup HA")
                    try:
                        setup_ha(client, controller_instanceobj, context)
                    except Exception as e:
                        responseStatus = 'FAILED'
                        print("Failed to setup HA %s" %str(e))
                else:
                    responseStatus = 'FAILED'
                    print("Unable to verify AWS or S3 credentials. Exiting...")
        elif event['RequestType'] == 'Delete':
            try:
                print("Trying to delete lambda created resources")
                delete_resources(controller_instanceobj)
            except Exception as e:
                print("Failed to delete lambda created resources. %s" %str(e))
                print("You'll have to manually delete Auto Scaling group, Launch Configuration, and SNS topic, all with name {}.".format(INSTANCE_NAME))
                pass

        #Send response to CFT.
        sendResponse(event, context, responseStatus, responseData)
        print("Sent {} to CFT.".format(responseStatus))
    elif sns_event:
        restore_backup(client, lambda_client, controller_instanceobj, context)

# Verify S3 and controller account credentials.
def verify_credentials():
    print("Verifying Credentials")
    try:
        s3_client = boto3.client('s3', aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_BACK'),
                            aws_secret_access_key=os.environ.get('AWS_SECRET_KEY_BACK'))
        bucket_loc = s3_client.get_bucket_location(Bucket=os.environ.get('S3_BUCKET_BACK'))
    except Exception as e:
        print("Either S3 credentials or S3 bucket used for backup is not valid. %s" %str(e))
        return False
    print("S3 credentials and S3 bucket both are valid.")
    EIP = os.environ.get('EIP')
    print(EIP)
    BASE_URL = "https://"+EIP+"/v1/api"
    url = BASE_URL+"?action=login&username="+os.environ.get('AVIATRIX_USER_BACK')+"&password="+os.environ.get('AVIATRIX_PASS_BACK')
    try:
        response = requests.get(url, verify=False)
    except Exception as e:
        print("Can't connect to controller with elastic IP %s. %s" % (EIP, str(e)))
        return False
    response_json = response.json()
    print(response_json)
    try:
        cid = response_json['CID']
        print("Created new session with CID %s. Controller backup account and password are valid.\n" %cid)
    except KeyError, e:
        print("Invalid backup account or password. Exception: %s" %str(e))
        return False
    return True

# Set Environment variables. 
def set_environ(client, lambda_client, controller_instanceobj, context):
    EIP = controller_instanceobj['NetworkInterfaces'][0]['Association'].get('PublicIp')
    PRIV_IP = controller_instanceobj.get('NetworkInterfaces')[0].get('PrivateIpAddress')
    lambda_client.update_function_configuration(FunctionName=context.function_name,
                                                Environment={'Variables': {'EIP': EIP,
                                                'AVIATRIX_TAG': os.environ.get('AVIATRIX_TAG'),
                                                'PRIV_IP': PRIV_IP,
                                                'SUBNETLIST': os.environ.get('SUBNETLIST'),
                                                'AWS_ACCESS_KEY_BACK': os.environ.get('AWS_ACCESS_KEY_BACK'),
                                                'AWS_SECRET_KEY_BACK': os.environ.get('AWS_SECRET_KEY_BACK'),
                                                'S3_BUCKET_BACK': os.environ.get('S3_BUCKET_BACK'),
                                                'AVIATRIX_USER_BACK': os.environ.get('AVIATRIX_USER_BACK'),
                                                'AVIATRIX_PASS_BACK': urllib2.quote(os.environ.get('AVIATRIX_PASS_BACK'), '%')
                                                }})

def restore_backup(client, lambda_client, controller_instanceobj, context):
    assign_eip(client, controller_instanceobj)
    EIP = os.environ.get('EIP')
    BASE_URL = "https://"+EIP+"/v1/api"
    url = BASE_URL+"?action=login&username="+os.environ.get('AVIATRIX_USER_BACK')+"&password="+os.environ.get('AVIATRIX_PASS_BACK')

    print(url)
    response = requests.get(url, verify=False)
    response_json = response.json()
    print(response_json)
    try:
        cid = response_json['CID']
        print("Created new session with CID %s\n" %cid)
    except KeyError, e:
        print("Unable to create session. %s" %str(e))
        return

    #This private IP belongs to older terminated instance
    s3_file = "CloudN_"+os.environ.get('PRIV_IP')+"_save_cloudx_config.enc"
    #s3_file = "CloudN_10.0.0.188_save_cloudx_config.enc"

    restore_data = {"CID": cid, "action": "restore_cloudx_config", "cloud_type": "1",
                    "access_key": os.environ.get('AWS_ACCESS_KEY_BACK'),
                    "secret_key": os.environ.get('AWS_SECRET_KEY_BACK'),
                    "bucket_name": os.environ.get('S3_BUCKET_BACK'), "file_name":s3_file}
    response = requests.post(BASE_URL, data=restore_data, verify=False)
    response_json = response.json()
    print(response_json)
    #If restore succeeded, update private IP to that of new instance now.
    if response_json['return'] == True:
        PRIV_IP = controller_instanceobj.get('NetworkInterfaces')[0].get('PrivateIpAddress')
        lambda_client.update_function_configuration(FunctionName=context.function_name,
                                                    Environment={'Variables': {'EIP': os.environ.get('EIP'),
                                                    'AVIATRIX_TAG': os.environ.get('AVIATRIX_TAG'),
                                                    'PRIV_IP': PRIV_IP,
                                                    'SUBNETLIST': os.environ.get('SUBNETLIST'),
                                                    'AWS_ACCESS_KEY_BACK': os.environ.get('AWS_ACCESS_KEY_BACK'),
                                                    'AWS_SECRET_KEY_BACK': os.environ.get('AWS_SECRET_KEY_BACK'),
                                                    'S3_BUCKET_BACK': os.environ.get('S3_BUCKET_BACK'),
                                                    'AVIATRIX_USER_BACK': os.environ.get('AVIATRIX_USER_BACK'),
                                                    'AVIATRIX_PASS_BACK': os.environ.get('AVIATRIX_PASS_BACK'),
                                                    }})

def assign_eip(client, controller_instanceobj):
    EIP = os.environ.get('EIP')
    eip_alloc_id = client.describe_addresses(PublicIps=[EIP]).get('Addresses')[0].get('AllocationId')
    client.associate_address(AllocationId=eip_alloc_id,
                                     InstanceId=controller_instanceobj['InstanceId'])
    print("Assigned elastic IP")

def setup_ha(client, controller_instanceobj, context):
    AMI_NAME = LC_NAME = ASG_NAME = SNS_TOPIC = os.environ.get('AVIATRIX_TAG')
    ami_id = client.describe_images(
        Filters=[{'Name': 'name','Values': [AMI_NAME]}],Owners=['self'])['Images'][0]['ImageId']

    asg_client = boto3.client('autoscaling')

    asg_client.create_launch_configuration(
            InstanceId = controller_instanceobj['InstanceId'],
            LaunchConfigurationName=LC_NAME,
            ImageId= ami_id)

    asg_client.create_auto_scaling_group(AutoScalingGroupName = ASG_NAME,
        LaunchConfigurationName=LC_NAME,
        MinSize=0,
        MaxSize=1,
        VPCZoneIdentifier=os.environ.get('SUBNETLIST'),
        Tags=[{'Key': 'Name','Value': ASG_NAME, 'PropagateAtLaunch': True}]
    )
    print('Created ASG')
    asg_client.attach_instances(InstanceIds=[controller_instanceobj['InstanceId']], AutoScalingGroupName=ASG_NAME)
    sns_client = boto3.client('sns')
    sns_topic_arn = sns_client.create_topic(Name=SNS_TOPIC).get('TopicArn')
    print('Created SNS topic')
    lambda_client = boto3.client('lambda')
    lambda_fn_arn = lambda_client.get_function(FunctionName=context.function_name).get('Configuration').get('FunctionArn')
    sns_client.subscribe(TopicArn=sns_topic_arn,Protocol='lambda',Endpoint=lambda_fn_arn).get('SubscriptionArn')
    response = lambda_client.add_permission(FunctionName=context.function_name, StatementId=str(uuid.uuid4()),
                                    Action='lambda:InvokeFunction',
                                    Principal='sns.amazonaws.com',SourceArn=sns_topic_arn)
    print('SNS topic: Added lambda subscription.')
    response = asg_client.put_notification_configuration(AutoScalingGroupName=ASG_NAME,
                    NotificationTypes=['autoscaling:EC2_INSTANCE_LAUNCH'],
                    TopicARN=sns_topic_arn)
    print('Attached ASG')

def delete_resources(controller_instanceobj):
    LC_NAME = ASG_NAME = SNS_TOPIC = os.environ.get('AVIATRIX_TAG')
 
    asg_client = boto3.client('autoscaling')   
    response = asg_client.detach_instances(InstanceIds=[controller_instanceobj['InstanceId']],
        AutoScalingGroupName=ASG_NAME,
        ShouldDecrementDesiredCapacity=True)
    print("Controller instance detached from autoscaling group")
    asg_client.delete_auto_scaling_group(AutoScalingGroupName=ASG_NAME,ForceDelete=True)
    print("Autoscaling group deleted")
    asg_client.delete_launch_configuration(LaunchConfigurationName=LC_NAME)
    print("Launch configuration deleted")
    sns_client = boto3.client('sns')
    sns_topic_arn = sns_client.create_topic(Name=SNS_TOPIC).get('TopicArn')
    sns_client.delete_topic(TopicArn=sns_topic_arn)
    print("SNS topic deleted")

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
