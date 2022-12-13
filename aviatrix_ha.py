""" Aviatrix Controller HA Lambda script """
# pylint: disable=too-many-lines,too-many-locals,too-many-branches,too-many-return-statements
# pylint: disable=too-many-statements,too-many-arguments,broad-except
import os
import json
import traceback
import urllib3
from urllib3.exceptions import InsecureRequestWarning
import boto3
import version
from handlers.asg.event import handle_ha_event
from csp.lambda_c import update_env_dict
from csp.sg import restore_security_group_access, create_new_sg
from errors.exceptions import AvxError
from csp.instance import get_controller_instance
from handlers.cft.create import setup_ha
from handlers.cft.delete import delete_resources
from handlers.cft.handler import handle_cloud_formation_request
from handlers.cft.response import send_response

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


