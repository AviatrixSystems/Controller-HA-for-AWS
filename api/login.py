import json

import requests

from tools.string_utils import MASK
from errors.exceptions import AvxError


def get_api_token(ip_addr):
    """ Get API token from controller. Older controllers that don't support it will not have this
    API or endpoints. We return None in that scenario to be backkward compatible """
    try:
        data = requests.get(f'https://{ip_addr}/v2/api?action=get_api_token', verify=False)
    except requests.exceptions.ConnectionError as err:
        print("Can't connect to controller with elastic IP %s. %s" % (ip_addr, str(err)))
        raise AvxError(str(err)) from err
    buf = data.content
    try:
        out = json.loads(buf)
    except ValueError:
        print(f"Token is probably not supported. Reponse is {buf}")
    else:
        try:
            token = out['results']['api_token']
        except (ValueError, AttributeError, TypeError, KeyError) as err:
            print(f"Getting token failed due to {err}")
            print(f"Token is probably not supported. Reponse is {out}")
        else:
            print('Obtained token')
            return token
    print('Did not obtain token')
    return None


def login_to_controller(ip_addr, username, pwd):
    """ Logs into the controller and returns the cid"""
    token = get_api_token(ip_addr)
    headers = {}
    base_url = "https://" + ip_addr + "/v1/api"
    if token:
        headers = {"Content-Type": "application/x-www-form-urlencoded",
                   "X-Access-Key": token}
        base_url = "https://" + ip_addr + "/v2/api"
    try:
        response = requests.post(base_url, verify=False, headers=headers,
                                 data={'username': username, 'password': pwd, 'action': 'login'})
    except Exception as err:
        print("Can't connect to controller with elastic IP %s. %s" % (ip_addr,
                                                                      str(err)))
        raise AvxError(str(err)) from err
    try:
        response_json = response.json()
    except ValueError as err:
        print(f"response not in json {response}")
        raise AvxError("Unable to create session. {}".format(response)) from err
    try:
        cid = response_json.pop('CID')
        print("Created new session with CID {}\n".format(MASK(cid)))
    except KeyError as err:
        print(response_json)
        print("Unable to create session. {} {}".format(err, response_json))
        raise AvxError("Unable to create session. {}".format(err)) from err
    print(response_json)
    return cid
