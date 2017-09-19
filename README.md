# Controller-HA-for-AWS

Prerequisites
1. Launch Aviatrix AWS controller using this startup guide. Make sure instance has a 'Name' tag with value as 'AviatrixController'
2. Creating multiple subnets on the VPC where AWS controller is launched. This is for HA over different Availability zones. You can skip this step, if you want to achieve HA over a single AZ only.
3. Create a new 

Procedure:

Create lambda function:
1. Go to lambda console https://console.aws.amazon.com/lambda/home.
2. Click on Create function. Click on Author from scratch. 
3. Click on faded square, and select CloudWatch Events. Click on Rule dropdown box, and select new Rule. 
Add a Rule name(eg. controller_backup). In Schedule expression, add 'rate(1 day)' without colons.  Click Next.
3. Add a function name(eg. controller_ha). Change Runtime to Python 2.7. In Lambda function code section paste the content from file controller_ha.py.
4. Add an environment variable with key as SUBNET_LIST and value as a comma separated list of subnets created in the beginning.
5. In Lambda function handler and role-> Role, from dropdown menu, select 'Create a custom role', A new tab window will open. In IAM Role dropdown menu, click on 'Create a new IAM Role'. Give a Role Name(eg. controller_backup_lambda). Click on View Policy Document and Edit. Paste the content from aviatrix-lambda-policy. Click on Allow.
Create SNS topic and subscribe lambda function to this topic:
6. Click on Next. Click on Create function.
7. Go to SNS console. Click on 'Create new topic'. Enter topic name as AviatrixController. Click on Create Topic.
Click on ARN link next to AviatrixController topic. Click on Create subscription. Choose Protocol as AWS Lambda. 
8. Click on Endpoint and select ARN with lambda function created in last step. Click Create subscription.

Attach controller instance to autoscaling group:
9. Go to EC2 console. Select AviatrixController instance. Click on Actions->Instance Settings->Attach to Auto Scaling Group. Select 'a new Auto Scaling group' Enter Auto Scaling Group Name as 'AviatrixController'.
10. From the left side menu in EC2 console, expand AUTO SCALING, and click on Auto Scaling Groups. Select AviatrixController, and click on Notifications tab. Click on Send a notification to, and from drop down menu, select AviatrixController. In Whenever instances, make sure only launch is checked. Click on Save.
