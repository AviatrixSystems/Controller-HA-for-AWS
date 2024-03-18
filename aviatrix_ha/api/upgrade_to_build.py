import json

import requests


def is_upgrade_to_build_supported(ip_addr, cid):
    """Check if the version supports upgrade to build"""
    print("Checking if upgrade to build is suppported")
    base_url = "https://" + ip_addr + "/v1/api"
    post_data = {"CID": cid, "action": "get_feature_info"}
    try:
        response = requests.post(base_url, data=post_data, verify=False)
        print(response.content)
        response_json = json.loads(response.content)
        if (
            response_json.get("return") is True
            and response_json.get("results", {}).get("allow_build_upgrade") is True
        ):
            print("Upgrade to build is supported")
            return True
    except requests.exceptions.ConnectionError as err:
        print(str(err))
    except (ValueError, TypeError):
        print("json decode failed: {}".format(response.content))
    print("Upgrade to build is not supported")
    return False
