import json
import os

import requests

AMI_ID = 'https://aviatrix-download.s3-us-west-2.amazonaws.com/AMI_ID/ami_id.json'
DEV_FLAG = "dev_flag"


def check_ami_id(ami_id):
    """ Check if AMI is latest"""
    if os.path.exists(DEV_FLAG):
        print("Skip checking AMI ID for dev work")
        return True
    print("Verifying AMI ID")
    resp = requests.get(AMI_ID)
    ami_dict = json.loads(resp.content)
    for image_type in ami_dict:
        if ami_id in list(ami_dict[image_type].values()):
            print("AMI is valid")
            return True
    print("AMI is not latest. Cannot enable Controller HA. Please backup restore to the latest AMI"
          "before enabling controller HA")
    return False


