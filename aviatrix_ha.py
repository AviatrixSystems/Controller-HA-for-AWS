""" Aviatrix Controller HA Lambda script """
# pylint: disable=too-many-lines,too-many-locals,too-many-branches,too-many-return-statements
# pylint: disable=too-many-statements,too-many-arguments,broad-except
import time
import os
import uuid
import json
import threading
from urllib.error import HTTPError
from urllib.request import build_opener, HTTPHandler, Request
import traceback
import urllib3
from urllib3.exceptions import InsecureRequestWarning
import boto3
import botocore
import version
from api.account import create_cloud_account
from api.external.ami import check_ami_id
from api.cust import set_customer_id
from api.initial_setup import get_initial_setup_status, run_initial_setup
from api.login import login_to_controller
from api.restore import restore_backup
from api.upgrade_to_build import is_upgrade_to_build_supported
from common.constants import HANDLE_HA_TIMEOUT, WAIT_DELAY, INITIAL_SETUP_DELAY
from csp.eip import assign_eip
from csp.keypair import validate_keypair
from csp.lambda_c import set_environ, update_env_dict
from csp.s3 import retrieve_controller_version, verify_bucket, MAXIMUM_BACKUP_AGE, \
    verify_backup_file, is_backup_file_is_recent
from csp.sg import restore_security_group_access, temp_add_security_group_access, create_new_sg
from csp.target_group import get_target_group_arns
from errors.exceptions import AvxError
from csp.instance import get_controller_instance, enable_t2_unlimited, \
    is_controller_termination_protected

urllib3.disable_warnings(InsecureRequestWarning)

print('Loading function')


def lambda_handler(event, context):
    """ Entry point of the lambda script"""
    try:
        _lambda_handler(event, context)
    except AvxError as err:
        print('Operation failed due to: ' + str(err))
    except Exception as err:  # pylint: disable=broad-except
        print(str(traceback.format_exc()))
        print("Lambda function failed due to " + str(err))


