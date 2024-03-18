import os

import requests

from aviatrix_ha.common.constants import DEV_FLAG

AMI_ID = "https://aviatrix-download.s3-us-west-2.amazonaws.com/AMI_ID/ami_id.json"


def check_ami_id(ami_id):
    """Check if AMI is latest"""
    if os.path.exists(DEV_FLAG):
        print("Skip checking AMI ID for dev work")
        return True
    print("Verifying AMI ID")
    try:
        resp = requests.get(AMI_ID)
        resp.raise_for_status()
        ami_dict = resp.json()
        for image_type in ami_dict:
            if ami_id in list(ami_dict[image_type].values()):
                print("AMI is valid")
                return True
        print(
            "AMI is not latest. Cannot enable Controller HA. Please backup restore to the latest AMI"
            "before enabling controller HA"
        )
    except requests.RequestException as err:
        print(f"Error checking AMI ID: {err}")
    return False
