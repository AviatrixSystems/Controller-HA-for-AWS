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

1. Download aviatrix_ha.py. Zip it with name aviatrix_ha.zip. Create an S3 bucket named aviatrix-lambda and  upload aviatrix_ha.zip there. (Upload this zip file on our S3, so that customers can directly download and upload on their S3??)

2. Access your AWS Console.

3. Under Services -> Management Tools.
```
 Select CloudFormation.
 ```
 OR
```
 Search for CloudFormation.
```

4. At the CloudFormation page, Select Create stack.

5. On the next screen, Select "Upload a template to Amazon S3".
```
  Choose file -> aviatrix-aws-quickstart.json
```

  > Note: the [aviatrix-aws-quickstart.json file](https://github.com/AviatrixSystems/Controller-HA-for-AWS/blob/master/aviatrix-aws-quickstart-with-ha.json) can be found in this project, click [here](https://raw.githubusercontent.com/AviatrixSystems/Controller-HA-for-AWS/master/aviatrix-aws-quickstart-with-ha.json)   for direct download.

6. Click next.

7. On the Stack Name textbox, Name your Stack -> Something like *AviatrixController*

8. Select the following parameters:

  * VPC
  * Subnet
  * KeyPair Name
  * Elastic IP

9. Click next

10. Especify your options/tags/permissions as per your policies, when in doubt just click next.

11. On the review page, scroll to the bottom and check the button that reads:
*I acknowledge that AWS CloudFormation might create IAM resources with custom names.*

12. Click on Create.

13. Verify that the instance, roles and policies has been created and associated accordingly.

14. Enjoy! You are welcomed!

### Caveats:

* There is no current automated way to check if the VPC/Subnet/IGW/Elastic IP are all in place and correctly configured. Manual creation of those elements is required.