def _lambda_handler(event, context):
    """ Entry point of the lambda script without exception hadling
        This lambda function will serve 2 kinds of requests:
        one time request from CFT - Request to setup HA (setup_ha method)
         made by Cloud formation template.
        sns_event - Request from sns to attach elastic ip to new instance
         created after controller failover. """
    # scheduled_event = False
    sns_event = False
    print("Version: %s Event: %s" % (version.VERSION, event))
    try:
        cf_request = event["StackId"]
        print("From CFT")
    except (KeyError, AttributeError, TypeError):
        cf_request = None
        print("Not from CFT")
    try:
        sns_event = event["Records"][0]["EventSource"] == "aws:sns"
        print("From SNS Event")
    except (AttributeError, IndexError, KeyError, TypeError):
        pass
    if os.environ.get("TESTPY") == "True":
        print("Testing")
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

    tmp_sg = os.environ.get('TMP_SG_GRP', '')
    if tmp_sg:
        print("Lambda probably did not complete last time. Reverting sg %s" % tmp_sg)
        update_env_dict(lambda_client, context, {'TMP_SG_GRP': ''})
        restore_security_group_access(client, tmp_sg)
    instance_name = os.environ.get('AVIATRIX_TAG')
    inst_id = os.environ.get('INST_ID')
    print(f"Trying describe with name {instance_name} and ID {inst_id}")
    describe_err, controller_instanceobj = get_controller_instance(client, instance_name, inst_id)

    if cf_request:
        if describe_err:
            print("From CF Request")
            if event.get("RequestType", None) == 'Create':
                print("Create Event")
                send_response(event, context, 'FAILED', describe_err)
                return
            print("Ignoring delete CFT for no Controller")
            # While deleting cloud formation template, this lambda function
            # will be called to delete AssignEIP resource. If the controller
            # instance is not present, then cloud formation will be stuck
            # in deletion.So just pass in that case.
            send_response(event, context, 'SUCCESS', '')
            return

        try:
            response_status, err_reason = handle_cloud_formation_request(
                client, event, lambda_client, controller_instanceobj, context, instance_name)
        except AvxError as err:
            err_reason = str(err)
            print(err_reason)
            response_status = 'FAILED'
        except Exception as err:  # pylint: disable=broad-except
            err_reason = str(err)
            print(traceback.format_exc())
            response_status = 'FAILED'

        # Send response to CFT.
        if response_status not in ['SUCCESS', 'FAILED']:
            response_status = 'FAILED'
        send_response(event, context, response_status, err_reason)
        print("Sent {} to CFT.".format(response_status))
    elif sns_event:
        if describe_err:
            try:
                sns_msg_event = (json.loads(event["Records"][0]["Sns"]["Message"]))['Event']
                print(sns_msg_event)
            except (KeyError, IndexError, ValueError) as err:
                raise AvxError("1.Could not parse SNS message %s" % str(err)) from err
            if not sns_msg_event == "autoscaling:EC2_INSTANCE_LAUNCH_ERROR":
                print("Not from launch error. Exiting")
                return
            print("From the instance launch error. Will attempt to re-create Auto scaling group")
        try:
            sns_msg_json = json.loads(event["Records"][0]["Sns"]["Message"])
            sns_msg_event = sns_msg_json['Event']
            sns_msg_desc = sns_msg_json.get('Description', "")
        except (KeyError, IndexError, ValueError) as err:
            raise AvxError("2. Could not parse SNS message %s" % str(err)) from err
        print("SNS Event %s Description %s " % (sns_msg_event, sns_msg_desc))
        if sns_msg_event == "autoscaling:EC2_INSTANCE_LAUNCH":
            print("Instance launched from Autoscaling")
            handle_ha_event(client, lambda_client, controller_instanceobj, context)
        elif sns_msg_event == "autoscaling:TEST_NOTIFICATION":
            print("Successfully received Test Event from ASG")
        elif sns_msg_event == "autoscaling:EC2_INSTANCE_LAUNCH_ERROR":
            # and "The security group" in sns_msg_desc and "does not exist in VPC" in sns_msg_desc:
            print("Instance launch error, recreating with new security group configuration")
            sg_id = create_new_sg(client)
            ami_id = os.environ.get('AMI_ID')
            inst_type = os.environ.get('INST_TYPE')
            key_name = os.environ.get('KEY_NAME')
            delete_resources(None, detach_instances=False)
            setup_ha(ami_id, inst_type, None, key_name, [sg_id], context, attach_instance=False)
    else:
        print("Unknown source. Not from CFT or SNS")


