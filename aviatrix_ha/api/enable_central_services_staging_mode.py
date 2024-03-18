"""Call API to set controller to staging environment."""

import time

import requests

from aviatrix_ha.common.constants import API_TIMEOUT


RESTART_DELAY = 30


def enable_central_services_staging_mode(cid, controller_api_ip):
    print("Enabling staging mode")
    base_url = f"https://{controller_api_ip}/v2/api"
    post_data = {
        "CID": cid,
        "action": "enable_central_services_staging_mode",
    }
    try:
        requests.post(base_url, json=post_data, verify=False, timeout=API_TIMEOUT)
    except requests.exceptions.ConnectionError as err:
        print(f"Request failed: {err}")
        return False
    else:
        print(f"Waiting for {RESTART_DELAY} seconds for controller restart")
        time.sleep(RESTART_DELAY)
        return True
