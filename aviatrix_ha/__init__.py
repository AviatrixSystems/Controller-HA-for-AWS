""" Aviatrix Controller HA Lambda script """
# pylint: disable=too-many-lines,too-many-locals,too-many-branches,too-many-return-statements
# pylint: disable=too-many-statements,too-many-arguments,broad-except
import os
import traceback
import urllib3
from urllib3.exceptions import InsecureRequestWarning
import boto3
from aviatrix_ha.csp.lambda_c import update_env_dict
from aviatrix_ha.csp.sg import restore_security_group_access, create_new_sg
from aviatrix_ha.errors.exceptions import AvxError
from aviatrix_ha.csp.instance import get_controller_instance
from aviatrix_ha.handlers.cft.handler import handle_cft
from aviatrix_ha.handlers.asg.handler import handle_sns_event
from aviatrix_ha.version import VERSION

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
    print("Version: %s Event: %s" % (VERSION, event))
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
        handle_cft(describe_err, event, context, client, lambda_client, controller_instanceobj,
                   instance_name)
    elif sns_event:
        handle_sns_event(describe_err, event, client, lambda_client, controller_instanceobj,
                         context)
    else:
        print("Unknown source. Not from CFT or SNS")
