## Aviatrix - AWS Cloudformation template for New Aviatrix controller with HA

### Description

This guide helps you enable controller HA in AWS when launch a **New** Aviatrix Controller. If you already have an existing Controller running and would like to enable HA, refer to [Existing-Controller-README.md](https://github.com/AviatrixSystems/Controller-HA-for-AWS/blob/master/Existing-Controller-README.md)

This CloudFormation script will create the following:

* An Aviatrix Autoscaling group with size 1, launching an EC2 Instance (named AviatrixController).
* An SNS topic named `AviatrixController`.
* A lambda function named `enable_ha`.
* An autoscaling group named `AviatrixController`.
* One Aviatrix Role for Lambda (named aviatrix-role-lambda) with corresponding role policy (named AviatrixLambdaRolePolicy).

### Step by step Procedure:

1. Launch a controller using instructions available at https://github.com/AviatrixSystems/AWSQuickStart

2. Find the VPC in which controller instance has launched. Go to that VPC from AWS console, and create one or more public subnets preferrably in different AZs for HA across AZ.

2. Now login to controller, and create a new account of any name(for eg. backup) for backup purpose. Note account name and password down.

3. Create a new S3 bucket for backup. Go to Settings->Maintenance->Backup & Restore, and enable backup with account name created in previous step.

4. Once the backup image is complete, download this repository as zip file, by clicking on top right green button named `Clone or download`, and then click on `Download ZIP`.

5. Extract the downloaded zipped file on your local system. You will get a directory named `Controller-HA-for-AWS-master`. Inside this directory, there will be a zipped file named `aviatrix_ha.zip`.

6. Create an S3 bucket of nay name(for eg. aviatrix_lambda). Note down this bucket's name, this will be used later. Upload `aviatrix_ha.zip` to this S3 bucket.

7. Go to AWS Console-> Services -> Management Tools-> CloudFormation.

8. On CloudFormation page, Select Create stack.

9. On the next screen, Select `Upload a template to Amazon S3`. Click on `Choose file`, and then select `aviatrix-aws-existing-controller-ha.json` from directory `Controller-HA-for-AWS-master` created in Step 2.

10. Click next.

11. On the Stack Name textbox, Name your Stack -> Something like *AviatrixHa*

12. Enter the parameters as per description. Click next.

13. Specify your options/tags/permissions as per your policies, when in doubt just click next.

14. On the review page, scroll to the bottom and check the button that reads:
*I acknowledge that AWS CloudFormation might create IAM resources with custom names.*

15. Click on Create.

16. Wait for status to change to `CREATE_COMPLETE`. If fails, debug or contact Aviatrix support.

17. Enjoy! You are welcome!

### Caveats:

* There is no current automated way to check if the VPC/Subnet/IGW/Elastic IP are all in place and correctly configured. Manual creation of those elements is required.
