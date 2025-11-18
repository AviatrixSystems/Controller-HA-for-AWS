import os
import traceback
from typing import Any

from types_boto3_ec2.client import EC2Client
from types_boto3_ec2.type_defs import InstanceTypeDef
from types_boto3_lambda.client import LambdaClient

from aviatrix_ha.api.external.ami import check_ami_id
from aviatrix_ha.csp.eip import is_ip_elastic
from aviatrix_ha.csp.instance import get_user_data, verify_iam
from aviatrix_ha.csp.lambda_c import set_environ, update_env_dict
from aviatrix_ha.csp.s3 import (
    MAXIMUM_BACKUP_AGE,
    is_backup_file_is_recent,
    verify_backup_file,
    verify_bucket,
)
from aviatrix_ha.errors.exceptions import AvxError
from aviatrix_ha.handlers.cft.create import setup_ha
from aviatrix_ha.handlers.cft.delete import delete_resources
from aviatrix_ha.handlers.cft.response import send_response


def handle_cft(
    describe_err: str | None,
    event: dict[str, Any],
    context: Any,
    ec2_client: EC2Client,
    lambda_client: LambdaClient,
    controller_instanceobj: InstanceTypeDef,
    instance_name: str,
) -> None:
    """Handle CFT event"""
    # Preserve "PhysicalResourceId" for custom resource "setupHA"
    physical_resource_id = event.get(
        "PhysicalResourceId", f"aviatrix-ha-{instance_name}"
    )
    request_type = event.get("RequestType", None)
    print(f"Using PhysicalResourceId: {physical_resource_id} for {request_type} event")

    if describe_err:
        print("From CF Request")
        if request_type == "Create":
            print("Create Event")
            send_response(
                event, context, "FAILED", describe_err, {}, physical_resource_id
            )
            return
        print("Ignoring delete CFT for no Controller")
        # While deleting cloud formation template, this lambda function
        # will be called to delete AssignEIP resource. If the controller
        # instance is not present, then cloud formation will be stuck
        # in deletion.So just pass in that case.
        send_response(event, context, "SUCCESS", "", {}, physical_resource_id)
        return

    try:
        response_status, err_reason = _handle_cloud_formation_request(
            ec2_client,
            event,
            lambda_client,
            controller_instanceobj,
            context,
            instance_name,
        )
    except AvxError as err:
        err_reason = str(err)
        print(err_reason)
        response_status = "FAILED"
    except Exception as err:  # pylint: disable=broad-except
        err_reason = str(err)
        print(traceback.format_exc())
        response_status = "FAILED"

    # Send response to CFT.
    if response_status not in ["SUCCESS", "FAILED"]:
        response_status = "FAILED"
    send_response(event, context, response_status, err_reason, {}, physical_resource_id)
    print("Sent {} to CFT.".format(response_status))


