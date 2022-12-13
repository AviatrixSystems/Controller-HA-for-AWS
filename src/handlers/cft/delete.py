import os

import boto3
import botocore

from errors.exceptions import AvxError


def delete_resources(inst_id, delete_sns=True, detach_instances=True):
    """ Cloud formation cleanup"""
    lt_name = lc_name = asg_name = os.environ.get('AVIATRIX_TAG')

    asg_client = boto3.client('autoscaling')
    if detach_instances:
        try:
            # in case customer manually changed the MinSize to greater than 0.
            asg_client.update_auto_scaling_group(
                AutoScalingGroupName=asg_name,
                MinSize=0)
            print("Updated asg MinSize to be 0 before detaching")
            asg_client.detach_instances(
                InstanceIds=[inst_id],
                AutoScalingGroupName=asg_name,
                ShouldDecrementDesiredCapacity=True)
            print("Controller instance detached from autoscaling group")
        except botocore.exceptions.ClientError as err:
            print(str(err))
    try:
        boto3.client('ec2').delete_launch_template(LaunchTemplateName=lt_name)
    except Exception as err:
        print(str(err))

    try:
        asg_client.delete_auto_scaling_group(AutoScalingGroupName=asg_name,
                                             ForceDelete=True)
    except botocore.exceptions.ClientError as err:
        if "AutoScalingGroup name not found" in str(err):
            print('ASG already deleted')
        else:
            raise AvxError(str(err)) from err
    print("Autoscaling group deleted")
    try:
        asg_client.delete_launch_configuration(LaunchConfigurationName=lc_name)
    except botocore.exceptions.ClientError as err:
        if "Launch configuration name not found" in str(err):
            print('LC already deleted')
        else:
            print(str(err))
    print("Launch configuration deleted")
    if delete_sns:
        print("Deleting SNS topic")
        sns_client = boto3.client('sns')
        topic_arn = os.environ.get('TOPIC_ARN')
        if topic_arn == "N/A" or not topic_arn:
            print("Topic not created. Exiting")
            return
        try:
            response = sns_client.list_subscriptions_by_topic(TopicArn=topic_arn)
        except botocore.exceptions.ClientError as err:
            print('Could not delete topic due to %s' % str(err))
        else:
            for subscription in response.get('Subscriptions', []):
                try:
                    sns_client.unsubscribe(SubscriptionArn=subscription.get('SubscriptionArn', ''))
                except botocore.exceptions.ClientError as err:
                    print(str(err))
            print("Deleted subscriptions")
        try:
            sns_client.delete_topic(TopicArn=topic_arn)
        except botocore.exceptions.ClientError as err:
            print('Could not delete topic due to %s' % str(err))
        else:
            print("SNS topic deleted")
