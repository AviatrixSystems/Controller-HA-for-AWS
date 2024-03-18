import time

import requests

from aviatrix_ha.errors.exceptions import AvxError

INITIAL_SETUP_API_WAIT = 20


def get_initial_setup_status(ip_addr, cid):
    """ Get status of the initial setup completion execution"""
    print("Checking initial setup")
    base_url = "https://" + ip_addr + "/v1/api"
    post_data = {"CID": cid,
                 "action": "initial_setup",
                 "subaction": "check"}
    try:
        response = requests.post(base_url, data=post_data, verify=False)
    except requests.exceptions.ConnectionError as err:
        print(str(err))
        return {'return': False, 'reason': str(err)}
    return response.json()


def run_initial_setup(ip_addr, cid, ctrl_version):
    """ Boots the fresh controller to the specific version"""
    response_json = get_initial_setup_status(ip_addr, cid)
    if response_json.get('return') is True:
        print("Initial setup is already done. Skipping")
        return True
    post_data = {"target_version": ctrl_version,
                 "action": "initial_setup",
                 "subaction": "run"}
    print("Trying to run initial setup %s\n" % str(post_data))
    post_data["CID"] = cid
    base_url = "https://" + ip_addr + "/v1/api"
    try:
        response = requests.post(base_url, data=post_data, verify=False)
    except requests.exceptions.ConnectionError as err:
        if "Remote end closed connection without response" in str(err):
            print("Server closed the connection while executing initial setup API."
                  " Ignoring response")
            response_json = {'return': True, 'reason': 'Warning!! Server closed the connection'}
        else:
            raise AvxError("Failed to execute initial setup: " + str(err)) from err
    else:
        response_json = response.json()
        # Controllers running 6.4 and above would be unresponsive after initial_setup
    print(response_json)
    time.sleep(INITIAL_SETUP_API_WAIT)
    if response_json.get('return') is True:
        print("Successfully initialized the controller")
    else:
        raise AvxError("Could not bring up the new controller to the "
                       "specific version")
    return False
