## Aviatrix - AWS CloudFormation template for HA on an Existing Aviatrix controller.

### Description
This guide assumes you already have an Aviatrix Controller running and has been configured. If you don't, launch a controller through instructions available at [Aviatrix Controller Startup Guide](https://docs.aviatrix.com/documentation/latest/getting-started/deploy-controller.html)

This CloudFormation script will create the following:

Core HA Components
* An Aviatrix Autoscaling group with size 1 with a new security group
* An SNS topic with same name as of existing controller instance.
* An email subscription to the SNS topic(optional)
* A lambda function for setting up HA and restoring configuration automatically.
* An Aviatrix Role for Lambda with corresponding role policy with required permissions.

Private API Endpoint
* VPC Endpoint
* Private API Gateway
Need to save a security group rule for `VpcEndpointSecurityGroupIngress`
The Controller can call the Lambda function's `/controller_version` endpoint privately (without going over public internet). This endpoint is restricted to access from the VPC Endpoint only

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

4. Select the appropriate CloudFormation template based on your controller version:
   * **Controller version 7.2 or later**: [Launch template](https://console.aws.amazon.com/cloudformation/home#/stacks/new?stackName=AviatrixHA&templateURL=https://aviatrix-cloudformation-templates.s3.us-west-2.amazonaws.com/aviatrix-aws-existing-controller-ha-v4.json)
   * **Controller version 3.4 to 7.1**: [Launch template](https://console.aws.amazon.com/cloudformation/home#/stacks/new?stackName=AviatrixHA&templateURL=https://aviatrix-cloudformation-templates.s3-us-west-2.amazonaws.com/aviatrix-aws-existing-controller-ha.json)

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


### Terraform Users: Important Configuration Note

This CloudFormation stack creates a self-referencing security group ingress rule (HTTPS from the security group to itself) to enable Private API Gateway communication during HA failover.

**If you manage the controller's security group with Aviatrix terraform module**, the next time it's applied, this rule will be deleted, which will break HA functionality.


### FAQ
1. How do I disable controller H/A?
   
   -  You can disable controller H/A by deleting the CFT stack that was used to enable H/A
   
2. How can I know which version of HA script I am running?
   
   -  versions.py file found in the AWS Lambda function with the name <controller_name>-ha would show the information. You can also see the version in the cloudwatch logs. Only versions from 1.5 and above are visible.   
 
3. How can I get notification for H/A events?
   
   -  Enter an email address to receive notifications for autoscaling group events while launching the CFT. You would receive an email to subscribe to SNS. Click on the link from the email to accept SNS event notifications   
 
4. My H/A event failed. What can I do?
   
   -  You can manually restore the saved backup to a newly launched controller. Please ensure controller H/A is disabled and re-enabled by deleting and re-creating the CFT stack to ensure that lambda is pointing to the right backup
 
5. How do I ensure that lambda is pointing to the right backup?
   
   -  In the AWS Lambda, verify if the INST_ID environment variable is updated correctly to the current controller instance ID and the PRIV_IP environment variable is updated to the current controller private IP.
   
6. Where do I find logs related to controller H/A ?
   
   - All logs related to H/A can be found in AWS Cloudwatch under the log group <controller_name>-ha
   
7. How do I make lambda talk to controller privately within the VPC? (**Advanced, Manual Setup required**)
    
   - Launch CFT with Private access set to True. Attach lambda to the VPC from the AWS console. Ensure that the VPC that you have attached the lambda to has internet access via NAT gateway or VPC endpoints. You can also ensure that lambda has internet access by attaching an EIP(Elastic IP) to the lambda ENI(Network Interface). Please ensure that everything is reverted before you destroy the stack. Otherwise the lambda will not have internet access to respond to the CFT(CFT may get stuck on destroy). Please note that it takes around 15 minutes for lambda to get attached to the VPC and to be able to talk to the controller. Please wait for this duration of 15 minutes, after the VPC attachment, before attempting to test the HA script. 

8. How do I manage the controller HA stack if the controller instance's disk is encrypted?
   - If EBS Encryption using Customer managed key is enabled, the Autoscaling Group created may not have permissions to launch the instance.
You will need to allow the service-linked role created for the Autoscaling group to have permissions to use this key for the cryptographic operation.
To do so, go to AWS KMS->Customer managed keys->select the key and add the "AWSServiceRoleForAutoScaling" role to the list of Key Users.

9. What do I need to do after I change the controller name?
   - Please delete the CFT stack and then create a new CFT stack using the new controller name.

10. How do I update from v3 to v4 CloudFormation template?
   - If you are currently running a 7.2+ AWS Controller AMI with the v3 CloudFormation stack, you can update to the v4 template to address the security issue with the public Lambda function URL being over-permissive and to get improvements for handling security group rule limits. Starting from v4, the public Lambda function URL has been replaced with a private API Gateway endpoint accessed via VPC PrivateLink, and the HA code now automatically tries all security groups when adding temporary Lambda access rules (see FAQ #11). You can perform a direct stack update using the v4 launch template, which is faster than deleting and recreating the stack. However, if there are any changes to the controller configuration, deleting the current stack and recreating a new stack is recommended.

11. What should I do if HA restore fails with "RulesPerSecurityGroupLimitExceeded" error?
   - AWS has a limit of 60 ingress rules per security group. When Security Group Management is enabled, gateway rules are automatically added to the primary security group (the first Aviatrix-created security group, typically named `Aviatrix-SG-{ip}`) first. During HA failover, the HA code needs to add a temporary Lambda access rule to allow configuration restore.
   - **For v4 template users**: The HA code automatically tries all security groups attached to the controller until it finds one with available rule slots. This fix is included in the v4 CloudFormation template and the updated Lambda code package. If you're using v3 or earlier, we recommend updating to v4 to get this improvement.
   - **For v2/v3 template users**: The HA code only uses the first security group. If this security group has reached the 60-rule limit, HA restore will fail. **Solution**: Ensure the first security group attached to your controller has at least one available rule slot (fewer than 60 ingress rules) before enabling HA. You can remove unnecessary rules or reorder security groups so that one with available slots is first.


### Troubleshooting
1. What should I do if I saw this error `[Errno 2] No such file or directory: 'python'` when running poetry commands?
   - `sudo apt install python-is-python3` should fix the issue


### Changelog

The changes between various releases can be viewed from [here](https://github.com/AviatrixSystems/Controller-HA-for-AWS/releases)
