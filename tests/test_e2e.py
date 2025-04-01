"""End-to-end tests for Aviatrix HA module.

Prerequisites for running the test:
1. Set the following environment variables:
    TF_VAR_customer_id: Customer ID for the Aviatrix controller
2. If testing a non-released version of the module, set the following environment variables:
    TF_VAR_controller_version: The version of the controller to deploy
    TF_VAR_environment=staging
    TF_VAR_registry_auth_token=<staging auth token>
3. Build the dev version of the CloudFormation script, and deploy the dev lambda:
    make push_dev

What does this test do:
1. Deploys the controller using the Terraform module
2. Sets up controller HA using CloudFormation
3. Terminates the running controller to trigger HA failover
4. Verifies that the new controller is up and running by logging in to the
   controller. The login will only succeed if backup/restore succeeds.
"""
import datetime
import logging
import os
import time

import boto3
import pytest
from pytest_terraform import terraform


from aviatrix_ha.api import client


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@terraform("e2e_controller", scope="session")
@pytest.mark.skipif(os.environ.get("TF_VAR_customer_id") is None, reason="TF_VAR_customer_id is not set")
def test_e2e_controller(e2e_controller):
    instance_id = e2e_controller.outputs["controller_instance_id"]["value"]
    instance_name = e2e_controller.outputs["controller_name"]["value"]
    eip = e2e_controller.outputs["controller_public_ip"]["value"]
    admin_password = e2e_controller.outputs["controller_admin_password"]["value"]
    if not instance_id or not instance_name or not eip or not admin_password:
        pytest.fail("Failed to get controller instance information")
        return

    try:
        ec2 = boto3.client("ec2", region_name="us-east-1")

        rsp = ec2.describe_instances(
            Filters=[
                {"Name": "instance-state-name", "Values": ["running"]},
                {"Name": "tag:Name", "Values": [instance_name]},
            ]
        )
        # Get the security group id
        sg_id = rsp["Reservations"][0]["Instances"][0]["SecurityGroups"][0]["GroupId"]
        logger.info("Controller instance found: %s, Instance ID: %s, EIP: %s, SG ID: %s",
                    instance_name, instance_id, eip, sg_id)
        ec2.authorize_security_group_ingress(GroupId=sg_id, IpPermissions=[{
            "IpProtocol": "tcp",
            "FromPort": 443,
            "ToPort": 443,
            "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
        }])
        ec2.modify_instance_attribute(
            InstanceId=instance_id, DisableApiTermination={"Value": False}
        )
        ec2.terminate_instances(InstanceIds=[instance_id])
        logger.info("Terminating instance %s", instance_id)
        waiter = ec2.get_waiter("instance_terminated")
        waiter.wait(InstanceIds=[instance_id])
        logger.info("Instance %s terminated", instance_id)

        logger.info("Waiting for new instance to be created")
        waiter = ec2.get_waiter("instance_running")
        waiter.wait(
            Filters=[
                {"Name": "instance-state-name", "Values": ["running"]},
                {"Name": "tag:Name", "Values": [instance_name]},
            ],
            WaiterConfig={"Delay": 30, "MaxAttempts": 10},
        )
        logger.info("New instance created")

        api_client = client.ApiClient(eip)

        deadline = datetime.datetime.now() + datetime.timedelta(minutes=10)
        while datetime.datetime.now() < deadline:
            try:
                api_client.login("admin", admin_password)
                logging.info("Successfully logged in to controller")
                break
            except Exception as err:
                logger.info("Failed to login: %s", err)
                time.sleep(30)
        else:
            pytest.fail("Failed to login to controller")
    finally:
        # We have to manually terminate any matching controller instances,
        # because after HA failover the controller instance that is running is
        # not managed by Terraform, so Terraform will get stuck waiting for the
        # instance to be terminated to resolve dependencies.
        #
        # There is a race condition here because when this code runs, the ASG
        # is still active, so presumably it could start up a new instance
        # before the ASG is cleaned up, but in practice because termination
        # takes a while, Terraform will cleanup the CloudFormation and ASG
        # before the instance finishes terminating.
        rsp = ec2.describe_instances(
            Filters=[
                {"Name": "instance-state-name", "Values": ["running"]},
                {"Name": "tag:Name", "Values": [instance_name]},
            ]
        )

        for reservation in rsp["Reservations"]:
            for instance in reservation["Instances"]:
                # skip if instance is in terminated state
                if instance["State"]["Name"] == "terminated":
                    continue
                instance_id = instance["InstanceId"]
                logger.info("Terminating instance %s", instance_id)
                ec2.modify_instance_attribute(
                    InstanceId=instance_id, DisableApiTermination={"Value": False}
                )
                ec2.terminate_instances(InstanceIds=[instance_id])
