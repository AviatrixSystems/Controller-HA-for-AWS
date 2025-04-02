import os
from typing import Any

import requests

from aviatrix_ha.common.constants import DEV_FLAG

AMI_ID = "https://cdn.aviatrix.com/image-details/aws_controller_image_details.json"


def _has_value(data: dict[str, Any], key: str) -> bool:
    for k, v in data.items():
        if isinstance(v, dict):
            if _has_value(v, key):
                return True
        else:
            if v == key:
                return True
    return False


def check_ami_id(ami_id: str) -> bool:
    """Check if AMI is latest"""
    if os.path.exists(DEV_FLAG):
        print("Skip checking AMI ID for dev work")
        return True
    print("Verifying AMI ID")
    try:
        resp = requests.get(AMI_ID)
        resp.raise_for_status()
        ami_dict = resp.json()
        if _has_value(ami_dict, ami_id):
            print("AMI is valid")
            return True
        print(
            "AMI is not latest. Cannot enable Controller HA. Please backup restore to the latest AMI"
            "before enabling controller HA"
        )
    except requests.RequestException as err:
        print(f"Error checking AMI ID: {err}")
    return False
