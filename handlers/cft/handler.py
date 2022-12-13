import os

from api.external.ami import check_ami_id
from csp.eip import assign_eip
from csp.instance import verify_iam
from csp.lambda_c import set_environ, update_env_dict
from csp.s3 import verify_bucket, verify_backup_file, is_backup_file_is_recent, MAXIMUM_BACKUP_AGE
from handlers.cft.create import setup_ha
from handlers.cft.delete import delete_resources


def handle_cloud_formation_request(client, event, lambda_client, controller_instanceobj, context,
                                   instance_name):
    """Handle Requests from cloud formation"""
    response_status = 'SUCCESS'
    err_reason = ''
    if event['RequestType'] == 'Create':
        try:
            os.environ['TOPIC_ARN'] = 'N/A'
            os.environ['S3_BUCKET_REGION'] = ""
            set_environ(client, lambda_client, controller_instanceobj, context)
            print("Environment variables have been set.")
        except Exception as err:
            err_reason = "Failed to setup environment variables %s" % str(err)
            print(err_reason)
            return 'FAILED', err_reason

        if not verify_iam(controller_instanceobj):
            return 'FAILED', 'IAM role aviatrix-role-ec2 could not be verified to be attached to' \
                             ' controller'
        bucket_status, bucket_region = verify_bucket(controller_instanceobj)
        os.environ['S3_BUCKET_REGION'] = bucket_region
        update_env_dict(lambda_client, context, {"S3_BUCKET_REGION": bucket_region})
        if not bucket_status:
            return 'FAILED', 'Unable to verify S3 bucket'
        backup_file_status, backup_file = verify_backup_file(controller_instanceobj)
        if not backup_file_status:
            return 'FAILED', 'Cannot find backup file in the bucket'
        if not is_backup_file_is_recent(backup_file):
            return 'FAILED', f'Backup file is older than {MAXIMUM_BACKUP_AGE}'
        if not assign_eip(client, controller_instanceobj, None):
            return 'FAILED', 'Failed to associate EIP or EIP was not found.' \
                             ' Please attach an EIP to the controller before enabling HA'
        if not check_ami_id(controller_instanceobj['ImageId']):
            return 'FAILED', "AMI is not latest. Cannot enable Controller HA. Please backup" \
                             "/restore to the latest AMI before enabling controller HA"

        print("Verified AWS and controller Credentials and backup file, EIP and AMI ID")
        print("Trying to setup HA")
        try:
            ami_id = controller_instanceobj['ImageId']
            inst_id = controller_instanceobj['InstanceId']
            inst_type = controller_instanceobj['InstanceType']
            key_name = controller_instanceobj.get('KeyName', '')
            sgs = [sg_['GroupId'] for sg_ in controller_instanceobj['SecurityGroups']]
            setup_ha(ami_id, inst_type, inst_id, key_name, sgs, context)
        except Exception as err:
            response_status = 'FAILED'
            err_reason = "Failed to setup HA. %s" % str(err)
            print(err_reason)
    elif event['RequestType'] == 'Delete':
        try:
            print("Trying to delete lambda created resources")
            inst_id = controller_instanceobj['InstanceId']
            delete_resources(inst_id)
        except Exception as err:
            err_reason = "Failed to delete lambda created resources. %s" % str(err)
            print(err_reason)
            print("You'll have to manually delete Auto Scaling group,"
                  " Launch Configuration, and SNS topic, all with"
                  " name {}.".format(instance_name))
            response_status = 'FAILED'
    return response_status, err_reason
