import logging
import os
import time
from enum import Enum, auto
from typing import Any

from types_boto3_ec2.client import EC2Client
from types_boto3_ec2.type_defs import InstanceTypeDef
from types_boto3_lambda.client import LambdaClient

from aviatrix_ha.api import client
from aviatrix_ha.api.external.ip import get_public_ip
from aviatrix_ha.common.constants import (
    HANDLE_HA_TIMEOUT,
    TEMP_ACCOUNT_NAME,
    WAIT_DELAY,
)
from aviatrix_ha.csp.eip import assign_eip
from aviatrix_ha.csp.instance import enable_t2_unlimited
from aviatrix_ha.csp.lambda_c import set_environ, update_env_dict
from aviatrix_ha.csp.s3 import (
    MAXIMUM_BACKUP_AGE,
    is_backup_file_is_recent,
)
from aviatrix_ha.csp.sg import (
    disable_open_sg_rules,
    enable_open_sg_rules,
    restore_security_group_access,
    temp_add_security_group_access,
)
from aviatrix_ha.errors.exceptions import AvxError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class HAStepResult(Enum):
    # CONTINUE means we should contiue with the next step
    CONTINUE = auto()
    # FINISH means we should stop processing steps
    FINISH = auto()
    # Note that fatal errors are indicated by raising AvxError exceptions


