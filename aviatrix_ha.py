from __future__ import print_function
import time
import boto3
import botocore
import os
import uuid
import json
import urllib2
import traceback
from urllib2 import HTTPError, build_opener, HTTPHandler, Request

import requests
from urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

MAX_LOGIN_TIMEOUT = 300
WAIT_DELAY = 30

INITIAL_SETUP_WAIT = 180


class AvxError(Exception):
    """ Error class for Aviatrix exceptions"""
    pass


print('Loading function')


def lambda_handler(event, context):
    """ Entry point of the lambda script"""
    try:
        _lambda_handler(event, context)
    except AvxError as err:
        print('Operation failed due to: ' + str(err))
    except Exception as err:
        print(str(traceback.format_exc()))
        print("Lambda function failed due to " + str(err))


def _lambda_handler(event, context):
    """ Entry point of the lambda script without exception hadling
        This lambda function will serve 2 kinds of requests:
        one time request from CFT - Request to setup HA (setup_ha method)
         made by Cloud formation template.
        sns_event - Request from sns to attach elastic ip to new instance
         created after controller failover. """
    scheduled_event = False
    sns_event = False
    responseData = {}
    try:
        cf_request = event.get("StackId", None)
    except:
        print("Not from CFT")
        pass
    try:
        sns_event = event.get("Records")[0].get("EventSource") == "aws:sns"
    except:
        pass
    if os.environ.get("TESTPY") == "True":
        print ("Testing")
        client = boto3.client(
            'ec2', region_name=os.environ["AWS_TEST_REGION"],
            aws_access_key_id=os.environ["AWS_ACCESS_KEY_BACK"],
            aws_secret_access_key=os.environ["AWS_SECRET_KEY_BACK"])
        lambda_client = boto3.client(
            'lambda', region_name=os.environ["AWS_TEST_REGION"],
            aws_access_key_id=os.environ["AWS_ACCESS_KEY_BACK"],
            aws_secret_access_key=os.environ["AWS_SECRET_KEY_BACK"])
    else:
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
                    set_environ(lambda_client, controller_instanceobj, context)
                    print("Environment variables have been set.")
                except Exception as e:
                    responseStatus = 'FAILED'
                    print("Failed to setup environment variables %s" %str(e))

                if responseStatus == 'SUCCESS' and verify_credentials(controller_instanceobj) == True:
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

        # Send response to CFT.
        sendResponse(event, context, responseStatus, responseData)
        print("Sent {} to CFT.".format(responseStatus))
    elif sns_event:
        restore_backup(client, lambda_client, controller_instanceobj, context)


def set_environ(lambda_client, controller_instanceobj, context):
    """ Sets Environment variables """

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
                                                'AVIATRIX_PASS_BACK': os.environ.get('AVIATRIX_PASS_BACK')
                                                }})


def login_to_controller(ip, username, pwd):
    """ Logs into the controller and returns the cid"""
    base_url = "https://" + ip + "/v1/api"
    url = base_url + "?action=login&username=" + username + "&password=" +\
          urllib2.quote(pwd, '%')
    try:
        response = requests.get(url, verify=False)
    except Exception as err:
        print("Can't connect to controller with elastic IP %s. %s" % (ip, str(err)))
        raise AvxError(str(err))
    response_json = response.json()
    print(response_json)
    try:
        cid = response_json['CID']
        print("Created new session with CID {}\n".format(cid))
    except KeyError as err:
        print("Unable to create session. {}".format(err))
        raise AvxError("Unable to create session. {}".format(err))
    else:
        return cid


def verify_credentials(controller_instanceobj):
    """ Verify S3 and controller account credentials """
    print("Verifying Credentials")
    try:
        s3_client = boto3.client(
            's3', aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_BACK'),
            aws_secret_access_key=os.environ.get('AWS_SECRET_KEY_BACK'))
        bucket_loc = s3_client.get_bucket_location(
            Bucket=os.environ.get('S3_BUCKET_BACK'))
    except Exception as err:
        print("Either S3 credentials or S3 bucket used for backup is not "
              "valid. %s" % str(err))
        return False
    print("S3 credentials and S3 bucket both are valid.")
    eip = controller_instanceobj[
        'NetworkInterfaces'][0]['Association'].get('PublicIp')
    print(eip)

    login_to_controller(eip, os.environ.get('AVIATRIX_USER_BACK'),
                        os.environ.get('AVIATRIX_PASS_BACK'))
    return True


