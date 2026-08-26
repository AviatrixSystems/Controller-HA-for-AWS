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


def _create(ec2_client, lt_name, metadata_options=None):
    tags = {
        ("Name", "ctrl"): {"Key": "Name", "Value": "ctrl"},
        ("ApplicationCI", "cwj"): {"Key": "ApplicationCI", "Value": "cwj"},
    }
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
        unique_tags=tags,
        cf_tags=[],
        metadata_options=metadata_options or {},
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
    _create(ec2_client, "lt-default")

    lt_data = _get_lt_data(ec2_client, "lt-default")
    assert "MetadataOptions" not in lt_data


def test_launch_template_tags_all_resource_types(ec2_client):
    """Tags must propagate to volumes and network interfaces, not just the instance.

    Customers with IAM permission boundaries requiring tags on all resources
    (e.g. ApplicationCI:cwj) will have RunInstances denied if volume or ENI
    resource types are missing from TagSpecifications.
    """
    _create(ec2_client, "lt-tags")

    lt_data = _get_lt_data(ec2_client, "lt-tags")
    tag_specs = lt_data["TagSpecifications"]
    resource_types = {spec["ResourceType"] for spec in tag_specs}
    assert "instance" in resource_types
    assert "volume" in resource_types
    assert "network-interface" in resource_types

    for spec in tag_specs:
        spec_tags = {t["Key"]: t["Value"] for t in spec["Tags"]}
        assert spec_tags["ApplicationCI"] == "cwj"