def _handle_cloud_formation_request(
    ec2_client: EC2Client,
    event: dict[str, Any],
    lambda_client: LambdaClient,
    controller_instanceobj: InstanceTypeDef,
    context: Any,
    instance_name: str,
) -> tuple[str, str]:
    """Handle Requests from cloud formation"""
    response_status = "SUCCESS"
    err_reason = ""
    if event["RequestType"] == "Create":
        try:
            os.environ["TOPIC_ARN"] = "N/A"
            os.environ["S3_BUCKET_REGION"] = ""
            os.environ["SERVICE_URL"] = event["ResourceProperties"]["ServiceURL"]
            set_environ(ec2_client, lambda_client, controller_instanceobj, context)
            print("Environment variables have been set.")
        except Exception as err:
            err_reason = "Failed to setup environment variables %s" % str(err)
            print(traceback.format_exc())
            print(err_reason)
            return "FAILED", err_reason

        if not verify_iam(controller_instanceobj):
            return (
                "FAILED",
                "IAM role aviatrix-role-ec2 could not be verified to be attached to"
                " controller",
            )
        bucket_status, bucket_region = verify_bucket()
        os.environ["S3_BUCKET_REGION"] = bucket_region
        update_env_dict(lambda_client, context, {"S3_BUCKET_REGION": bucket_region})
        if not bucket_status:
            return "FAILED", "Unable to verify S3 bucket"
        backup_file_status, backup_file = verify_backup_file(controller_instanceobj)
        if not backup_file_status:
            return "FAILED", "Cannot find backup file in the bucket"
        if not is_backup_file_is_recent(backup_file):
            return "FAILED", f"Backup file is older than {MAXIMUM_BACKUP_AGE}"
        if os.environ.get("EIP"):
            if not is_ip_elastic(ec2_client, os.environ.get("EIP", "")):
                # Public IP but no Elastic IP
                if (
                    not os.environ.get("API_PRIVATE_ACCESS", "False") == "True"
                ):  # Private mode
                    return (
                        "FAILED",
                        "Failed to associate EIP or EIP was not found."
                        " Please attach an EIP to the controller before enabling HA",
                    )
                else:
                    # Correct the use_eip attribute
                    os.environ["USE_EIP"] = "False"
                    update_env_dict(lambda_client, context, {"USE_EIP": "False"})
            # else  # Elastic IP is valid and attached to the instance
        # else # Else private mode without public IP USE_EIP=False from set_environ() above
        if not check_ami_id(controller_instanceobj["ImageId"]):
            return (
                "FAILED",
                "AMI is not latest. Cannot enable Controller HA. Please backup"
                "/restore to the latest AMI before enabling controller HA",
            )

        print("Verified AWS and controller Credentials and backup file, EIP and AMI ID")
        print("Trying to setup HA")
        ami_id = controller_instanceobj["ImageId"]
        inst_id = controller_instanceobj["InstanceId"]
        inst_type = controller_instanceobj["InstanceType"]
        key_name = controller_instanceobj.get("KeyName", "")
        user_data = get_user_data(ec2_client, controller_instanceobj)
        sgs = [sg_["GroupId"] for sg_ in controller_instanceobj["SecurityGroups"]]
        setup_ha(ami_id, inst_type, inst_id, key_name, sgs, context, user_data)

    elif event["RequestType"] == "Update":
        print("Handling Update request")
        try:
            # Update SERVICE_URL in Lambda environment
            new_service_url = event["ResourceProperties"].get("ServiceURL")
            if new_service_url != os.environ.get("SERVICE_URL"):
                os.environ["SERVICE_URL"] = new_service_url
                update_env_dict(
                    lambda_client, context, {"SERVICE_URL": new_service_url}
                )

            # Recreate launch template and update ASG (SNS stays unchanged)
            ami_id = controller_instanceobj["ImageId"]
            inst_type = controller_instanceobj["InstanceType"]
            key_name = controller_instanceobj.get("KeyName", "")
            user_data = get_user_data(ec2_client, controller_instanceobj)
            sgs = [sg_["GroupId"] for sg_ in controller_instanceobj["SecurityGroups"]]

            # inst_id set to None with cft update, read from environment variables
            setup_ha(
                ami_id,
                inst_type,
                None,
                key_name,
                sgs,
                context,
                user_data,
                attach_instance=False,
                is_update=True,
            )
            print("Update completed successfully")

        except Exception as err:
            err_reason = f"Failed to handle update: {str(err)}"
            print(traceback.format_exc())
            return "FAILED", err_reason

    elif event["RequestType"] == "Delete":
        try:
            print("Trying to delete lambda created resources")
            inst_id = controller_instanceobj["InstanceId"]
            delete_resources(inst_id)
        except Exception as err:
            print(traceback.format_exc())
            err_reason = "Failed to delete lambda created resources. %s" % str(err)
            print(err_reason)
            print(
                "You'll have to manually delete Auto Scaling group,"
                " Launch Configuration, and SNS topic, all with"
                " name {}.".format(instance_name)
            )
            response_status = "FAILED"
    return response_status, err_reason
