data "aws_ami" "latest_controller" {
  most_recent = true
  owners      = ["600530653622"]

  filter {
    name   = "name"
    values = ["avx-controller-g4-*"]
  }
}

# try to satisfy the controller's password strength meter by combining
# two passwords with a special char
resource "random_password" "admin" {
  count = 3

  length      = 6
  special     = false
  min_numeric = 1
}

locals {
  admin_password = nonsensitive(join("-", random_password.admin[*].result))
}

module "my_controller" {
  source = "git::https://github.com/AviatrixSystems/terraform-aviatrix-aws-controlplane?ref=no-cft"

  account_email             = var.admin_email
  customer_id               = var.customer_id
  controller_admin_email    = var.admin_email
  controller_admin_password = local.admin_password
  incoming_ssl_cidrs        = var.incoming_ssl_cidrs

  controller_ami_id = var.controller_ami_id == "" ? data.aws_ami.latest_controller.id : var.controller_ami_id
  controller_user_data = templatefile("${path.module}/cloud-config.yaml", {
    software_version          = var.controller_version
    use_containerized_gateway = var.use_containerized_gateway ? "true" : "false"
  })
  controller_wait_for_setup_duration = "0s"
  use_existing_keypair               = var.key_pair_name == "" ? false : true
  key_pair_name                      = var.key_pair_name == "" ? "" : var.key_pair_name

  module_config = {
    controller_iam            = false,
    controller_deployment     = var.setup_controller
    controller_initialization = var.setup_controller
    copilot_deployment        = var.setup_copilot
    copilot_initialization    = var.setup_copilot
  }
}

resource "aws_s3_bucket" "backup_bucket" {
  bucket_prefix = "tf-"
  tags = {
    CreatedBy = "tf-ctrl-ha-test"
  }
  force_destroy = true
}

output "controller_public_ip" {
  value = module.my_controller.controller_public_ip
}

output "controller_private_ip" {
  value = module.my_controller.controller_private_ip
}

output "controller_instance_id" {
  value = module.my_controller.controller_instance_id
}

output "controller_name" {
  value = module.my_controller.controller_name
}

output "controller_admin_password" {
  value = local.admin_password
}
