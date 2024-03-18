import boto3
import botocore


def get_target_group_arns(inst_id):
    """Get target group arns the running ec2 instance is registered to."""
    elb_client = boto3.client("elbv2")
    target_groups = elb_client.describe_target_groups().get("TargetGroups", [])
    target_group_arns = []
    for tg_ in target_groups:
        try:
            target_health = elb_client.describe_target_health(
                TargetGroupArn=tg_.get("TargetGroupArn", "")
            ).get("TargetHealthDescriptions", [])
            for registered_target in target_health:
                if registered_target.get("Target", {}).get("Id", "") == inst_id:
                    target_group_arns.append(tg_["TargetGroupArn"])
                    break
        except (
            botocore.exceptions.ClientError,
            elb_client.exceptions.TargetGroupNotFoundException,
        ) as err:
            print(str(err))
    print(f"target_group_arns is {target_group_arns}")
    return target_group_arns