def handle_cloud_formation_request(client, event, lambda_client, controller_instanceobj, context,
                                   instance_name):
    """Handle Requests from cloud formation"""
    response_status = 'SUCCESS'
    err_reason = ''
    if event['RequestType'] == 'Create':
        try:
            os.environ['TOPIC_ARN'] = 'N/A'
            os.environ['S3_BUCKET_REGION'] = ""
            set_environ(client, lambda_client, controller_instanceobj, context)
            print("Environment variables have been set.")
        except Exception as err:
            err_reason = "Failed to setup environment variables %s" % str(err)
            print(err_reason)
            return 'FAILED', err_reason

        if not verify_iam(controller_instanceobj):
            return 'FAILED', 'IAM role aviatrix-role-ec2 could not be verified to be attached to' \
                             ' controller'
        bucket_status, bucket_region = verify_bucket(controller_instanceobj)
        os.environ['S3_BUCKET_REGION'] = bucket_region
        update_env_dict(lambda_client, context, {"S3_BUCKET_REGION": bucket_region})
        if not bucket_status:
            return 'FAILED', 'Unable to verify S3 bucket'
        backup_file_status, backup_file = verify_backup_file(controller_instanceobj)
        if not backup_file_status:
            return 'FAILED', 'Cannot find backup file in the bucket'
        if not is_backup_file_is_recent(backup_file):
            return 'FAILED', f'Backup file is older than {MAXIMUM_BACKUP_AGE}'
        if not assign_eip(client, controller_instanceobj, None):
            return 'FAILED', 'Failed to associate EIP or EIP was not found.' \
                             ' Please attach an EIP to the controller before enabling HA'
        if not check_ami_id(controller_instanceobj['ImageId']):
            return 'FAILED', "AMI is not latest. Cannot enable Controller HA. Please backup" \
                             "/restore to the latest AMI before enabling controller HA"

        print("Verified AWS and controller Credentials and backup file, EIP and AMI ID")
        print("Trying to setup HA")
        try:
            ami_id = controller_instanceobj['ImageId']
            inst_id = controller_instanceobj['InstanceId']
            inst_type = controller_instanceobj['InstanceType']
            key_name = controller_instanceobj.get('KeyName', '')
            sgs = [sg_['GroupId'] for sg_ in controller_instanceobj['SecurityGroups']]
            setup_ha(ami_id, inst_type, inst_id, key_name, sgs, context)
        except Exception as err:
            response_status = 'FAILED'
            err_reason = "Failed to setup HA. %s" % str(err)
            print(err_reason)
    elif event['RequestType'] == 'Delete':
        try:
            print("Trying to delete lambda created resources")
            inst_id = controller_instanceobj['InstanceId']
            delete_resources(inst_id)
        except Exception as err:
            err_reason = "Failed to delete lambda created resources. %s" % str(err)
            print(err_reason)
            print("You'll have to manually delete Auto Scaling group,"
                  " Launch Configuration, and SNS topic, all with"
                  " name {}.".format(instance_name))
            response_status = 'FAILED'
    return response_status, err_reason


def verify_iam(controller_instanceobj):
    """ Verify IAM roles"""
    print("Verifying IAM roles ")
    iam_arn = controller_instanceobj.get('IamInstanceProfile', {}).get('Arn', '')
    if not iam_arn:
        return False
    return True


def handle_login_failure(priv_ip,
                         client, lambda_client, controller_instanceobj, context,
                         eip):
    """ Handle login failure through private IP"""
    print("Checking for backup file")
    new_version_file = "CloudN_" + priv_ip + "_save_cloudx_version.txt"
    try:
        retrieve_controller_version(new_version_file)
    except Exception as err:
        print(str(err))
        print("Could not retrieve new version file. Stopping instance. ASG will terminate and "
              "launch a new instance")
        inst_id = controller_instanceobj['InstanceId']
        print("Stopping %s" % inst_id)
        client.stop_instances(InstanceIds=[inst_id])
    else:
        print("Successfully retrieved version. Previous restore operation had succeeded. "
              "Previous lambda may have exceeded 5 min. Updating lambda config")
        set_environ(client, lambda_client, controller_instanceobj, context, eip)


