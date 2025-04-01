""" Aviatrix Controller HA Lambda script """

# pylint: disable=too-many-lines,too-many-locals,too-many-branches,too-many-return-statements
# pylint: disable=too-many-statements,too-many-arguments,broad-except
import enum
import os
import traceback

import boto3
import urllib3
from urllib3.exceptions import InsecureRequestWarning

from aviatrix_ha.csp.instance import get_controller_instance
from aviatrix_ha.csp.lambda_c import update_env_dict
from aviatrix_ha.csp.sg import restore_security_group_access
from aviatrix_ha.errors.exceptions import AvxError
from aviatrix_ha.handlers.asg.handler import handle_sns_event
from aviatrix_ha.handlers.cft.handler import handle_cft
from aviatrix_ha.handlers.function.handler import handle_function_event
from aviatrix_ha.version import VERSION

urllib3.disable_warnings(InsecureRequestWarning)

print("Loading function")


class EventType(enum.Enum):
    """Enum for event types"""

    CFT = "CFT"
    SNS = "SNS"
    FUNCTION = "Function"
    UNKNOWN = "Unknown"


def lambda_handler(event, context):
    """Entry point of the lambda script"""
    try:
        return _lambda_handler(event, context)
    except AvxError as err:
        print("Operation failed due to: " + str(err))
    except Exception as err:  # pylint: disable=broad-except
        print(str(traceback.format_exc()))
        print("Lambda function failed due to " + str(err))


def _get_event_type(event) -> EventType:
    """Get the event type from the event"""
    if "StackId" in event:
        return EventType.CFT

    try:
        if event["Records"][0]["EventSource"] == "aws:sns":
            return EventType.SNS
    except (AttributeError, IndexError, KeyError, TypeError):
        pass

    if "headers" in event and "requestContext" in event:
        return EventType.FUNCTION

    return EventType.UNKNOWN


def _lambda_handler(event, context):
    """Entry point of the lambda script without exception handling
    This lambda function will serve muliple kinds of requests:
    1) request from CFT - Request to setup HA (setup_ha method) made by CloudFormation template.
    2) sns_event - Request from sns to attach elastic ip to new instance
       created after controller failover.
    3) function_request - request to the function url
    """
    event_type = _get_event_type(event)
    client = boto3.client("ec2")
    lambda_client = boto3.client("lambda")

    tmp_sg = os.environ.get("TMP_SG_GRP", "")
    tmp_sgr = os.environ.get("TMP_SG_RULE", "")
    if event_type != EventType.FUNCTION and tmp_sg and tmp_sgr:
        print(
            f"Lambda probably did not complete last time. Reverting {tmp_sg}/{tmp_sgr}"
        )
        update_env_dict(lambda_client, context, {"TMP_SG_GRP": "", "TMP_SG_RULE": ""})
        restore_security_group_access(client, tmp_sg, tmp_sgr)
    instance_name = os.environ.get("AVIATRIX_TAG")
    inst_id = os.environ.get("INST_ID")
    print(f"Trying describe with name {instance_name} and ID {inst_id}")
    describe_err, controller_instanceobj = get_controller_instance(
        client, instance_name, inst_id
    )

    if event_type == EventType.CFT:
        return handle_cft(
            describe_err,
            event,
            context,
            client,
            lambda_client,
            controller_instanceobj,
            instance_name,
        )
    elif event_type == EventType.SNS:
        return handle_sns_event(
            describe_err, event, client, lambda_client, controller_instanceobj, context
        )
    elif event_type == EventType.FUNCTION:
        return handle_function_event(event, context)
    else:
        print("Unknown source. Not from CFT or SNS")
        return False
