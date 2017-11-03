## Aviatrix - AWS CloudFormation template for HA on an Existing Aviatrix controller.

### Description
This CloudFormation script will create the following:

* An Aviatrix Autoscaling group with size 1..
* An SNS topic named `AviatrixController`.
* A lambda function named `enable_ha`.
* An autoscaling group named `AviatrixController`.
* One Aviatrix Role for Lambda (named aviatrix-role-lambda) with corresponding role policy (named AviatrixLambdaRolePolicy).

### Pre-requisites:

* VPC of existing controller.
* Existing controller should have Name tag `AviatrixController`.
* Existing controller's VPC should have one or more public subnets, preferrably in different AZs for HA across AZ.

### Step by step Procedure:

1. Launch a new Controller using CloudFormation script available at https://github.com/AviatrixSystems/AWSQuickStart. Since this new controller is used to build AMI, for IAMRole parameter, select "aviatrix-role-ec2" to indicate IAM roles and policies have already been created.  

2. Now login to the new controller, and create a new account of any name(for eg. backup) for backup purpose. Note account name and password down. Go to your existing controller, and setup new account with same name and password. Then setup backup on your existing controller with this account.

3. Go to AWS EC2 console, and select new controller instance. Click Actions-> Image-> Create Image. Input Image name as `AviatrixController`. Leave other options to their default, and click `Create Image`. This newly created image will act as base image for all configuration restoration from now on. 

4. Once image is created, go ahead and terminate new controller instance from AWS console.

5. Download this repository as zip file, by clicking on top right green button named `Clone or download`, and then click on `Download ZIP`.

6. Extract the downloaded zipped file on your local system. You will get a directory named `Controller-HA-for-AWS-master`. Inside this directory, there will be a zipped file named `aviatrix_ha.zip`.

7. Create an S3 bucket of nay name(for eg. aviatrix_lambda). Note down this bucket's name, this will be used later. Upload `aviatrix_ha.zip` to this S3 bucket.

8. Go to AWS Console-> Services -> Management Tools-> CloudFormation.

10. At the CloudFormation page, Select Create stack.

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
