""" Test Module to test restore functionality"""

import argparse
import base64
import json
import os
import ssl
from typing import Any

import boto3
import botocore
import moto
import pytest
from pytest_httpserver import HTTPServer
import trustme
import werkzeug.wrappers as wrappers

import aviatrix_ha


HA_TAG = "ha_ctrl"

CONTEXT = argparse.Namespace()
CONTEXT.function_name = HA_TAG + "-ha"
CONTEXT.log_stream_name = "aviatrix_ha"


# https://github.com/getmoto/moto/blob/master/tests/__init__.py
MOTO_AMI_ID = "ami-12c6146b"


@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    # defined in cft/aviatrix-aws-existing-controller-ha-v3.json
    monkeypatch.setenv("AVIATRIX_TAG", HA_TAG)
    monkeypatch.setenv("AWS_ROLE_APP_NAME", "aviatrix-role-app")
    monkeypatch.setenv("AWS_ROLE_EC2_NAME", "aviatrix-role-ec2")
    monkeypatch.setenv("SUBNETLIST", "subnet-497e8as511,subnet-87ase3,subnet-aasd6a0ef")
    monkeypatch.setenv("S3_BUCKET_BACK", "backup-bucket")
    monkeypatch.setenv("API_PRIVATE_ACCESS", "False")
    monkeypatch.setenv("NOTIF_EMAIL", "nobody@aviatrix.com")

    # Make sure we are not using real AWS credentials
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


def _cft_message(request_type, lambda_arn):
    return {
        "RequestType": request_type,
        "StackId": "arn:aws:cloudformation:us-west-2:1234567",
        "ServiceToken": lambda_arn,
        "ResponseURL": "https://cloudformation-custom-resource-response",
        "RequestId": "6c5486f4-bd67-4fcc-919a-bee7351c5d0c",
        "LogicalResourceId": "SetupHA",
        "ResourceType": "Custom::SetupHA",
        "ResourceProperties": {
            "ServiceToken": lambda_arn,
            "ServiceURL": "https://test.lambda-url.us-east-1.on.aws/",
        },
    }


def _sns_message(event_type):
    return {
        "Records": [
            {
                "EventSource": "aws:sns",
                "Sns": {
                    "Message": f'{{"Event": "{event_type}"}}',
                },
            }
        ]
    }


def mock_send_response(event, context, status, reason, **kwargs):
    if status != "SUCCESS":
        pytest.fail(f"{status}: {reason}")


orig = botocore.client.BaseClient._make_api_call


def mock_make_api_call(self, operation_name, kwarg):
    # stub out calls not supported by moto
    if operation_name in (
        "PutNotificationConfiguration",
        "ModifyInstanceCreditSpecification",
    ):
        return
    return orig(self, operation_name, kwarg)


@pytest.fixture(scope="session")
def ca():
    return trustme.CA()


@pytest.fixture(scope="session")
def httpserver_ssl_context(ca):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    localhost_cert = ca.issue_cert("localhost")
    localhost_cert.configure_cert(context)
    return context


def respond_with_json(data: dict[str, Any]) -> wrappers.Response:
    return wrappers.Response(json.dumps(data), content_type="application/json")


def v2_api_handler(request: wrappers.Request) -> wrappers.Response:
    print(request.json)
    if request.json.get("action") == "login":
        if request.json.get("username") == "admin":
            return respond_with_json({"return": True, "CID": "mycid"})
        return respond_with_json({"return": False})

    if request.json.get("action") == "initial_setup":
        return respond_with_json({"return": True})

    if request.json.get("action") == "setup_account_profile":
        if request.json.get("account_name") == "tempacc":
            return respond_with_json({"return": True})
        return respond_with_json({"return": False})

    if request.json.get("action") == "restore_cloudx_config":
        if request.json.get("account_name") == "tempacc":
            return respond_with_json({"return": True})
        return respond_with_json({"return": False})

    return wrappers.Response(status=404)


