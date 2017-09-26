## Aviatrix - AWS Cloudformation template for Aviatrix controller with HA

### Description
This CloudFormation script will create the following:

* An Aviatrix Autoscaling group with size 1, launching an EC2 Instance (named AviatrixController).
* An SNS topic named `AviatrixController`.
* An autoscaling group named `AviatrixController`.
* One Aviatrix Security Group (named AviatrixSecurityGroup).
* One Aviatrix Role for EC2 (named aviatrix-role-ec2) with corresponding role policy (named aviatrix-assume-role-policy). [Click here for this policy details](https://s3-us-west-2.amazonaws.com/aviatrix-download/iam_assume_role_policy.txt)
* One Aviatrix Role for Lambda function (named aviatrix-role-app) with corresponding role policy (named aviatrix-app-policy) [Click here for this policy details](https://s3-us-west-2.amazonaws.com/aviatrix-download/IAM_access_policy_for_CloudN.txt)
* One Aviatrix Role for Lambda (named aviatrix-role-lambda) with corresponding role policy (named AviatrixLambdaRolePolicy).

### Pre-requisites:

* An existing VPC.
* One or more public subnets on different Availability Zones on that VPC(These subnets will be used by AutoScaling Group to launch new controller instance, so make sure they are on different AZs to achieve HA across AZs.).
* An internet gateway attached to the VPC.
* A keyPair.
* An Elastic IP with VPC scope.
* Create an S3 bucket, and note its name down.
* In order to use the Aviatrix Controller first you need to accept the terms and subscribe to it in the AWS Marketplace.  Click [here](https://aws.amazon.com/marketplace/pp?sku=zemc6exdso42eps9ki88l9za)

> Note: this script does **NOT** check that the subnet selected is on the same VPC selected, you need to make sure you are selecting the right combination.

> Note 2: this script does **NOT** check that an Internet Gateway is created and attached to the VPC. If this is missing there will be no way to access the Aviatrix Controller.

> Note 2: this script does NOT check whether provided Elastic IP is available or not.

### Step by step Procedure:

1. Download this repository as zip file, by clicking on top left green button named `Clone or download`, and then click on `Download ZIP`. 

2. Extract the downloaded zipped file on your local system. You will get a directory named `Controller-HA-for-AWS-master`. Go to that directory and zip file `aviatrix_ha.py` with name aviatrix_ha.zip.

3. Now upload `aviatrix_ha.zip` to S3 bucket created in prerequisite steps.

4. Access your AWS Console.

5. Under Services -> Management Tools.
```
 Select CloudFormation.
 ```
 OR
```
 Search for CloudFormation.
```

6. At the CloudFormation page, Select Create stack.

7. On the next screen, Select `Upload a template to Amazon S3`. Click on `Choose file`, and then select `aviatrix-aws-quickstart-with-ha.json` from directory `Controller-HA-for-AWS-master` created in Step 2.

8. Click next.

9. On the Stack Name textbox, Name your Stack -> Something like *AviatrixController*

10. Select the following parameters:

  * VPC
  * Subnet
  * KeyPair Name
  * Elastic IP
  * S3 Bucket(enter name of S3 bucket created in prerequisite steps)

11. Click next

12. Specify your options/tags/permissions as per your policies, when in doubt just click next.

13. On the review page, scroll to the bottom and check the button that reads:
*I acknowledge that AWS CloudFormation might create IAM resources with custom names.*

14. Click on Create.

15. Verify that the instance, roles and policies has been created and associated accordingly.

16. Enjoy! You are welcomed!

### Caveats:

* There is no current automated way to check if the VPC/Subnet/IGW/Elastic IP are all in place and correctly configured. Manual creation of those elements is required.