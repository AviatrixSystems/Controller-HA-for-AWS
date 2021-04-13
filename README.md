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
* Existing controller must have "aviatrix-role-ec2" attached to it and IAM roles "aviatrix-role-ec2" and "aviatrix-role-app" must be created before hand. Refer [here](https://docs.aviatrix.com/HowTos/HowTo_IAM_role.html)
* Non IAM based controller HA script has been deprecated. An old version is available at "access_key_support" branch in github
* S3 bucket(s) to host the Lambda script and for the backup restore functionality
* S3 bucket used for controller backup/restore must be in the same account


### Step by step Procedure:

1. Make sure that controller version is >= 3.4 in Settings->Maintenance->Upgrade. if not, upgrade your controller to the latest by clicking on "Upgrade" in Settings->Maintence->Upgrade

2. In the controller, make sure that daily backup and restore is enabled in Settings->Maintenance->Backup restore page

3. Do a "Backup Now" from  the Settings->Maintenance->Backup restore page

4. You can launch the cloud formation directly from [here](https://console.aws.amazon.com/cloudformation/home#/stacks/new?stackName=AviatrixHA&templateURL=https://aviatrix-cloudformation-templates.s3-us-west-2.amazonaws.com/aviatrix-aws-existing-controller-ha.json)

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


### FAQ
1. How do I disable controller H/A?
   
   -  You can disable controller H/A by deleting the CFT stack that was used to enable H/A
   
2. How can I know which version of HA script I am running?
   
   - versions.py found in the AWS Lambda with the name <controller_name>-ha. You can also see the version in the cloudwatch logs. Only versions from 1.5 and above are present
   
3. How can I get notification for H/A events?
   
   Enter an email while  notifications for autoscaling group events. You would receive an email to subscribe to SNS. Click on the link from the email to accept SNS events   

4. My H/A event failed. What can I do?
   
   - You can manually restore the saved backup to a newly launched controller. Please ensure controller H/A is disabled and re-enabled by deleting and re-creating the CFT stack to ensure that lambda is pointing to the right backup
 
5. How do I ensure that lambda is pointing to the right backup?
   
   - In the AWS Lambda, verify INST_ID environment variable is updated correctly to the current controller. 
   
6. Where do I find logs related to controller H/A ?
   
   - All logs related to H/A can be found in AWS Cloudwatch under the log group <controller_name>-ha
   
7. How do I make lambda talks to controller privately within the VPC?
    
   - Launch CFT like you normally would. Attach lambda to the VPC form the AWS console. Ensure that the VPC that you have attached has internet access via NAT gateway or VPC endpoints. You can also ensure lambda has internet access by attaching an EIP(Elastic IP) to the lambda ENI(Network Interface). After ensuring that lambda has internet access you can modify the API_PRIVATE_ACCESS environment variable to True. Please ensure that everything is reverted before you destroy the stack. Otherwise the lambda will not have internet access to respond to CFT

    