""" Test Module to test restore functionality"""
import os
import argparse
import aviatrix_ha
HA_TAG = 'ha_ctrl'
os.environ["TESTPY"] = "True"
os.environ["AWS_TEST_REGION"] = "us-west-2"

os.environ["AVIATRIX_PASS_BACK"] = "Oldbkuppwd"
os.environ["AVIATRIX_TAG"] = HA_TAG
os.environ["AVIATRIX_USER_BACK"] = "admin"
os.environ["AWS_ACCESS_KEY_BACK"] = "access_key"
os.environ["AWS_SECRET_KEY_BACK"] = "secret_key"
os.environ["EIP"] = "54.2.2.4"  # New controller IP
os.environ["PRIV_IP"] = "172.31.45.188"  # Older private IP
os.environ["S3_BUCKET_BACK"] = "backrestorebucketname"
os.environ["SUBNETLIST"] = "subnet-497e8as511,subnet-87ase3,subnet-aasd6a0ef"

CONTEXT = argparse.Namespace()
TESTCASE = 4    # Choose 1 to 6 based on the message
CONTEXT.function_name = HA_TAG + "-ha"
EVENT_LIST = [
    {"StackId": "sdfsdf", 'RequestType': 'Create'},   # 1.Cloudformation launch
    {"Records": [{"EventSource": "aws:sns",           # 2 ASG Event lambda init
                  "Sns": {"Message": '{Event": "autoscaling:EC2_INSTANCE_LAUNCH"}'}}]},
    {"Records": [{"EventSource": "aws:sns",           # 3 ASG Event lambda test
                  "Sns": {"Message": '{Event": "autoscaling:TEST_NOTIFICATION"}'}}]},
    {"Records": [{"EventSource": "aws:sns",           # 4. ASG HA Instance Launch
                  "Sns": {"Message": '{Event": "autoscaling:EC2_INSTANCE_LAUNCH"}'}}]},
    {"StackId": "sdfsdf", 'RequestType': 'Delete'},   # 5 Cloudformation delete
    {"Records": [{"EventSource": "aws:sns",           # 6. ASG HA Instance Launch Fail Sec group
                  "Sns": {"Message": '{"Event": "autoscaling:EC2_INSTANCE_LAUNCH_ERROR",'
                                     '"Description": "The security group does not exist in VPC"}'}}]
    }
]
EVENT = EVENT_LIST[TESTCASE - 1]
aviatrix_ha.lambda_handler(EVENT, CONTEXT)

