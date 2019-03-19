## Aviatrix - AWS CloudFormation template for HA on an Existing Aviatrix controller.

### Description
This guide assumes you already have an Aviatrix Controller running and has been configured. If you don't, launch a controller through instructions available at [Aviatrix Controller Startup Guide](https://docs.aviatrix.com/StartUpGuides/aviatrix-cloud-controller-startup-guide.html)

This CloudFormation script will create the following:

* An Aviatrix Autoscaling group with size 1 with a new security group
* An SNS topic with same name as of existing controller instance.
* An email subscription to the SNS topic(optional)
* A lambda function for setting up HA and restoring configuration automatically.
* An Aviatrix Role for Lambda with corresponding role policy with required permissions.

This script is only supported for Aviatrix Controller version >= 3.4
### Pre-requisites:

* VPC of existing controller.
* Existing controller's VPC should have one or more public subnets, preferrably in different AZs for HA across AZ. 
* Existing controller version should be >= 3.4. if not, upgrade your controller to the latest
* Existing controller must have backup and restore enabled
* Existing controller must have at least AMI ID aviatrix_cloud_services_gateway_043018_BYOL-xxxxxx. If you are on an older AMI ID, please refer [here](https://docs.aviatrix.com/HowTos/Migration_From_Marketplace.html) to migrate to the latest controller AMI ID first.
* S3 bucket(s) to host the Lambda script and for the backup restore functionality

### Step by step Procedure:

1. Make sure that controller version is >= 3.4 in Settings->Maintenance->Upgrade. if not, upgrade your controller to the latest by clicking on "Upgrade" in Settings->Maintence->Upgrade

2. In the controller, make sure that daily backup and restore is enabled in Settings->Maintenance->Backup restore page

3. Do a "Backup Now" from  the Settings->Maintenance->Backup restore page

4. You can launch the cloud formation directly from [here](https://console.aws.amazon.com/cloudformation/home#/stacks/new?stackName=AviatrixHA&templateURL=https://s3-us-west-2.amazonaws.com/aviatrix-cloudformation-templates/aviatrix-aws-existing-controller-ha-acc-sec.json) 

5. On the Stack Name textbox, Name your Stack -> Something like `AviatrixHA`

6. Enter the parameters. Read the descriptions and instructions carefully. Click next.

7. Specify your options/tags/permissions as per your policies, when in doubt just click next.

8. On the review page, scroll to the bottom and check the button that reads:
`I acknowledge that AWS CloudFormation might create IAM resources with custom names.`

9. Click on Create.

10. Wait for status to change to `CREATE_COMPLETE`. If fails or rolls back, you can see the error message in the Cloudwatch logs.

11. If you provided an email to subscribe to SNS events, you will need to confirm the subscription in your email

12. You are encouraged to test the functionality before deploying in production. This can be done by shutting down the controller from the AWS EC2 console. This would trigger the Autoscaling and the HA switchover. Ensure that the new controller has the correct configuration.

13. If you see any issues, report them in this github

14. Enjoy! You are welcome!
