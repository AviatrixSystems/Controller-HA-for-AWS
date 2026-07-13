"""Tests for mirroring the source controller's IMDS configuration.

Controller HA must copy the original controller's MetadataOptions onto the ASG
launch template. Otherwise a replacement launched during failover inherits the
account/region default (HttpTokens: optional) and in an environment with an SCP
requiring HttpTokens: required, the RunInstances call is denied and failover
fails immediately.
"""

import boto3
import moto
import pytest

from aviatrix_ha.handlers.cft.create import _create_launch_template

MOTO_AMI_ID = "ami-12c6146b"


@pytest.fixture
def ec2_client():
    with moto.mock_aws():
        yield boto3.client("ec2", region_name="us-east-1")


def _get_lt_data(ec2_client, lt_name):
    version = ec2_client.describe_launch_template_versions(LaunchTemplateName=lt_name)[
        "LaunchTemplateVersions"
    ][0]
    return version["LaunchTemplateData"]


def _create(ec2_client, lt_name, metadata_options):
    _create_launch_template(
        ec2_client,
        lt_name=lt_name,
        ami_id=MOTO_AMI_ID,
        inst_type="t3.large",
        key_name="",
        sg_list=["sg-12345678"],
        user_data="",
        bld_map=[],
        iam_arn="arn:aws:iam::123456789012:instance-profile/test",
        monitoring=False,
        ebz_optimized=False,
        disable_api_term=False,
        unique_tags={("Name", "ctrl"): {"Key": "Name", "Value": "ctrl"}},
        cf_tags=[],
        metadata_options=metadata_options,
    )


def test_launch_template_mirrors_metadata_options(ec2_client):
    """IMDSv2 enforcement from the source controller lands on the template."""
    metadata_options = {"HttpTokens": "required", "HttpEndpoint": "enabled"}
    _create(ec2_client, "lt-imdsv2", metadata_options)

    lt_data = _get_lt_data(ec2_client, "lt-imdsv2")
    assert lt_data["MetadataOptions"]["HttpTokens"] == "required"
    assert lt_data["MetadataOptions"]["HttpEndpoint"] == "enabled"


def test_launch_template_no_metadata_options_when_empty(ec2_client):
    """With no source config we fall back to the account/region default."""
    _create(ec2_client, "lt-default", {})

    lt_data = _get_lt_data(ec2_client, "lt-default")
    assert "MetadataOptions" not in lt_data