def retrieve_controller_version(version_file):
    """ Get the controller version from backup file"""
    print("Retrieving version from file " + str(version_file))
    s3c = boto3.client(
        's3',
        aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_BACK'),
        aws_secret_access_key=os.environ.get('AWS_SECRET_KEY_BACK'))
    try:
        with open('/tmp/version_ctrlha.txt', 'w') as data:
            s3c.download_fileobj(os.environ.get('S3_BUCKET_BACK'), version_file,
                                 data)
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] == "404":
            print("The object does not exist.")
            raise AvxError("The cloudx version file does not exist")
        else:
            raise
    if not os.path.exists('/tmp/version_ctrlha.txt'):
        raise AvxError("Unable to open version file")
    with open("/tmp/version_ctrlha.txt") as fileh:
        buf = fileh.read()
    print ("Retrieved version " + str(buf))
    if not buf:
        raise AvxError("Version file is empty")
    print("Parsing version")
    try:
        version = ".".join(((buf[12:]).split("."))[:-1])
    except (KeyboardInterrupt, IndexError, ValueError):
        raise AvxError("Could not decode version")
    else:
        print("Parsed version sucessfully " + str(version))
        return version


def run_initial_setup(ip, cid, version):
    """ Boots the fresh controller to the specific version"""
    base_url = "https://" + ip + "/v1/api"
    # print(json.dumps(controller_instanceobj, indent=2))
    post_data = {"CID": cid,
                 "target_version": version,
                 "action": "initial_setup",
                 "subaction": "run"}

    print("Trying to run initial setup %s\n" % str(post_data))

    response = requests.post(base_url, data=post_data, verify=False)
    response_json = response.json()
    print(response_json)

    if response_json.get('return') is True:
        print ("Successfully initialized the controller")
    else:
        raise AvxError("Could not bring up the new controller to the "
                       "specific version")


def restore_backup(client, lambda_client, controller_instanceobj, context):
    """ Restores the backup by doing the following
    1. Login to new controller
    2. Assign the EIP to the new controller
    2. Run initial setup to boot ot specific version parsed from backup
    3. Login again and restore the configuration """

    assign_eip(client, controller_instanceobj)
    eip = os.environ.get('EIP')

    new_private_ip = controller_instanceobj.get(
        'NetworkInterfaces')[0].get('PrivateIpAddress')
    print("New Private IP " + str(new_private_ip))

    total_time = 0
    while total_time <= MAX_LOGIN_TIMEOUT:
        try:
            cid = login_to_controller(eip, "admin", new_private_ip)
        except Exception as err:
            print(str(err))
            print("Login failed, Trying again in " + str(WAIT_DELAY))
            total_time += WAIT_DELAY
            time.sleep(WAIT_DELAY)
        else:
            break
    if total_time == MAX_LOGIN_TIMEOUT:
        raise AvxError("Could not login to the controller")

    priv_ip = os.environ.get('PRIV_IP')     # This private IP belongs to older
                                            # terminated instance

    version_file = "CloudN_" + priv_ip + "_save_cloudx_version.txt"
    version = retrieve_controller_version(version_file)

    run_initial_setup(eip, cid, version)

    # Need to login again as initial setup invalidates cid after waiting

    cid = login_to_controller(eip, "admin", new_private_ip)

    s3_file = "CloudN_" + priv_ip + "_save_cloudx_config.enc"

    restore_data = {"CID": cid,
                    "action": "restore_cloudx_config",
                    "cloud_type": "1",
                    "access_key": os.environ.get('AWS_ACCESS_KEY_BACK'),
                    "secret_key": os.environ.get('AWS_SECRET_KEY_BACK'),
                    "bucket_name": os.environ.get('S3_BUCKET_BACK'),
                    "file_name": s3_file}
    print("Trying to restore config with data %s\n" % str(restore_data))
    base_url = "https://" + eip + "/v1/api"

    total_time = 0
    sleep = True
    while total_time <= INITIAL_SETUP_WAIT:
        if sleep:
            print("Waiting for safe initial setup completion, maximum of " +
                  str(INITIAL_SETUP_WAIT - total_time) + " seconds remaining")
            time.sleep(WAIT_DELAY)
        else:
            sleep = True
        response = requests.post(base_url, data=restore_data, verify=False)
        response_json = response.json()
        print(response_json)
        if response_json.get('return', False) is True:
            # If restore succeeded, update private IP to that of the new
            #  instance now.
            print("Successfully restored backup. Updating lambda configuration")
            set_environ(lambda_client, controller_instanceobj, context)
            print("Updated lambda configuration")
            return
        elif response_json.get('reason', '') == 'valid action required':
            print("API is not ready yet")
            total_time += WAIT_DELAY
        elif response_json.get('reason', '') == 'CID is invalid or expired.':
            print("Service abrupty restarted")
            sleep = False
            try:
                cid = login_to_controller(eip, "admin", new_private_ip)
            except AvxError:
                pass
            else:
                restore_data["CID"] = cid
        else:
            print("Restoring backup failed due to " +
                  str(response_json.get('reason', '')))
            return
    print("Restore failed, did not update lambda config")


