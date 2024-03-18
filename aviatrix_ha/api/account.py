import os
import time

import boto3
import requests

from aviatrix_ha.common.constants import INITIAL_SETUP_DELAY


def create_cloud_account(cid, controller_ip, account_name):
    """ Create a temporary account to restore the backup"""
    print("Creating temporary account")
    client = boto3.client('sts')
    aws_acc_num = client.get_caller_identity()["Account"]
    base_url = "https://%s/v1/api" % controller_ip
    post_data = {
        "action": "setup_account_profile",
        "account_name": account_name,
        "aws_account_number": aws_acc_num,
        "aws_role_arn":
            "arn:aws:iam::%s:role/%s" % (aws_acc_num,
                                         get_role("AWS_ROLE_APP_NAME", "aviatrix-role-app")),
        "aws_role_ec2":
            "arn:aws:iam::%s:role/%s" % (aws_acc_num,
                                         get_role("AWS_ROLE_EC2_NAME", "aviatrix-role-ec2")),
        "cloud_type": 1,
        "aws_iam": "true",
        "skip_sg_config": "true"}
    print("Trying to create account with data %s\n" % str(post_data))
    post_data["CID"] = cid
    try:
        response = requests.post(base_url, data=post_data, verify=False)
    except requests.exceptions.ConnectionError as err:
        if "Remote end closed connection without response" in str(err):
            print("Server closed the connection while executing create account API."
                  " Ignoring response")
            output = {"return": True, 'reason': 'Warning!! Server closed the connection'}
            time.sleep(INITIAL_SETUP_DELAY)
        else:
            output = {"return": False, "reason": str(err)}
    else:
        output = response.json()

    return output


def get_role(role, default):
    """ Get Role name from the environment """
    name = os.environ.get(role)
    if len(name) == 0:
        return default
    return name
