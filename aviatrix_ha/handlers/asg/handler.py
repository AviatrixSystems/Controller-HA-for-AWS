import json
import os
from typing import cast, Any

from types_boto3_ec2.client import EC2Client
from types_boto3_ec2.literals import InstanceTypeType
from types_boto3_ec2.type_defs import InstanceTypeDef
from types_boto3_lambda.client import LambdaClient

from aviatrix_ha.csp.sg import create_new_sg
from aviatrix_ha.errors.exceptions import AvxError
from aviatrix_ha.handlers.asg.event import handle_ha_event
from aviatrix_ha.handlers.cft.handler import delete_resources, setup_ha


def handle_sns_event(
    describe_err: str | None,
    event: dict[str, Any],
    client: EC2Client,
    lambda_client: LambdaClient,
    controller_instanceobj: InstanceTypeDef,
    context: Any,
) -> None:
    """Handle an autoscaling group event which is sent by SNS"""
    if describe_err:
        try:
            sns_msg_event = (json.loads(event["Records"][0]["Sns"]["Message"]))["Event"]
            print(sns_msg_event)
        except (KeyError, IndexError, ValueError) as err:
            raise AvxError("1.Could not parse SNS message %s" % str(err)) from err
        if not sns_msg_event == "autoscaling:EC2_INSTANCE_LAUNCH_ERROR":
            print("Not from launch error. Exiting")
            return
        print(
            "From the instance launch error. Will attempt to re-create Auto scaling group"
        )
    try:
        sns_msg_json = json.loads(event["Records"][0]["Sns"]["Message"])
        sns_msg_event = sns_msg_json["Event"]
        sns_msg_desc = sns_msg_json.get("Description", "")
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
        ami_id = os.environ.get("AMI_ID", "")
        inst_type = cast(InstanceTypeType, os.environ.get("INST_TYPE", ""))
        key_name = os.environ.get("KEY_NAME", "")
        user_data = os.environ.get("USER_DATA", "")
        delete_resources(None, detach_instances=False)
        setup_ha(
            ami_id,
            inst_type,
            None,
            key_name,
            [sg_id],
            context,
            user_data,
            attach_instance=False,
        )
