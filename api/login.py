import requests

from aviatrix_ha import get_api_token, AvxError, MASK


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