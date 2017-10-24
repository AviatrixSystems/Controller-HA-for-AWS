## Aviatrix - AWS Cloudformation template for Aviatrix controller with HA

### Description
This CloudFormation script will create the following:

* An Aviatrix Autoscaling group with size 1, launching an EC2 Instance (named AviatrixController).
* An SNS topic named `AviatrixController`.
* A lambda function named `enable_ha`.
* An autoscaling group named `AviatrixController`.

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

1. Launch a controller using instructions available at https://github.com/AviatrixSystems/AWSQuickStart

2. Now login to controller, and create a new account of any name(for eg. backup) for backup purpose. Note account name and password down.

3. Create a new S3 bucket for backup. Go to Settings->Maintenance->Backup & Restore, and enable backup with account name created in previous step.

4. Go to AWS console, and select controller instance. Click Actions-> Image-> Create Image. Input Image name as `AviatrixController`. Leave other options to their default, and click `Create Image`. This newly created image will act as base image for all configuration restoration from now on.

5. Once `AviatrixController` image is created, download this repository as zip file, by clicking on top left green button named `Clone or download`, and then click on `Download ZIP`.

6. Extract the downloaded zipped file on your local system. You will get a directory named `Controller-HA-for-AWS-master`. Inside this directory, there will be a zipped file named `aviatrix_ha.zip`.

7. Upload `aviatrix_ha.zip` to S3 bucket created in prerequisite steps.

8. Access your AWS Console.

9. Under Services -> Management Tools.
```
 Select CloudFormation.
 ```
 OR
```
 Search for CloudFormation.
```

10. At the CloudFormation page, Select Create stack.

11. On the next screen, Select `Upload a template to Amazon S3`. Click on `Choose file`, and then select `aviatrix-aws-existing-controller-ha.json` from directory `Controller-HA-for-AWS-master` created in Step 2.

12. Click next.

13. On the Stack Name textbox, Name your Stack -> Something like *AviatrixHa*

14. Enter the parameters as per description. Click next.

15. Specify your options/tags/permissions as per your policies, when in doubt just click next.

16. On the review page, scroll to the bottom and check the button that reads:
*I acknowledge that AWS CloudFormation might create IAM resources with custom names.*

17. Click on Create.

18. Wait for status to change to `CREATE_COMPLETE`. If fails, debug or contact Riverbed support.

19. Enjoy! You are welcome!

### Caveats:

* There is no current automated way to check if the VPC/Subnet/IGW/Elastic IP are all in place and correctly configured. Manual creation of those elements is required.
