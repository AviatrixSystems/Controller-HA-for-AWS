""" CSP APis related to instances"""
import botocore


def get_controller_instance(ec2_client, instance_name, inst_id):
    """ Find the controller instance based on name or id"""
    controller_instanceobj = None
    describe_err = None
    try:
        try:
            controller_instanceobj = ec2_client.describe_instances(
                Filters=[
                    {'Name': 'instance-state-name', 'Values': ['running']},
                    {'Name': 'tag:Name', 'Values': [instance_name]}]
            )['Reservations'][0]['Instances'][0]
        except IndexError:
            if inst_id:
                print("Can't find Controller instance with name tag %s, "
                      "trying with inst id %s" % (instance_name, inst_id))
                controller_instanceobj = ec2_client.describe_instances(
                    InstanceIds=[inst_id])['Reservations'][0]['Instances'][0]
            else:
                raise
    except Exception as err:
        inst_id_err = " or inst id %s" % inst_id if inst_id else ""
        describe_err = "Can't find Controller instance with name tag %s%s. %s" % (
            instance_name, inst_id_err, str(err))
        print(describe_err)
    return describe_err, controller_instanceobj


def enable_t2_unlimited(client, inst_id):
    """ Modify instance credit to unlimited for T2 """
    print("Enabling T2 unlimited for %s" % inst_id)
    try:
        client.modify_instance_credit_specification(ClientToken=inst_id,
                                                    InstanceCreditSpecifications=[{
                                                        'InstanceId': inst_id,
                                                        'CpuCredits': 'unlimited'}])
    except botocore.exceptions.ClientError as err:
        print(str(err))
