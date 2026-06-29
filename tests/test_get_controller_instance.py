"""Tests for aviatrix_ha.csp.instance.get_controller_instance.

These cover controller lookup, in particular the case where multiple running
instances share the same Name tag and HA must not select the wrong one.
"""

import boto3
import moto
import pytest

from aviatrix_ha.csp.instance import get_controller_instance

NAME_TAG = "my-controller"
MOTO_AMI_ID = "ami-12c6146b"


def run_controller_instance(ec2_client, name, subnet_id=None, private_ip=None):
    """Launch a moto instance tagged with the given Name and return it."""
    kwargs = {
        "ImageId": MOTO_AMI_ID,
        "MinCount": 1,
        "MaxCount": 1,
        "TagSpecifications": [
            {
                "ResourceType": "instance",
                "Tags": [{"Key": "Name", "Value": name}],
            }
        ],
    }
    if subnet_id:
        kwargs["SubnetId"] = subnet_id
    if private_ip:
        kwargs["PrivateIpAddress"] = private_ip
    return ec2_client.run_instances(**kwargs)["Instances"][0]


@pytest.fixture
def ec2_client():
    with moto.mock_aws():
        yield boto3.client("ec2", region_name="us-east-1")


def test_single_instance_is_returned(ec2_client):
    """One running instance with the Name tag is returned with no error."""
    instance = run_controller_instance(ec2_client, NAME_TAG)
    err, found = get_controller_instance(ec2_client, NAME_TAG)
    assert err is None
    assert found["InstanceId"] == instance["InstanceId"]


def test_matching_private_ip_selects_the_right_instance(ec2_client):
    """With multiple Name tag matches, priv_ip selects the intended instance."""
    # Two subnets so the two instances get distinct private IPs.
    vpc_id = ec2_client.create_vpc(CidrBlock="10.0.0.0/16")["Vpc"]["VpcId"]
    subnet_one = ec2_client.create_subnet(VpcId=vpc_id, CidrBlock="10.0.1.0/24")[
        "Subnet"
    ]["SubnetId"]
    subnet_two = ec2_client.create_subnet(VpcId=vpc_id, CidrBlock="10.0.2.0/24")[
        "Subnet"
    ]["SubnetId"]
    intended_instance = run_controller_instance(
        ec2_client, NAME_TAG, subnet_id=subnet_one, private_ip="10.0.1.52"
    )
    run_controller_instance(
        ec2_client, NAME_TAG, subnet_id=subnet_two, private_ip="10.0.2.99"
    )

    err, found = get_controller_instance(ec2_client, NAME_TAG, priv_ip="10.0.1.52")
    assert err is None
    assert found["InstanceId"] == intended_instance["InstanceId"]


def test_multiple_matches_without_private_ip_returns_error(ec2_client):
    """Multiple Name tag matches and no private IP -> error, no guess."""
    run_controller_instance(ec2_client, NAME_TAG)
    run_controller_instance(ec2_client, NAME_TAG)

    err, found = get_controller_instance(ec2_client, NAME_TAG)
    assert err is not None
    assert "2 running instances" in err
    assert found == {}


def test_private_ip_matching_none_returns_error(ec2_client):
    """If priv_ip matches none of the instances, do not select one."""
    run_controller_instance(ec2_client, NAME_TAG)
    run_controller_instance(ec2_client, NAME_TAG)

    err, found = get_controller_instance(ec2_client, NAME_TAG, priv_ip="10.255.255.255")
    assert err is not None
    assert "cannot determine which instance" in err.lower()
    assert found == {}


def test_no_match_and_no_instance_id_returns_error(ec2_client):
    """Nothing found -> error message set, empty instance object."""
    err, found = get_controller_instance(ec2_client, NAME_TAG)
    assert err is not None
    assert NAME_TAG in err
    assert found == {}


def test_instance_id_is_authoritative_over_name_tag(ec2_client):
    """When inst_id is given it is used directly, even with a duplicate tag.

    Reproduces the failover case: a second instance shares the Name tag. The ASG
    reports the exact id of the instance it just launched, and that instance
    must be selected directly - not resolved through the ambiguous Name tag - so
    restore runs against the new controller instead of being skipped.
    """
    run_controller_instance(ec2_client, NAME_TAG)
    launched = run_controller_instance(ec2_client, NAME_TAG)

    err, found = get_controller_instance(
        ec2_client, NAME_TAG, inst_id=launched["InstanceId"]
    )
    assert err is None
    assert found["InstanceId"] == launched["InstanceId"]
