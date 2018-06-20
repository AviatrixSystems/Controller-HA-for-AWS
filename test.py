import os
import argparse
import aviatrix_ha
os.environ["TESTPY"] = "True"
os.environ["AWS_TEST_REGION"] = "us-west-2"

os.environ["AVIATRIX_PASS_BACK"] = "Oldbkuppwd"
os.environ["AVIATRIX_TAG"] = "ctrlhami"
os.environ["AVIATRIX_USER_BACK"] = "admin"
os.environ["AWS_ACCESS_KEY_BACK"] = "access_key"
os.environ["AWS_SECRET_KEY_BACK"] = "secret_key"
os.environ["EIP"] = "4.6.6.169"
os.environ["EIP"] = "54.2.2.4"  # New controller IP

os.environ["PRIV_IP"] = "172.31.45.188"  # Older private IP
os.environ["S3_BUCKET_BACK"] = "backrestorebucketname"
os.environ["SUBNETLIST"] = "subnet-497e8as511,subnet-87ase3,subnet-aasd6a0ef"

context = argparse.Namespace()
context.function_name = "ctrlhami-ha"
event = {"Records": [{"EventSource": "aws:sns"}]}
aviatrix_ha.lambda_handler(event, context)
