from __future__ import print_function

import boto3
import re
import json
import datetime
import time
import os

print('Loading function')

INSTANCE_TAG = 'AviatrixController'
AMI_NAME = 'AviatrixController'
LC_NAME = 'AviatrixController'
ASG_NAME = 'AviatrixController'
SNS_TOPIC = 'AviatrixController'

def lambda_handler(event, context):
	client = boto3.client('ec2')
	controller_instanceobj = client.describe_instances(Filters=[{'Name': 'instance-state-name', 'Values': ['running']},
						{'Name': 'tag:Name','Values': [INSTANCE_TAG]}])['Reservations'][0]['Instances'][0]

	try:
		scheduled_event = event.get("detail-type") == "Scheduled Event"
	except:
		pass
	try:
		sns_event = event.get("Records")[0].get("EventSource") == "aws:sns"
	except:
		pass

	if scheduled_event:        
		duplicate_ami(client, controller_instanceobj, context)
	else if sns_event:
		assign_eip(client, controller_instanceobj)

def assign_eip(client, controller_instanceobj):
	try:
		EIP = os.environ['EIP']
	except:
		pass
	else:
		return
	eip_alloc_id = client.describe_addresses(PublicIps=[EIP]).get('Addresses')[0].get('AllocationId')
	client.associate_address(AllocationId=eip_alloc_id,
									 InstanceId=controller_instanceobj['InstanceId'])

def duplicate_ami(client, controller_instanceobj, context):
	delete_image_n_snapshot(client)
	new_ami = register_new_image(client, controller_instanceobj, context)
	#new_ami = 'ami-ab5315c4'
	update_autoscaling_conf(new_ami, controller_instanceobj, context)

def delete_image_n_snapshot(client):
	try:
		old_image = client.describe_images(
			Filters=[{'Name': 'name','Values': [AMI_NAME]}],Owners=['self'])['Images'][0]['ImageId']
	except:
		print("No older backup AMI found")
		return
	if old_image:
		client.deregister_image(ImageId=old_image)
		for snapshot in client.describe_snapshots(OwnerIds=['self'])['Snapshots']:
			if re.match(r".*for ({0}) from.*".format(old_image), snapshot['Description']):
				client.delete_snapshot(SnapshotId=snapshot['SnapshotId'])

def register_new_image(client, controller_instanceobj, context):
	print("REgistering new image.")
	# Register new AMI from Aviatrix controller instance.
	if controller_instanceobj['NetworkInterfaces'][0]['Association']['IpOwnerId'] != 'amazon':
		EIP = controller_instanceobj['NetworkInterfaces'][0]['Association']['PublicIp']
		print(EIP)
		lambda_client = boto3.client('lambda')
		lambda_client.update_function_configuration(FunctionName=context.function_name,
													Environment={'Variables': {'EIP': EIP, 
													'SUBNET_LIST': os.environ['SUBNET_LIST']}})

	image = client.create_image(
		InstanceId=controller_instanceobj['InstanceId'],
		Description='Aviatrix controller backup AMI created from active ec2 instance',
		Name=AMI_NAME,
		NoReboot=True
	)
	return image['ImageId']

def update_autoscaling_conf(new_ami, controller_instanceobj, context):
	asg_client = boto3.client('autoscaling')
	timeStamp = time.time()
	timeStampString = datetime.datetime.fromtimestamp(timeStamp).strftime('%Y-%m-%d  %H-%M-%S')
	newLaunchConfigName = LC_NAME+timeStampString
	asg_client.create_launch_configuration(
			InstanceId = controller_instanceobj['InstanceId'],
			LaunchConfigurationName=newLaunchConfigName,
			ImageId= new_ami)
	asg = asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=[ASG_NAME]).get('AutoScalingGroups')
	if not asg:
		create_autoscaling_conf(asg_client, controller_instanceobj, newLaunchConfigName, context)
		return
	old_lc = asg[0]['LaunchConfigurationName']
	print(old_lc)
	response = asg_client.update_auto_scaling_group(AutoScalingGroupName = ASG_NAME,
			LaunchConfigurationName = newLaunchConfigName)
	#Delete old launch configuration
	asg_client.delete_launch_configuration(LaunchConfigurationName=old_lc)
	print('Updated ASG')

def create_autoscaling_conf(asg_client, controller_instanceobj, newLaunchConfigName, context):
	asg_client.create_auto_scaling_group(AutoScalingGroupName = ASG_NAME,
			LaunchConfigurationName=newLaunchConfigName,
			MinSize=0,
			MaxSize=1,
			VPCZoneIdentifier=os.environ['SUBNET_LIST'],
			Tags=[{'Key': 'Name','Value': ASG_NAME, 'PropagateAtLaunch': True}]
		)
	print('Created ASG')
	asg_client.attach_instances(InstanceIds=[controller_instanceobj['InstanceId']], AutoScalingGroupName=ASG_NAME)
	sns_client = boto3.client('sns')
	sns_topic_arn = sns_client.create_topic(Name=SNS_TOPIC).get('TopicArn')
	lambda_client = boto3.client('lambda')
	lambda_fn_arn = lambda_client.get_function(FunctionName=context.function_name).get('Configuration').get('FunctionArn')
	sub_arn = sns_client.subscribe(TopicArn=sns_topic_arn,Protocol='lambda',Endpoint=lambda_fn_arn).get('SubscriptionArn')

	response = asg_client.put_notification_configuration(AutoScalingGroupName=ASG_NAME,
					NotificationTypes=['autoscaling:EC2_INSTANCE_LAUNCH'],
					TopicARN=sns_topic_arn)
	print('Attached ASG')