class HAEventHandler:
    """Encapsulates the steps taken to handle a HA event"""

    def __init__(
        self,
        ec2_client: EC2Client,
        lambda_client: LambdaClient,
        context: Any,
        controller_instance: InstanceTypeDef,
    ):
        self.ec2_client = ec2_client
        self.lambda_client = lambda_client
        self.context = context
        self.controller_instance = controller_instance
        self.start_time = time.time()

        self.public_ip = self.api_ip = os.environ.get("EIP", "")
        self.private_ip = controller_instance["NetworkInterfaces"][0][
            "PrivateIpAddress"
        ]
        if self.api_ip is None or os.environ.get("API_PRIVATE_ACCESS") == "True":
            self.api_ip = self.private_ip

        if self.api_ip is None:
            raise AvxError("Could not determine controller API endpoint IP")
        self.client = client.ApiClient(self.api_ip)

    def deadline_exceeded(self) -> bool:
        return time.time() - self.start_time >= HANDLE_HA_TIMEOUT

    def disable_api_termination_step(self) -> HAStepResult:
        old_inst_id = os.environ.get("INST_ID")
        if old_inst_id == self.controller_instance["InstanceId"]:
            logger.info("Controller is already saved. Not restoring")
            return HAStepResult.FINISH
        if os.environ.get("DISABLE_API_TERMINATION") == "True":
            try:
                self.ec2_client.modify_instance_attribute(
                    InstanceId=self.controller_instance["InstanceId"],
                    DisableApiTermination={"Value": True},
                )
                logger.info(
                    "Updated controller instance termination protection to be true"
                )
            except Exception as err:
                logger.exception(err)
                return HAStepResult.FINISH
        else:
            logger.info("Not updating controller instance termination protection")
        return HAStepResult.CONTINUE

    def disable_open_sg_rules_step(self) -> HAStepResult:
        logger.info("Disabling any open SG rules")
        modified_rules = disable_open_sg_rules(
            self.ec2_client, self.controller_instance["InstanceId"]
        )
        if modified_rules:
            logger.info("Disabled rules: %s", modified_rules)

        rsp = self.ec2_client.describe_security_groups(
            GroupIds=[
                sg["GroupId"] for sg in self.controller_instance["SecurityGroups"]
            ],
        )
        logger.info("Current security groups for the controller instance: %s", rsp)
        return HAStepResult.CONTINUE

    def enable_open_sg_rules_step(self) -> HAStepResult:
        logger.info("Re-enabling any previously allowed open SG rules")
        enable_open_sg_rules(self.ec2_client, self.controller_instance["InstanceId"])

        rsp = self.ec2_client.describe_security_groups(
            GroupIds=[
                sg["GroupId"] for sg in self.controller_instance["SecurityGroups"]
            ],
        )
        logger.info("Current security groups for the controller instance: %s", rsp)
        return HAStepResult.CONTINUE

    def assign_eip_step(self) -> HAStepResult:
        if os.environ.get("USE_EIP", "False") == "True":
            logger.info("Assigning EIP")
            if not assign_eip(
                self.ec2_client, self.controller_instance, os.environ.get("EIP")
            ):
                raise AvxError("Could not assign EIP")
        else:
            logger.info("Not Assigning EIP")
        return HAStepResult.CONTINUE

    def enable_t2_unlimited_step(self) -> HAStepResult:
        enable_t2_unlimited(self.ec2_client, self.controller_instance["InstanceId"])
        return HAStepResult.CONTINUE

    def create_temp_sg_rule_step(self) -> HAStepResult:
        my_ip = get_public_ip()
        duplicate, sg_modified, sgr_id = temp_add_security_group_access(
            self.ec2_client,
            self.controller_instance,
            my_ip,
            os.environ.get("API_PRIVATE_ACCESS"),
        )
        logger.info(
            "%s:443/32 rule is %s present %s",
            my_ip,
            "already" if duplicate else "not",
            "" if duplicate else f". Modified Security group {sg_modified}/{sgr_id}",
        )
        if not duplicate:
            update_env_dict(
                self.lambda_client,
                self.context,
                {"TMP_SG_GRP": sg_modified, "TMP_SG_RULE": sgr_id},
            )
        return HAStepResult.CONTINUE

    def login_step(self) -> HAStepResult:
        # Because this is a newly created instance, it may take some time for the
        # controller to be ready to accept logins.
        while not self.deadline_exceeded():
            try:
                self.client.login("admin", self.private_ip)
                break
            except Exception as err:
                logger.exception(
                    "Login failed due to %s: trying again in %s", err, WAIT_DELAY
                )
                time.sleep(WAIT_DELAY)
        return HAStepResult.CONTINUE

    def initial_setup_step(self) -> HAStepResult:
        logger.info("Running initial setup")
        self.client.initial_setup()
        return HAStepResult.CONTINUE

    def create_temp_account_step(self) -> HAStepResult:
        """Need to retry because initial_setup_step takes some time"""
        logger.info("Creating temporary account for config restore")
        while not self.deadline_exceeded():
            try:
                response_json = self.client.create_cloud_account(TEMP_ACCOUNT_NAME)
                if response_json.get("return", False) is True:
                    logger.info("Successfully created temp account for restore")
                    return HAStepResult.CONTINUE
                logger.warning(
                    "Create temp account returned failure: %s, retrying in %s",
                    response_json,
                    WAIT_DELAY,
                )
            except Exception as err:
                logger.exception(
                    "Failed to create temp account due to %s: retrying in %s",
                    err,
                    WAIT_DELAY,
                )
            time.sleep(WAIT_DELAY)
        raise AvxError("Deadline exceeded while creating temp account")

    def restore_backup_step(self) -> HAStepResult:
        priv_ip = os.environ.get(
            "PRIV_IP"
        )  # This private IP belongs to older terminated instance
        s3_file = f"CloudN_{priv_ip}_save_cloudx_config.enc"
        logger.info("Restoring backup file %s", s3_file)
        if not is_backup_file_is_recent(s3_file):
            raise AvxError(
                f"HA event failed. Backup file {s3_file} does not exist or is older"
                f" than {MAXIMUM_BACKUP_AGE}"
            )

        response_json = self.client.restore_backup(s3_file, TEMP_ACCOUNT_NAME)
        if response_json.get("return", False) is not True:
            raise AvxError(f"Could not restore backup: {response_json}")
        return HAStepResult.CONTINUE

    def update_lambda_env_step(self) -> HAStepResult:
        set_environ(
            self.ec2_client,
            self.lambda_client,
            self.controller_instance,
            self.context,
            self.public_ip,
        )
        return HAStepResult.CONTINUE

    def remove_temp_sg_rule_step(self) -> HAStepResult:
        if not os.environ.get("TMP_SG_GRP") or not os.environ.get("TMP_SG_RULE"):
            return HAStepResult.CONTINUE
        restore_security_group_access(
            self.ec2_client, os.environ["TMP_SG_GRP"], os.environ["TMP_SG_RULE"]
        )
        update_env_dict(
            self.lambda_client, self.context, {"TMP_SG_GRP": "", "TMP_SG_RULE": ""}
        )
        return HAStepResult.CONTINUE

    def run(self) -> None:
        steps = [
            self.disable_api_termination_step,
            self.disable_open_sg_rules_step,
            self.assign_eip_step,
            self.enable_t2_unlimited_step,
            self.create_temp_sg_rule_step,
            self.login_step,
            self.initial_setup_step,
            self.create_temp_account_step,
            self.restore_backup_step,
            self.update_lambda_env_step,
            self.enable_open_sg_rules_step,
        ]
        cleanup_steps = [
            self.remove_temp_sg_rule_step,
            self.enable_open_sg_rules_step,
        ]
        try:
            for step in steps:
                if self.deadline_exceeded():
                    raise AvxError("Deadline exceeded while handling HA event")
                result = step()
                if result == HAStepResult.FINISH:
                    return
        except Exception:
            raise
        finally:
            for step in cleanup_steps:
                try:
                    step()
                except Exception as err:
                    logger.exception(
                        "Error during cleanup step %s: %s", step.__name__, err
                    )


def handle_ha_event(
    ec2_client: EC2Client,
    lambda_client: LambdaClient,
    controller_instanceobj: InstanceTypeDef,
    context: Any,
) -> None:
    """handle_ha_event() is called in response to the ASG creating a new controller instance.

    The function will run through a set of steps to restore the controller to a previous state.

    Care has to be taken for each step to be idempotent, so that if the function
    is interrupted, it can be safely re-run without causing problems.
    """
    handler = HAEventHandler(ec2_client, lambda_client, context, controller_instanceobj)
    handler.run()
