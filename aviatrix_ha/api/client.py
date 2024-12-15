import os
import logging
from typing import Any

import boto3
import requests

from aviatrix_ha.errors.exceptions import AvxError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


OVERRIDE_API_ENDPOINT: str | None = None


def _get_aws_account_number() -> str:
    client = boto3.client("sts")
    return client.get_caller_identity()["Account"]


def _get_role(role: str, default: str) -> str:
    name = os.environ.get(role, "")
    if len(name) == 0:
        return default
    return name


class ApiClient:
    def __init__(self, controller_ip: str):
        self.controller_ip = OVERRIDE_API_ENDPOINT or controller_ip
        self.endpoint = f"https://{self.controller_ip}/v2/api"
        self.cid = ""

    def get_api_token(self) -> str | None:
        try:
            response = requests.get(
                f"{self.endpoint}?action=get_api_token", verify=False
            )
            response.raise_for_status()
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError,
        ) as err:
            raise AvxError(f"Failed to get API token: {err}") from err
        response_json = response.json()
        if response_json.get("return") is False:
            return None
        return response_json.get("results", {}).get("api_token")

    def login(self, username: str, password: str) -> None:
        token = self.get_api_token()
        headers = {}
        if token is not None:
            headers["X-Access-Key"] = token

        try:
            response = requests.post(
                self.endpoint,
                json={
                    "action": "login",
                    "username": username,
                    "password": password,
                },
                headers=headers,
                verify=False,
            )
            response.raise_for_status()
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError,
        ) as err:
            raise AvxError(f"Failed to login: {err}") from err
        response_json = response.json()
        self.cid = response_json.get("CID")

    def get_initial_setup_status(self) -> dict[str, Any]:
        data = {"CID": self.cid, "action": "initial_setup", "subaction": "check"}
        try:
            response = requests.post(self.endpoint, json=data, verify=False)
            response.raise_for_status()
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError,
        ) as err:
            logger.error(err)
            return {"return": False, "reason": str(err)}
        return response.json()

    def initial_setup(self) -> None:
        check = self.get_initial_setup_status()
        if check.get("return") is True:
            logger.info("Initial setup is already done. Skipping")
            return
        setup_data = {
            "CID": self.cid,
            "action": "initial_setup",
            "subaction": "run",
        }
        try:
            response = requests.post(self.endpoint, json=setup_data, verify=False)
            response.raise_for_status()
            response_json = response.json()
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError,
        ) as err:
            raise AvxError(f"Failed to execute initial setup: {err}") from err
        if response_json.get("return") is True:
            logger.info("Successfully initialized the controller")
            return
        raise AvxError(
            "Could not setup the new controller: {response_json.get('reason')"
        )

    def create_cloud_account(self, account_name: str) -> dict[str, Any]:
        aws_acc_num = _get_aws_account_number()
        account_data = {
            "action": "setup_account_profile",
            "account_name": account_name,
            "aws_account_number": aws_acc_num,
            "aws_role_arn": "arn:aws:iam::%s:role/%s"
            % (aws_acc_num, _get_role("AWS_ROLE_APP_NAME", "aviatrix-role-app")),
            "aws_role_ec2": "arn:aws:iam::%s:role/%s"
            % (aws_acc_num, _get_role("AWS_ROLE_EC2_NAME", "aviatrix-role-ec2")),
            "cloud_type": 1,
            "aws_iam": "true",
            "skip_sg_config": "true",
        }
        logger.info("Trying to create account with data %s" % str(account_data))
        account_data["CID"] = self.cid
        try:
            response = requests.post(self.endpoint, json=account_data, verify=False)
            response.raise_for_status()
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError,
        ) as err:
            logger.error(err)
            response_json = {"return": False, "reason": str(err)}
        else:
            response_json = response.json()
        return response_json

    def restore_backup(self, s3_file: str, account_name: str) -> dict[str, Any]:
        restore_data = {
            "action": "restore_cloudx_config",
            "cloud_type": "1",
            "account_name": account_name,
            "file_name": s3_file,
            "bucket_name": os.environ.get("S3_BUCKET_BACK"),
        }
        logger.info("Trying to restore config with data %s" % str(restore_data))
        restore_data["CID"] = self.cid
        try:
            response = requests.post(self.endpoint, json=restore_data, verify=False)
            response.raise_for_status()
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError,
        ) as err:
            logger.error(err)
            response_json = {"return": False, "reason": str(err)}
        else:
            response_json = response.json()
        return response_json
