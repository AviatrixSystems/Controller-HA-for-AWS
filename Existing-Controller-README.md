## Aviatrix - AWS CloudFormation template for HA on an Existing Aviatrix controller.

### Description
This guide assumes you already have an Aviatrix Controller running with configurations.

This CloudFormation script will create the following:

* An Aviatrix Autoscaling group with size 1..
* An SNS topic with the same name as a controller AMI image name created in the instructions below. For example,  `AviatrixController`.
* A lambda function named `enable_ha`.
* An autoscaling group with the same as the SNS topic. For example, `AviatrixController`.
* One Aviatrix Role for Lambda (named aviatrix-role-lambda) with corresponding role policy (named AviatrixLambdaRolePolicy).

### Pre-requisites:

* VPC of existing controller.
* Existing controller should have Name tag `AviatrixController`.
* Existing controller's VPC should have one or more public subnets, preferrably in different AZs for HA across AZ.

### Step by step Procedure:

1. Prepare a AMI base image for auto scaling group. 
   * Launch a new Controller in the same VPC as the existing controller using CloudFormation script available at https://github.com/AviatrixSystems/AWSQuickStart. Since this new controller is used to build AMI for AWS auto scaling group, select `aviatrix-role-ec2` for IAMRole parameter to indicate IAM roles and policies have already been created when the existing controller was launched.  

   * Now login to the new controller, go through the initial bootup sequence to change the admin's password and re-login. Note down the admin password. Go to your existing controller, [enable backup function](http://docs.aviatrix.com/HowTos/controller_backup.html) to a S3 bucket if you have not already done so. Note currently the script only accpets access key and secret ID to access this S3 bucket, you may need to go to AWS console to create an access key and secret ID to access this S3 bucket. This credential will be used for restore configuration on an controller launched by auto scaling group. 

   * Go to AWS EC2 console, and select new controller instance. `Make sure you select the new controller as it has the same name as the existing controller`. Click Actions-> Image-> Create Image. Input an Image name. For example, name this new AMI as `AviatrixController`. Leave other options to their default, and click `Create Image`. This newly created image will act as base image for auto scaling group to launch a new controller to restore for all configuration from now on. 

4. Once image is created, go ahead delete this new CloudFormation stack .

5. Download this repository as zip file, by clicking on top right green button named `Clone or download`, and then click on `Download ZIP`.

6. Extract the downloaded zipped file on your local system. You will get a directory named `Controller-HA-for-AWS-master`. Inside this directory, there will be a zipped file named `aviatrix_ha.zip`.

7. Create an S3 bucket of any name(for eg. aviatrix_lambda). Note down this bucket's name, this will be used later. Upload `aviatrix_ha.zip` to this S3 bucket.

8. Go to AWS Console-> Services -> Management Tools-> CloudFormation.

10. At the CloudFormation page, Select Create stack.

11. On the next screen, Select `Upload a template to Amazon S3`. Click on `Choose file`, and then select `aviatrix-aws-existing-controller-ha.json` from directory `Controller-HA-for-AWS-master` created in Step 2.

12. Click next.

13. On the Stack Name textbox, Name your Stack -> Something like *AviatrixHa*

14. Enter the parameters. Read carefully the descriptions and instructions. Click next.

15. Specify your options/tags/permissions as per your policies, when in doubt just click next.

16. On the review page, scroll to the bottom and check the button that reads:
*I acknowledge that AWS CloudFormation might create IAM resources with custom names.*

17. Click on Create.

18. Wait for status to change to `CREATE_COMPLETE`. If fails, debug or contact Aviatrix support.

19. Enjoy! You are welcome!
