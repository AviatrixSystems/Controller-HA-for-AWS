import os
import time

import requests

from aviatrix_ha.common.constants import WAIT_DELAY


def set_customer_id(cid, controller_api_ip):
    """ Set the customer ID if set in environment to migrate to a different AMI type"""
    print("Setting up Customer ID")
    base_url = "https://" + controller_api_ip + "/v1/api"
    post_data = {"CID": cid,
                 "action": "setup_customer_id",
                 "customer_id": os.environ.get("CUSTOMER_ID")}
    try:
        response = requests.post(base_url, data=post_data, verify=False)
    except requests.exceptions.ConnectionError as err:
        if "Remote end closed connection without response" in str(err):
            print("Server closed the connection while executing setup_customer_id API."
                  " Ignoring response")
            response_json = {"return": True, 'reason': 'Warning!! Server closed the connection'}
            time.sleep(WAIT_DELAY)
        else:
            response_json = {"return": False, "reason": str(err)}
    else:
        response_json = response.json()

    if response_json.get('return') is True:
        print("Customer ID successfully programmed")
    else:
        print("Customer ID programming failed. DB restore will fail: " +
              response_json.get('reason', ""))
