import os

import requests


def restore_backup(cid, controller_ip, s3_file, account_name):
    """Restore backup from the s3 bucket"""
    restore_data = {
        "action": "restore_cloudx_config",
        "cloud_type": "1",
        "account_name": account_name,
        "file_name": s3_file,
        "bucket_name": os.environ.get("S3_BUCKET_BACK"),
    }
    print("Trying to restore config with data %s\n" % str(restore_data))
    restore_data["CID"] = cid
    base_url = "https://" + controller_ip + "/v2/api"
    try:
        response = requests.post(base_url, data=restore_data, verify=False)
    except requests.exceptions.ConnectionError as err:
        if "Remote end closed connection without response" in str(err):
            print(
                "Server closed the connection while executing restore_cloudx_config API."
                " Ignoring response"
            )
            response_json = {
                "return": True,
                "reason": "Warning!! Server closed the connection",
            }
        else:
            print(str(err))
            response_json = {"return": False, "reason": str(err)}
    else:
        response_json = response.json()

    return response_json