""" All message examples
# MESSAGE 1: Cloudformation launch
{u'StackId': u'arn:aws:cloudformation:us-west-2:09420***',
 u'ResponseURL': u'https://cloudformation-custom-resource-response***',
 u'ResourceProperties': {u'ServiceToken': u'arn:aws:la***function:ha_ctrl-ha'},
 u'RequestType': u'Create', u'ServiceToken': u'arn:aws:l***function:ha_ctrl-ha',
 u'ResourceType': u'Custom::SetupHA',
 u'RequestId': u'6c5486f4-bd67-4fcc-919a-bee7351c5d0c',
 u'LogicalResourceId': u'SetupHA'}

# MESSAGE 2: Attach to ASG HA event (Will be ignored due to incorrect password, no way to detect)
{u'Records': [
    {u'EventVersion': u'1.0',
     u'EventSubscriptionArn': u'arn:aws:sns:us-sdfsdf***',
     u'EventSource': u'aws:sns',
     u'Sns': {
         u'SignatureVersion': u'1',
         u'Timestamp': u'2018-07-11T00:29:38.704Z',
         u'Signature': u'5HBNtODGJzdKejn7eN/DucvVS***',
         u'SigningCertUrl': u'https://sns.us-west-2.amazos',
         u'MessageId': u'b5235c90-8ae6-5e09-8ec5-sdf',
         u'Message': {
             "Progress": 50,
             "AccountId": "09420830sadfaqwe",
             "Description": "Attaching an existing EC2 instance: i-02c7e76sadf3***",
             "RequestId": "8055921a-f932-7ec1-1a55-6dasdf4",
             "EndTime": "2018-07-11T00:29:38.655Z",
             "AutoScalingGroupARN": "arn:aws:autoscaling***ha_ctrl",
             "ActivityId": "8055921a-f932-7ec1-1a55-6d0asdf",
             "StartTime": "2018-07-11T00:29:35.775Z",
             "Service": "AWS Auto Scaling",
             "Time": "2018-07-11T00:29:38.655Z",
             "EC2InstanceId": "i-02c7e766bb2fasdf",
             "StatusCode": "InProgress",
             "StatusMessage": "",
             "Details": {"Availability Zone": "us-west-2b"},
             "AutoScalingGroupName": "ha_ctrl",
             "Cause": "At 2018-07-11T00:29:35Z an instance was added in response to user request."
                      " Keeping the capacity at the new 1.",
             "Event": "autoscaling:EC2_INSTANCE_LAUNCH"},
         u'MessageAttributes': {},
         u'Type': u'Notification',
         u'UnsubscribeUrl': u'****',
         u'TopicArn': u'arn:aws:sns:us-west-2:094208adf:ha_ctrl',
         u'Subject': u'Auto Scaling: launch for group "ha_ctrl"'
     }}]}

# MESSAGE 3: Test message from ASG (Will be ignored)
{u'Records': [{
    u'EventVersion': u'1.0',
    u'EventSubscriptionArn': u'arn:aws:sns:us-west-2:0942sdf3asdfasdf:ha****',
    u'EventSource': u'aws:sns',
    u'Sns': {
        u'SignatureVersion': u'1',
        u'Timestamp': u'2018-07-11T00:29:37.017Z',
        u'Signature': u'YRdc1g****XdfyyN2dZAodzQ6=',
        u'SigningCertUrl': u'https://****m',
        u'MessageId': u'43c55a35-2f83-5a1b-8f02-098asdff8',
        u'Message': {
            "AccountId": "0942083asdfas",
            "RequestId": "7daf9553-84a1-11e8-bc02-b1a9e72fca9d",
            "AutoScalingGroupARN": "arn:aws:autosZZZ***ha_ctrl",
            "AutoScalingGroupName": "ha_ctrl",
            "Service": "AWS Auto Scaling",
            "Event": "autoscaling:TEST_NOTIFICATION",
            "Time": "2018-07-11T00:29:36.940Z"},
        U'MessageAttributes': {},
        u'Type': u'Notification',
        u'UnsubscribeUrl': u'https://snASDFASD****',
        u'TopicArn': u'arn:aws:sns:us-west-2:***:ha_ctrl',
        u'Subject': u'Auto Scaling: test notification for group "ha_ctrl"'
    }}]}

# MESSAGE 4: HA event from ASG
{u'Records': [{
    u'EventVersion': u'1.0',
    u'EventSubscriptionArn': u'arn:aws:sns:us-west***',
    u'EventSource': u'aws:sns',
    u'Sns': {
        u'SignatureVersion': u'1',
        u'Timestamp': u'2018-07-11T00:29:38.704Z',
        u'Signature': u'****3DOHkd9MIbbHpDX5HBNtODGJ**',
        u'SigningCertUrl': u'https://**',
        u'MessageId': u'b5235c90-8ae6-5e09-8ec5-***',
        u'Message': {
            "Progress": 50,
            "AccountId": "094208*****",
            "Description": "Attaching an existing EC2 instance: i-***",
            "RequestId": "8055921a-f932-7ec1-1a55-***",
            "EndTime": "2018-07-11T00:29:38.655Z",
            "AutoScalingGroupARN": "arn:aws:autoscaliZ******/ha_ctrl",
            "ActivityId": "8055921a-f932-7ec1-1a55-***",
            "StartTime": "2018-07-11T00:29:35.775Z",
            "Service": "AWS Auto Scaling",
            "Time": "2018-07-11T00:29:38.655Z",
            "EC2InstanceId": "i-02c7e766bb2f36***d",
            "StatusCode": "InProgress",
            "StatusMessage": "",
            "Details": {"Availability Zone": "us-west-2b"},
            "AutoScalingGroupName": "ha_ctrl",
            "Cause": "At 2018-07-11T00:29:35Z an instance was added in response to user request."
                     " Keeping the capacity at the new 1.",
            "Event": "autoscaling:EC2_INSTANCE_LAUNCH"},
        u'MessageAttributes': {},
        u'Type': u'Notification',
        u'UnsubscribeUrl': u'htt******',
        u'TopicArn': u'arn:aws:sns:us-west-2:***:ha_ctrl',
        u'Subject': u'Auto Scaling: launch for group "ha_ctrl"'
    }}]}


# MESSAGE 5: CFT Delete
{u'StackId': u'arn:aws:cloudformation***',
 u'ResponseURL': u'https://clou***D',
 u'ResourceProperties': {
     u'ServiceToken': u'arn:aws:lambda:us-west-2:094208*****:function:ha_ctrl-ha'},
 u'RequestType': u'Delete',
 u'ServiceToken': u'arn:aws:lambda:us-west-2:094208*****:function:ha_ctrl-ha',
 u'ResourceType': u'Custom::SetupHA',
 u'PhysicalResourceId': u'2018/07/11/[$LATEST]163c82a474f142d28a45d404d56c849d',
 u'RequestId': u'1ffc6b70-2264-4f07-a29c-a8bef1b273e6',
 u'LogicalResourceId': u'SetupHA'}


# MESSAGE 6: Instance launch failure
{u'Records': [{
    u'EventVersion': u'1.0',
    u'EventSubscriptionArn': u'arn:aw***',
    u'EventSource': u'aws:sns',
    u'Sns': {
        u'SignatureVersion': u'1',
        u'Timestamp': u'2018-07-11T23:14:38.564Z',
        u'Signature': u'iTME2+k+kl/rsiGceDvB6JK+kl/xCgfpFGNuEFlOR1nCQ+bwmRE/kl+gaeRg==',
        u'SigningCertUrl': u'https://sns.us-west-2.amazonaws.com/l-kl;.pem',
        u'MessageId': u'73c91909-27cd-5b5a-a2a6-4ac9b6535609',
        u'Message': {
            "Progress": 100,
            "AccountId": "094208*****",
            "Description": "Launching a new EC2 instance. Status Reason: The security group"
                           " \'sg-3d7bcc4d\' does not exist in VPC \'vpc-be5433da\'. Launching"
                           " EC2 instance failed.",
            "RequestId": "c865922e-8021-d8b1-f890-023a682b2abf",
            "EndTime": "2018-07-11T23:14:38.000Z",
            "AutoScalingGroupARN": "arn:aws:autoscal****oupName/ha_ctrl",
            "ActivityId": "c865922e-8021-d8b1-f890-023a682b2abf",
            "StartTime": "2018-07-11T23:14:38.326Z",
            "Service": "AWS Auto Scaling",
            "Time": "2018-07-11T23:14:38.491Z",
            "EC2InstanceId": "",
            "StatusCode": "Failed",
            "StatusMessage": "The security group \'sg-3d7bcc4d\' does not exist in VPC "
                             "\'vpc-be5433da\'. Launching EC2 instance failed.",
            "Details": {"Subnet ID": "subnet-497e8511","Availability Zone": "us-west-2c"},
            "AutoScalingGroupName": "ha_ctrl",
            "Cause": "AASDASDASD.",
            "Event": "autoscaling:EC2_INSTANCE_LAUNCH_ERROR"},
        u'MessageAttributes': {},
        u'Type': u'Notification',
        u'UnsubscribeUrl': u'https://sns.u****',
        u'TopicArn': u'arn:aws:sns:us-west-2:094208*****:ha_ctrl',
        u'Subject': u'Auto Scaling: failed launch for group "ha_ctrl"'
    }}]}"""
