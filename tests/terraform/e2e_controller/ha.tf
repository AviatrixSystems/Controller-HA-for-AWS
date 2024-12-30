resource "aws_cloudformation_stack" "controller_ha" {
    name = "ControllerHA"

    parameters = {
        VPCParam = module.my_controller.controller_vpc_id
        SubnetParam = module.my_controller.controller_subnet_id
        AviatrixTagParam = module.my_controller.controller_name
        S3BucketBackupParam = aws_s3_bucket.backup_bucket.bucket
        NotifEmailParam = "nobody@aviatrix.com"
    } 

    template_body = file("${path.module}/aviatrix-aws-existing-controller-ha-v3-dev.json")

    capabilities = [
        "CAPABILITY_NAMED_IAM",
    ]

    depends_on = [
        module.my_controller,
        terracurl_request.enable_cloudn_backup_config
    ]
}
