## Aviatrix - AWS Quickstart script for CloudFormation

### Description
This CloudFormation script will create the following:

* One Aviatrix Controller EC2 Instance (named AviatrixController).
* One Aviatrix Security Group (named AviatrixSecurityGroup).
* One Aviatrix Role for EC2 (named aviatrix-role-ec2) with corresponding role policy (named aviatrix-assume-role-policy). [Click here for this policy details](https://s3-us-west-2.amazonaws.com/aviatrix-download/iam_assume_role_policy.txt)
* One Aviatrix Role for Lambda function (named aviatrix-role-app) with corresponding role policy (named aviatrix-app-policy) [Click here for this policy details](https://s3-us-west-2.amazonaws.com/aviatrix-download/IAM_access_policy_for_CloudN.txt)
* One Aviatrix Role for Lambda (named aviatrix-lambda-role)
> Quickstart lite:
>
If you only need to create the roles and policies, and plan to manually start the Aviatrix controller instance, use the Quickstart lite version. For lite version instructions click [here](./README-lite.md)

### Pre-requisites:

* An existing VPC.
* One or more public subnets on that VPC(These subnets will be used by AutoScaling Group to launch new controller instance).
* An internet gateway attached to the VPC.
* A keyPair.
* An Elastic IP with VPC scope
* In order to use the Aviatrix Controller first you need to accept the terms and subscribe to it in the AWS Marketplace.  Click [here](https://aws.amazon.com/marketplace/pp?sku=zemc6exdso42eps9ki88l9za)

> Note: this script does **NOT** check that the subnet selected is on the same VPC selected, you need to make sure you are selecting the right combination.

> Note 2: this script does **NOT** check that an Internet Gateway is created and attached to the VPC. If this is missing there will be no way to access the Aviatrix Controller.

### Step by step Procedure:

1. Download this repository as zip file, by clicking on top left green button named `Clone or download`, and then click on `Download ZIP`. 

2. Extract the downloaded zipped file on your local system. You will get a directory named `Controller-HA-for-AWS-master`. Go to that directory and zip file `aviatrix_ha.py` with name aviatrix_ha.zip.

3. Now create an S3 bucket named `aviatrix-lambda` from AWS console, and upload `aviatrix_ha.zip` there.

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

11. Click next

12. Especify your options/tags/permissions as per your policies, when in doubt just click next.

13. On the review page, scroll to the bottom and check the button that reads:
*I acknowledge that AWS CloudFormation might create IAM resources with custom names.*

14. Click on Create.

15. Verify that the instance, roles and policies has been created and associated accordingly.

16. Enjoy! You are welcomed!

### Caveats:

* There is no current automated way to check if the VPC/Subnet/IGW/Elastic IP are all in place and correctly configured. Manual creation of those elements is required.