def assign_eip(client, controller_instanceobj):
    """ Assign the EIP to the new instance"""
    eip = os.environ.get('EIP')
    eip_alloc_id = client.describe_addresses(
        PublicIps=[eip]).get('Addresses')[0].get('AllocationId')
    client.associate_address(AllocationId=eip_alloc_id,
                             InstanceId=controller_instanceobj['InstanceId'])
    print("Assigned elastic IP")


def setup_ha(_client, controller_instanceobj, context):
    """ Setup HA """
    LC_NAME = ASG_NAME = SNS_TOPIC = os.environ.get('AVIATRIX_TAG')
    # AMI_NAME = LC_NAME
    # ami_id = client.describe_images(
    #     Filters=[{'Name': 'name','Values':
    #  [AMI_NAME]}],Owners=['self'])['Images'][0]['ImageId']
    ami_id = controller_instanceobj['ImageId']
    asg_client = boto3.client('autoscaling')

    asg_client.create_launch_configuration(
            InstanceId=controller_instanceobj['InstanceId'],
            LaunchConfigurationName=LC_NAME,
            ImageId=ami_id)

    asg_client.create_auto_scaling_group(
        AutoScalingGroupName=ASG_NAME,
        LaunchConfigurationName=LC_NAME,
        MinSize=0,
        MaxSize=1,
        VPCZoneIdentifier=os.environ.get('SUBNETLIST'),
        Tags=[{'Key': 'Name', 'Value': ASG_NAME, 'PropagateAtLaunch': True}]
    )
    print('Created ASG')
    asg_client.attach_instances(InstanceIds=[controller_instanceobj[
                                                 'InstanceId']],
                                AutoScalingGroupName=ASG_NAME)
    sns_client = boto3.client('sns')
    sns_topic_arn = sns_client.create_topic(Name=SNS_TOPIC).get('TopicArn')
    print('Created SNS topic')
    lambda_client = boto3.client('lambda')
    lambda_fn_arn = lambda_client.get_function(
        FunctionName=context.function_name).get('Configuration').get(
        'FunctionArn')
    sns_client.subscribe(TopicArn=sns_topic_arn,
                         Protocol='lambda',
                         Endpoint=lambda_fn_arn).get('SubscriptionArn')
    lambda_client.add_permission(FunctionName=context.function_name,
                                 StatementId=str(uuid.uuid4()),
                                 Action='lambda:InvokeFunction',
                                 Principal='sns.amazonaws.com',
                                 SourceArn=sns_topic_arn)
    print('SNS topic: Added lambda subscription.')
    asg_client.put_notification_configuration(
        AutoScalingGroupName=ASG_NAME,
        NotificationTypes=['autoscaling:EC2_INSTANCE_LAUNCH'],
        TopicARN=sns_topic_arn)
    print('Attached ASG')


def delete_resources(controller_instanceobj):
    """ Cloud formation cleanup"""
    LC_NAME = ASG_NAME = SNS_TOPIC = os.environ.get('AVIATRIX_TAG')
 
    asg_client = boto3.client('autoscaling')
    try:
        asg_client.detach_instances(
            InstanceIds=[controller_instanceobj['InstanceId']],
            AutoScalingGroupName=ASG_NAME,
            ShouldDecrementDesiredCapacity=True)
        print("Controller instance detached from autoscaling group")
    except Exception as e:
        print(e)
        pass
    asg_client.delete_auto_scaling_group(AutoScalingGroupName=ASG_NAME,
                                         ForceDelete=True)
    print("Autoscaling group deleted")
    asg_client.delete_launch_configuration(LaunchConfigurationName=LC_NAME)
    print("Launch configuration deleted")
    sns_client = boto3.client('sns')
    sns_topic_arn = sns_client.create_topic(Name=SNS_TOPIC).get('TopicArn')
    sns_client.delete_topic(TopicArn=sns_topic_arn)
    print("SNS topic deleted")


def sendResponse(event, context, response_status, reason=None,
                 response_data=None, physical_resource_id=None):
    """ Send response to cloud formation template for custom resource creation
     by cloud formation"""

    response_data = response_data or {}
    response_body = json.dumps(
        {
            'Status': response_status,
            'Reason': reason or "See the details in CloudWatch Log Stream: "
                      + context.log_stream_name,
            'PhysicalResourceId': physical_resource_id or
                                  context.log_stream_name,
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