def patch_instance_security_group(ec2, sg_name):
    """Workaround a bug in moto where security group is not attached to
    instance by the ASG"""
    rsp = ec2.describe_instances(
        Filters=[
            {"Name": "instance-state-name", "Values": ["running"]},
            {"Name": "tag:Name", "Values": [HA_TAG]},
        ],
    )
    instance_id = rsp["Reservations"][0]["Instances"][0]["InstanceId"]
    rsp = ec2.describe_security_groups(
        Filters=[{"Name": "group-name", "Values": [sg_name]}],
    )
    sg_id = rsp["SecurityGroups"][0]["GroupId"]
    print(f"Modifying instance {instance_id} to use security group {sg_id}")
    ec2.modify_instance_attribute(
        InstanceId=instance_id,
        Groups=[sg_id],
    )


@moto.mock_aws
def test_lambda_e2e(monkeypatch, httpserver: HTTPServer):
    """Integration test using moto to simulate AWS environment

    This test exercises the typical sequence of events during Controller HA:
    1. CloudFormation creates the HA setup, and triggers the Lambda function.
       As part of this trigger, the Lambda sets up an ASG.
    2. ASG triggers a test notification to the Lambda function.
    3. If the controller instance is terminated, the ASG creates a new one.
       This triggers a notification to the Lambda function which will create and
       setup a new controller, and trigger restore.
    4. Finally if the user removes the HA setup, CloudFormation will trigger
       a delete event to the Lambda function.
    """
    # Check that CFT triggered Lambda calls do not report any errors.
    monkeypatch.setattr(
        aviatrix_ha.handlers.cft.handler, "send_response", mock_send_response
    )
    # Stub out the AMI ID check; moto uses fixed AMI IDs.
    monkeypatch.setattr(
        aviatrix_ha.handlers.cft.handler, "check_ami_id", lambda x: True
    )
    # Stub out some boto3 calls not handled by moto
    monkeypatch.setattr(
        botocore.client.BaseClient, "_make_api_call", mock_make_api_call
    )
    # Use the local HTTP server to mock the Aviatrix API
    monkeypatch.setattr(
        aviatrix_ha.handlers.asg.event.client,
        "OVERRIDE_API_ENDPOINT",
        f"localhost:{httpserver.port}",
    )

    # Handle Aviatrix API requests
    httpserver.expect_request(
        "/v2/api", query_string="action=get_api_token", method="GET"
    ).respond_with_json({"return": True, "results": {"api_token": "mytoken"}})
    httpserver.expect_request(
        "/v2/api",
    ).respond_with_handler(v2_api_handler)

    # Create controller resources expected to exist before HA setup
    ec2 = boto3.client("ec2")
    iam = boto3.client("iam")
    lfn = boto3.client("lambda")
    s3 = boto3.client("s3")

    iam.create_instance_profile(InstanceProfileName="test-profile")
    eip = ec2.allocate_address(Domain="vpc")
    ec2.create_security_group(GroupName="sg-test", Description="test")

    rsp = ec2.run_instances(
        ImageId=MOTO_AMI_ID,
        MinCount=1,
        MaxCount=1,
        IamInstanceProfile={"Name": "test-profile"},
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [{"Key": "Name", "Value": HA_TAG}],
            },
        ],
        SecurityGroups=["sg-test"],
        UserData="""#cloud-config
avx-controller:
    environment: prod
    extra-bootstrap-args:
        image-registry: registry-release.prod.sre.aviatrix.com
        image-registry-auth: some-auth-token
""",
        BlockDeviceMappings=[
            {
                "DeviceName": "/dev/sda1",
                "Ebs": {
                    "VolumeSize": 8,
                    "VolumeType": "gp3",
                    "DeleteOnTermination": True,
                },
            }
        ],
    )
    instance_id = rsp["Instances"][0]["InstanceId"]
    os.environ["INST_ID"] = ""
    priv_ip = rsp["Instances"][0]["NetworkInterfaces"][0]["PrivateIpAddress"]
    ec2.associate_address(
        AllocationId=eip["AllocationId"],
        InstanceId=instance_id,
    )

    # Create resources created by the CloudFormation template
    rsp = iam.create_role(
        RoleName="test-role",
        AssumeRolePolicyDocument="some policy",
        Path="/",
    )
    role_arn = rsp["Role"]["Arn"]

    rsp = lfn.create_function(
        FunctionName=HA_TAG + "-ha",
        Runtime="python3.13",
        Role=role_arn,
        Handler="aviatrix_ha.lambda_handler",
        Code={"ZipFile": b""},
    )
    lambda_arn = rsp["FunctionArn"]

    s3.create_bucket(Bucket=os.environ["S3_BUCKET_BACK"])
    s3.put_object(
        Bucket=os.environ["S3_BUCKET_BACK"],
        Key=f"CloudN_{priv_ip}_save_cloudx_version.txt",
        Body=b"8.0.0-1000.1234",
    )
    s3.put_object(
        Bucket=os.environ["S3_BUCKET_BACK"],
        Key=f"CloudN_{priv_ip}_save_cloudx_config.enc",
        Body=b"some data",
    )

    # ===== Actual test starts here =====
    # We call _lambda_handler instead of lambda_handler so that any exceptions
    # generated will fail the test.

    # Callback from CloudFormation to create the HA setup
    aviatrix_ha._lambda_handler(_cft_message("Create", lambda_arn), CONTEXT)

    # Test notification from ASG
    aviatrix_ha._lambda_handler(_sns_message("autoscaling:TEST_NOTIFICATION"), CONTEXT)

    # Simulate instance being terminated and ASG creating a new one
    ec2.terminate_instances(InstanceIds=[instance_id])
    ec2.disassociate_address(PublicIp=eip["PublicIp"])
    patch_instance_security_group(ec2, "sg-test")
    # Notification from ASG
    aviatrix_ha._lambda_handler(
        _sns_message("autoscaling:EC2_INSTANCE_LAUNCH"), CONTEXT
    )

    # Verify a new instance was launched
    rsp = ec2.describe_instances(
        Filters=[
            {"Name": "instance-state-name", "Values": ["running"]},
            {"Name": "tag:Name", "Values": [HA_TAG]},
        ]
    )
    instance_id = rsp["Reservations"][0]["Instances"][0]["InstanceId"]
    rsp = ec2.describe_instance_attribute(InstanceId=instance_id, Attribute="userData") 
    user_data = base64.b64decode(rsp["UserData"]["Value"]).decode("utf-8")
    print(f"User data from new instance: {user_data}")
    assert "#cloud-config\n" in user_data
    assert "avx-controller:" in user_data
    assert "avx-controller-version-url" in user_data

    # Callback from CloudFormation to delete the HA setup
    aviatrix_ha._lambda_handler(_cft_message("Delete", lambda_arn), CONTEXT)


@moto.mock_aws
def test_lambda_function():
    """Test the lambda function returns the controller version fetched from S3"""
    os.environ["S3_BUCKET_REGION"] = "us-west-2"
    s3 = boto3.client("s3")
    os.environ["PRIV_IP"] = priv_ip = "10.20.30.40"

    s3.create_bucket(Bucket=os.environ["S3_BUCKET_BACK"])
    s3.put_object(
        Bucket=os.environ["S3_BUCKET_BACK"],
        Key=f"CloudN_{priv_ip}_save_cloudx_version.txt",
        Body=b"8.0.0-1000.1234",
    )
    s3.put_object(
        Bucket=os.environ["S3_BUCKET_BACK"],
        Key=f"CloudN_{priv_ip}_save_cloudx_config.enc",
        Body=b"some data",
    )

    event = {
        "headers": {"user-agent": "pytest"},
        "requestContext": {"http": {"method": "GET", "path": "/controller_version"}},
    }
    result = aviatrix_ha._lambda_handler(event, CONTEXT)
    assert result["statusCode"] == 200
    assert result["body"] == "8.0.0-1000.1234"
