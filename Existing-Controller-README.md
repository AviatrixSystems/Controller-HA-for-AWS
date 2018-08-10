## Aviatrix - AWS CloudFormation template for HA on an Existing Aviatrix controller.

### Description
This guide assumes you already have an Aviatrix Controller running with configurations.

This CloudFormation script will create the following:

* An Aviatrix Autoscaling group with size 1.
* An SNS topic with same name as of existing controller instance.
* A lambda function for setting up HA and restoring configuration automatically.
* An Aviatrix Role for Lambda with corresponding role policy with required permissions.

This script is only supported for Aviatrix Controller version >= 3.4
### Pre-requisites:

* VPC of existing controller.
* Existing controller's VPC should have one or more public subnets, preferrably in different AZs for HA across AZ. 
* Existing controller version should be >= 3.4. if not, upgrade your controller to the latest
* Existing controller must have backup and restore enabled

### Step by step Procedure:

1. Make sure controller version is >= 3.4 ni Settings->Maintence->Upgrade. if not, upgrade your controller to the latest in Settings->Maintence->Upgrade

2. In the controller make sure that daily backup and restore is enabled in Settings->Maintence->Backup restore page

3. Do a "Backup Now" from  the Settings->Maintence->Backup restore page

4. Download this repository as zip file, by clicking on top right green button named `Clone or download`, and then click on `Download ZIP`.

5. Extract the downloaded zipped file on your local system. You will get a directory named `Controller-HA-for-AWS-master`. Inside this directory, there will be a zipped file named `aviatrix_ha.zip`.

6. Create an S3 bucket of any name(for eg. aviatrix_lambda). Upload `aviatrix_ha.zip` to this S3 bucket. Note down this bucket's name, this will be used later while setting up CloudFormation template.

7. Go to AWS Console-> Services -> Management Tools-> CloudFormation.

8. At the CloudFormation page, Select Create stack.

9. On the next screen, Select `Upload a template to Amazon S3`. Click on `Choose file`, and then select `aviatrix-aws-existing-controller-ha.json` from directory `Controller-HA-for-AWS-master` created in Step 5.

10. Click next.

11. On the Stack Name textbox, Name your Stack -> Something like `AviatrixHa`

12. Enter the parameters. Read carefully the descriptions and instructions. Click next.

13. Specify your options/tags/permissions as per your policies, when in doubt just click next.

14. On the review page, scroll to the bottom and check the button that reads:
`I acknowledge that AWS CloudFormation might create IAM resources with custom names.`

15. Click on Create.

16. Wait for status to change to `CREATE_COMPLETE`. If fails, debug or contact Aviatrix support.

17. Enjoy! You are welcome!
