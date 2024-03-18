import os
import threading
import time
import traceback

import boto3

from aviatrix_ha.api.account import create_cloud_account
from aviatrix_ha.api.cust import set_customer_id
from aviatrix_ha.api.initial_setup import get_initial_setup_status, run_initial_setup
from aviatrix_ha.api.login import login_to_controller
from aviatrix_ha.api.restore import restore_backup
from aviatrix_ha.api.upgrade_to_build import is_upgrade_to_build_supported
from aviatrix_ha.common.constants import (
    HANDLE_HA_TIMEOUT,
    INITIAL_SETUP_DELAY,
    WAIT_DELAY,
)
from aviatrix_ha.csp.eip import assign_eip
from aviatrix_ha.csp.instance import enable_t2_unlimited
from aviatrix_ha.csp.lambda_c import set_environ, update_env_dict
from aviatrix_ha.csp.s3 import (
    MAXIMUM_BACKUP_AGE,
    is_backup_file_is_recent,
    retrieve_controller_version,
)
from aviatrix_ha.csp.sg import (
    restore_security_group_access,
    temp_add_security_group_access,
)
from aviatrix_ha.errors.exceptions import AvxError


def handle_ha_event(client, lambda_client, controller_instanceobj, context):
    """Restores the backup by doing the following
    1. Login to new controller
    2. Assign the EIP to the new controller
    3. Run initial setup to boot to specific version parsed from backup
    4. Login again and restore the configuration"""
    start_time = time.time()
    old_inst_id = os.environ.get("INST_ID")
    if old_inst_id == controller_instanceobj["InstanceId"]:
        print("Controller is already saved. Not restoring")
        return
    if os.environ.get("DISABLE_API_TERMINATION") == "True":
        try:
            boto3.resource("ec2").Instance(  # pylint: disable=no-member
                controller_instanceobj["InstanceId"]
            ).modify_attribute(DisableApiTermination={"Value": True})
            print("Updated controller instance termination protection " "to be true")
        except Exception as err:
            print(err)
    else:
        print("Not updating controller instance termination protection")
    if os.environ.get("USE_EIP", "False") == "True":
        print("Assigning EIP")
        if not assign_eip(client, controller_instanceobj, os.environ.get("EIP")):
            raise AvxError("Could not assign EIP")
    else:
        print("Not Assigning EIP")
    eip = os.environ.get("EIP")
    api_private_access = os.environ.get("API_PRIVATE_ACCESS")
    new_private_ip = controller_instanceobj.get("NetworkInterfaces")[0].get(
        "PrivateIpAddress"
    )
    print("New Private IP " + str(new_private_ip))
    if api_private_access == "True":
        controller_api_ip = new_private_ip
        print(
            "API Access to Controller will use Private IP : " + str(controller_api_ip)
        )
    else:
        controller_api_ip = eip
        print("API Access to Controller will use Public IP : " + str(controller_api_ip))

    threading.Thread(
        target=enable_t2_unlimited, args=[client, controller_instanceobj["InstanceId"]]
    ).start()
    duplicate, sg_modified = temp_add_security_group_access(
        client, controller_instanceobj, api_private_access
    )
    print(
        "0.0.0.0:443/0 rule is %s present %s"
        % (
            "already" if duplicate else "not",
            "" if duplicate else ". Modified Security group %s" % sg_modified,
        )
    )

    priv_ip = os.environ.get(
        "PRIV_IP"
    )  # This private IP belongs to older terminated instance
    s3_file = "CloudN_" + priv_ip + "_save_cloudx_config.enc"

    if not is_backup_file_is_recent(s3_file):
        raise AvxError(
            f"HA event failed. Backup file does not exist or is older"
            f" than {MAXIMUM_BACKUP_AGE}"
        )

    try:
        if not duplicate:
            update_env_dict(lambda_client, context, {"TMP_SG_GRP": sg_modified})
        while time.time() - start_time < HANDLE_HA_TIMEOUT:
            try:
                cid = login_to_controller(controller_api_ip, "admin", new_private_ip)
            except AvxError as err:
                print(f"Login failed due to {err} trying again in {WAIT_DELAY}")
                time.sleep(WAIT_DELAY)
            except Exception:
                print(
                    f"Login failed due to {traceback.format_exc()} trying again in {WAIT_DELAY}"
                )
                time.sleep(WAIT_DELAY)
            else:
                break
        if time.time() - start_time >= HANDLE_HA_TIMEOUT:
            print(
                "Could not login to the controller. Attempting to handle login failure"
            )
            handle_login_failure(
                controller_api_ip,
                client,
                lambda_client,
                controller_instanceobj,
                context,
                eip,
            )
            return

        version_file = "CloudN_" + priv_ip + "_save_cloudx_version.txt"
        ctrl_version, ctrl_version_with_build = retrieve_controller_version(
            version_file
        )
        if is_upgrade_to_build_supported(controller_api_ip, cid):
            ctrl_version = ctrl_version_with_build

        initial_setup_complete = run_initial_setup(controller_api_ip, cid, ctrl_version)

        temp_acc_name = "tempacc"

        sleep = False
        created_temp_acc = False
        login_complete = False
        response_json = {}
        while time.time() - start_time < HANDLE_HA_TIMEOUT:
            print(
                "Maximum of "
                + str(int(HANDLE_HA_TIMEOUT - (time.time() - start_time)))
                + " seconds remaining"
            )
            if sleep:
                print("Waiting for safe initial setup completion")
                time.sleep(WAIT_DELAY)
            else:
                sleep = True
            if not login_complete:
                # Need to login again as initial setup invalidates cid after waiting
                print("Logging in again")
                try:
                    cid = login_to_controller(
                        controller_api_ip, "admin", new_private_ip
                    )
                except (
                    AvxError
                ) as err:  # It might not succeed since apache2 could restart
                    print(f"Cannot connect to the controller. {err}")
                    sleep = False
                    time.sleep(INITIAL_SETUP_DELAY)
                    continue
                else:
                    login_complete = True
            if not initial_setup_complete:
                response_json = get_initial_setup_status(controller_api_ip, cid)
                print("Initial setup status %s" % response_json)
                if response_json.get("return", False) is True:
                    initial_setup_complete = True
            if initial_setup_complete and not created_temp_acc:
                response_json = create_cloud_account(
                    cid, controller_api_ip, temp_acc_name
                )
                print(response_json)
                if response_json.get("return", False) is True:
                    created_temp_acc = True
                elif "already exists" in response_json.get("reason", ""):
                    created_temp_acc = True
            if created_temp_acc and initial_setup_complete:
                if os.environ.get(
                    "CUSTOMER_ID"
                ):  # Support for license migration scenario
                    set_customer_id(cid, controller_api_ip)
                response_json = restore_backup(
                    cid, controller_api_ip, s3_file, temp_acc_name
                )
                print(response_json)
            if response_json.get("return", False) is True and created_temp_acc:
                # If restore succeeded, update private IP to that of the new
                #  instance now.
                print("Successfully restored backup. Updating lambda configuration")
                set_environ(client, lambda_client, controller_instanceobj, context, eip)
                print("Updated lambda configuration")
                print("Controller HA event has been successfully handled")
                return
            if response_json.get("reason", "") == "account_password required.":
                print("API is not ready yet, requires account_password")
            elif response_json.get("reason", "") == "valid action required":
                print("API is not ready yet")
            elif (
                response_json.get("reason", "") == "CID is invalid or expired."
                or "Invalid session. Please login again."
                in response_json.get("reason", "")
                or f"Session {cid} not found" in response_json.get("reason", "")
                or f"Session {cid} expired" in response_json.get("reason", "")
            ):
                print("Service abrupty restarted")
                sleep = False
                try:
                    cid = login_to_controller(
                        controller_api_ip, "admin", new_private_ip
                    )
                except AvxError:
                    pass
            elif response_json.get("reason", "") == "not run":
                print("Initial setup not complete..waiting")
                time.sleep(INITIAL_SETUP_DELAY)
                sleep = False
            elif "Remote end closed connection without response" in response_json.get(
                "reason", ""
            ):
                print("Remote side closed the connection..waiting")
                time.sleep(INITIAL_SETUP_DELAY)
                sleep = False
            elif "Failed to establish a new connection" in response_json.get(
                "reason", ""
            ) or "Max retries exceeded with url" in response_json.get("reason", ""):
                print("Failed to connect to the controller")
            else:
                print(
                    "Restoring backup failed due to "
                    + str(response_json.get("reason", ""))
                )
                return
        raise AvxError("Restore failed, did not update lambda config")
    finally:
        if not duplicate:
            print("Reverting sg %s" % sg_modified)
            update_env_dict(lambda_client, context, {"TMP_SG_GRP": ""})
            restore_security_group_access(client, sg_modified)


def handle_login_failure(
    priv_ip, client, lambda_client, controller_instanceobj, context, eip
):
    """Handle login failure through private IP"""
    print("Checking for backup file")
    new_version_file = "CloudN_" + priv_ip + "_save_cloudx_version.txt"
    try:
        retrieve_controller_version(new_version_file)
    except Exception as err:
        print(str(err))
        print(
            "Could not retrieve new version file. Stopping instance. ASG will terminate and "
            "launch a new instance"
        )
        inst_id = controller_instanceobj["InstanceId"]
        print("Stopping %s" % inst_id)
        client.stop_instances(InstanceIds=[inst_id])
    else:
        print(
            "Successfully retrieved version. Previous restore operation had succeeded. "
            "Previous lambda may have exceeded 5 min. Updating lambda config"
        )
        set_environ(client, lambda_client, controller_instanceobj, context, eip)
