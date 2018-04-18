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

1. Launch a controller using instructions available at https://s3-us-west-2.amazonaws.com/aviatrix-cloudformation-templates/avx-awsmp-BYOL.template

2. Find the VPC in which controller instance has launched. Go to that VPC from AWS console, and create one or more public subnets preferrably in different AZs for HA across AZ.

2. Now login to controller, and create a new account of any name(for eg. backup) for backup purpose. Note account name and password down.

3. Create a new S3 bucket for backup. Go to Settings->Maintenance->Backup & Restore, and enable backup with account name created in previous step.

4. Go to AWS EC2 console, and select controller instance. Click Actions-> Image-> Create Image. Input Image name as `AviatrixController`. Leave other options to their default, and click `Create Image`. This newly created image will act as base image for all configuration restoration from now on.

5. Once `AviatrixController` image is created, download this repository as zip file, by clicking on top right green button named `Clone or download`, and then click on `Download ZIP`.

6. Extract the downloaded zipped file on your local system. You will get a directory named `Controller-HA-for-AWS-master`. Inside this directory, there will be a zipped file named `aviatrix_ha.zip`.

7. Create an S3 bucket of nay name(for eg. aviatrix_lambda). Note down this bucket's name, this will be used later. Upload `aviatrix_ha.zip` to this S3 bucket.

8. Go to AWS Console-> Services -> Management Tools-> CloudFormation.

10. On CloudFormation page, Select Create stack.

11. On the next screen, Select `Upload a template to Amazon S3`. Click on `Choose file`, and then select `aviatrix-aws-existing-controller-ha.json` from directory `Controller-HA-for-AWS-master` created in Step 2.

12. Click next.

13. On the Stack Name textbox, Name your Stack -> Something like *AviatrixHa*

14. Enter the parameters as per description. Click next.

15. Specify your options/tags/permissions as per your policies, when in doubt just click next.

16. On the review page, scroll to the bottom and check the button that reads:
*I acknowledge that AWS CloudFormation might create IAM resources with custom names.*

17. Click on Create.

18. Wait for status to change to `CREATE_COMPLETE`. If fails, debug or contact Aviatrix support.

19. Enjoy! You are welcome!

### Caveats:

* There is no current automated way to check if the VPC/Subnet/IGW/Elastic IP are all in place and correctly configured. Manual creation of those elements is required.