def handle_ha_event(client, lambda_client, controller_instanceobj, context):
    """ Restores the backup by doing the following
    1. Login to new controller
    2. Assign the EIP to the new controller
    3. Run initial setup to boot to specific version parsed from backup
    4. Login again and restore the configuration """
    start_time = time.time()
    old_inst_id = os.environ.get('INST_ID')
    if old_inst_id == controller_instanceobj['InstanceId']:
        print("Controller is already saved. Not restoring")
        return
    if os.environ.get('DISABLE_API_TERMINATION') == "True":
        try:
            boto3.resource('ec2').Instance(  # pylint: disable=no-member
                controller_instanceobj['InstanceId']) \
                .modify_attribute(DisableApiTermination={'Value': True})
            print("Updated controller instance termination protection "
                  "to be true")
        except Exception as err:
            print(err)
    else:
        print("Not updating controller instance termination protection")
    if not assign_eip(client, controller_instanceobj, os.environ.get('EIP')):
        raise AvxError("Could not assign EIP")
    eip = os.environ.get('EIP')
    api_private_access = os.environ.get('API_PRIVATE_ACCESS')
    new_private_ip = controller_instanceobj.get(
        'NetworkInterfaces')[0].get('PrivateIpAddress')
    print("New Private IP " + str(new_private_ip))
    if api_private_access == "True":
        controller_api_ip = new_private_ip
        print("API Access to Controller will use Private IP : " + str(controller_api_ip))
    else:
        controller_api_ip = eip
        print("API Access to Controller will use Public IP : " + str(controller_api_ip))

    threading.Thread(target=enable_t2_unlimited,
                     args=[client, controller_instanceobj['InstanceId']]).start()
    duplicate, sg_modified = temp_add_security_group_access(client, controller_instanceobj,
                                                            api_private_access)
    print("0.0.0.0:443/0 rule is %s present %s" %
          ("already" if duplicate else "not",
           "" if duplicate else ". Modified Security group %s" % sg_modified))

    priv_ip = os.environ.get('PRIV_IP')  # This private IP belongs to older terminated instance
    s3_file = "CloudN_" + priv_ip + "_save_cloudx_config.enc"

    if not is_backup_file_is_recent(s3_file):
        raise AvxError(f"HA event failed. Backup file does not exist or is older"
                       f" than {MAXIMUM_BACKUP_AGE}")

    try:
        if not duplicate:
            update_env_dict(lambda_client, context, {'TMP_SG_GRP': sg_modified})
        while time.time() - start_time < HANDLE_HA_TIMEOUT:
            try:
                cid = login_to_controller(controller_api_ip, "admin", new_private_ip)
            except AvxError as err:
                print(f"Login failed due to {err} trying again in {WAIT_DELAY}")
                time.sleep(WAIT_DELAY)
            except Exception:
                print(f'Login failed due to {traceback.format_exc()} trying again in {WAIT_DELAY}')
                time.sleep(WAIT_DELAY)
            else:
                break
        if time.time() - start_time >= HANDLE_HA_TIMEOUT:
            print("Could not login to the controller. Attempting to handle login failure")
            handle_login_failure(controller_api_ip, client, lambda_client, controller_instanceobj,
                                 context, eip)
            return

        version_file = "CloudN_" + priv_ip + "_save_cloudx_version.txt"
        ctrl_version, ctrl_version_with_build = retrieve_controller_version(
            version_file)
        if is_upgrade_to_build_supported(controller_api_ip, cid):
            ctrl_version = ctrl_version_with_build

        initial_setup_complete = run_initial_setup(controller_api_ip, cid, ctrl_version)

        temp_acc_name = "tempacc"

        sleep = False
        created_temp_acc = False
        login_complete = False
        response_json = {}
        while time.time() - start_time < HANDLE_HA_TIMEOUT:
            print("Maximum of " +
                  str(int(HANDLE_HA_TIMEOUT - (time.time() - start_time))) +
                  " seconds remaining")
            if sleep:
                print("Waiting for safe initial setup completion")
                time.sleep(WAIT_DELAY)
            else:
                sleep = True
            if not login_complete:
                # Need to login again as initial setup invalidates cid after waiting
                print("Logging in again")
                try:
                    cid = login_to_controller(controller_api_ip, "admin", new_private_ip)
                except AvxError:  # It might not succeed since apache2 could restart
                    print("Cannot connect to the controller")
                    sleep = False
                    time.sleep(INITIAL_SETUP_DELAY)
                    continue
                else:
                    login_complete = True
            if not initial_setup_complete:
                response_json = get_initial_setup_status(controller_api_ip, cid)
                print("Initial setup status %s" % response_json)
                if response_json.get('return', False) is True:
                    initial_setup_complete = True
            if initial_setup_complete and not created_temp_acc:
                response_json = create_cloud_account(cid, controller_api_ip, temp_acc_name)
                print(response_json)
                if response_json.get('return', False) is True:
                    created_temp_acc = True
                elif "already exists" in response_json.get('reason', ''):
                    created_temp_acc = True
            if created_temp_acc and initial_setup_complete:
                if os.environ.get("CUSTOMER_ID"):  # Support for license migration scenario
                    set_customer_id(cid, controller_api_ip)
                response_json = restore_backup(cid, controller_api_ip, s3_file, temp_acc_name)
                print(response_json)
            if response_json.get('return', False) is True and created_temp_acc:
                # If restore succeeded, update private IP to that of the new
                #  instance now.
                print("Successfully restored backup. Updating lambda configuration")
                set_environ(client, lambda_client, controller_instanceobj, context, eip)
                print("Updated lambda configuration")
                print("Controller HA event has been successfully handled")
                return
            if response_json.get('reason', '') == 'account_password required.':
                print("API is not ready yet, requires account_password")
            elif response_json.get('reason', '') == 'valid action required':
                print("API is not ready yet")
            elif response_json.get('reason', '') == 'CID is invalid or expired.' or \
                    "Invalid session. Please login again." in response_json.get('reason', '') or \
                    f"Session {cid} not found" in response_json.get('reason', '') or \
                    f"Session {cid} expired" in response_json.get('reason', ''):
                print("Service abrupty restarted")
                sleep = False
                try:
                    cid = login_to_controller(controller_api_ip, "admin", new_private_ip)
                except AvxError:
                    pass
            elif response_json.get('reason', '') == 'not run':
                print('Initial setup not complete..waiting')
                time.sleep(INITIAL_SETUP_DELAY)
                sleep = False
            elif 'Remote end closed connection without response' in response_json.get('reason', ''):
                print('Remote side closed the connection..waiting')
                time.sleep(INITIAL_SETUP_DELAY)
                sleep = False
            elif "Failed to establish a new connection" in response_json.get('reason', '') \
                    or "Max retries exceeded with url" in response_json.get('reason', ''):
                print('Failed to connect to the controller')
            else:
                print("Restoring backup failed due to " +
                      str(response_json.get('reason', '')))
                return
        raise AvxError("Restore failed, did not update lambda config")
    finally:
        if not duplicate:
            print("Reverting sg %s" % sg_modified)
            update_env_dict(lambda_client, context, {'TMP_SG_GRP': ''})
            restore_security_group_access(client, sg_modified)


