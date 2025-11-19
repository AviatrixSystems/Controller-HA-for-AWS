data "aws_instance" "controller_instance" {
    instance_id = module.my_controller.controller_instance_id
}

data "aws_subnet" "controller_subnet" {
    id = data.aws_instance.controller_instance.subnet_id
}

resource "aws_cloudformation_stack" "controller_ha" {
    name = "ControllerHA"

    parameters = {
        VPCParam = data.aws_subnet.controller_subnet.vpc_id
        SubnetParam = data.aws_instance.controller_instance.subnet_id
        AviatrixTagParam = module.my_controller.controller_name
        S3BucketBackupParam = aws_s3_bucket.backup_bucket.bucket
        NotifEmailParam = "nobody@aviatrix.com"
    } 

    template_body = file("${path.module}/aviatrix-aws-existing-controller-ha-v4-dev.json")

    capabilities = [
        "CAPABILITY_NAMED_IAM",
    ]

    depends_on = [
        module.my_controller,
        terracurl_request.enable_cloudn_backup_config
    ]
}