def validate_subnets(subnet_list):
    """ Validates subnets"""
    vpc_id = os.environ.get('VPC_ID')
    if not vpc_id:
        print("New creation. Assuming subnets are valid as selected from CFT")
        return ",".join(subnet_list)
    try:
        client = boto3.client('ec2')
        response = client.describe_subnets(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
    except botocore.exceptions.ClientError as err:
        raise AvxError(str(err)) from err
    sub_aws_list = [sub['SubnetId'] for sub in response['Subnets']]
    sub_list_new = [sub for sub in subnet_list if sub.strip() in sub_aws_list]
    if not sub_list_new:
        ctrl_subnet = os.environ.get('CTRL_SUBNET')
        if ctrl_subnet not in sub_aws_list:
            raise AvxError("All subnets %s or controller subnet %s are not found in vpc %s")
        print("All subnets are invalid. Using existing controller subnet")
        return ctrl_subnet
    return ",".join(sub_list_new)


def setup_ha(ami_id, inst_type, inst_id, key_name, sg_list, context,
             attach_instance=True):
    """ Setup HA """
    print("HA config ami_id %s, inst_type %s, inst_id %s, key_name %s, sg_list %s, "
          "attach_instance %s" % (ami_id, inst_type, inst_id, key_name, sg_list, attach_instance))
    lc_name = asg_name = sns_topic = os.environ.get('AVIATRIX_TAG')
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

    if inst_id:
        print("Setting launch config from instance")
        asg_client.create_launch_configuration(
            LaunchConfigurationName=lc_name,
            ImageId=ami_id,
            InstanceId=inst_id,
            BlockDeviceMappings=bld_map,
            UserData="# Ignore"
        )

        target_group_arns = get_target_group_arns(inst_id)
        if target_group_arns:
            update_env_dict(lambda_client, context,
                            {'TARGET_GROUP_ARNS': json.dumps(target_group_arns)})
        if is_controller_termination_protected(inst_id):
            update_env_dict(lambda_client, context,
                            {'DISABLE_API_TERMINATION': "True"})
    else:
        print("Setting launch config from environment")
        iam_arn = os.environ.get('IAM_ARN')
        monitoring = os.environ.get('MONITORING', 'disabled') == 'enabled'

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


def delete_resources(inst_id, delete_sns=True, detach_instances=True):
    """ Cloud formation cleanup"""
    lc_name = asg_name = os.environ.get('AVIATRIX_TAG')

    asg_client = boto3.client('autoscaling')
    if detach_instances:
        try:
            # in case customer manually changed the MinSize to greater than 0.
            asg_client.update_auto_scaling_group(
                AutoScalingGroupName=asg_name,
                MinSize=0)
            print("Updated asg MinSize to be 0 before detaching")
            asg_client.detach_instances(
                InstanceIds=[inst_id],
                AutoScalingGroupName=asg_name,
                ShouldDecrementDesiredCapacity=True)
            print("Controller instance detached from autoscaling group")
        except botocore.exceptions.ClientError as err:
            print(str(err))
    try:
        asg_client.delete_auto_scaling_group(AutoScalingGroupName=asg_name,
                                             ForceDelete=True)
    except botocore.exceptions.ClientError as err:
        if "AutoScalingGroup name not found" in str(err):
            print('ASG already deleted')
        else:
            raise AvxError(str(err)) from err
    print("Autoscaling group deleted")
    try:
        asg_client.delete_launch_configuration(LaunchConfigurationName=lc_name)
    except botocore.exceptions.ClientError as err:
        if "Launch configuration name not found" in str(err):
            print('LC already deleted')
        else:
            print(str(err))
    print("Launch configuration deleted")
    if delete_sns:
        print("Deleting SNS topic")
        sns_client = boto3.client('sns')
        topic_arn = os.environ.get('TOPIC_ARN')
        if topic_arn == "N/A" or not topic_arn:
            print("Topic not created. Exiting")
            return
        try:
            response = sns_client.list_subscriptions_by_topic(TopicArn=topic_arn)
        except botocore.exceptions.ClientError as err:
            print('Could not delete topic due to %s' % str(err))
        else:
            for subscription in response.get('Subscriptions', []):
                try:
                    sns_client.unsubscribe(SubscriptionArn=subscription.get('SubscriptionArn', ''))
                except botocore.exceptions.ClientError as err:
                    print(str(err))
            print("Deleted subscriptions")
        try:
            sns_client.delete_topic(TopicArn=topic_arn)
        except botocore.exceptions.ClientError as err:
            print('Could not delete topic due to %s' % str(err))
        else:
            print("SNS topic deleted")


def send_response(event, context, response_status, reason='',
                  response_data=None, physical_resource_id=None):
    """ Send response to cloud formation template for custom resource creation
     by cloud formation"""

    response_data = response_data or {}
    response_body = json.dumps(
        {
            'Status': response_status,
            'Reason': str(reason) + ". See the details in CloudWatch Log Stream: " +
                      context.log_stream_name,
            'PhysicalResourceId': physical_resource_id or context.log_stream_name,
            'StackId': event['StackId'],
            'RequestId': event['RequestId'],
            'LogicalResourceId': event['LogicalResourceId'],
            'Data': response_data
        }
    )
    opener = build_opener(HTTPHandler)
    request = Request(event['ResponseURL'], data=response_body.encode())
    request.add_header('Content-Type', '')
    request.add_header('Content-Length', len(response_body.encode()))
    request.get_method = lambda: 'PUT'
    try:
        response = opener.open(request)
        print("Status code: {}".format(response.getcode()))
        print("Status message: {}".format(response.msg))
        return True
    except HTTPError as exc:
        print("Failed executing HTTP request: {}".format(exc.code))
        return False
