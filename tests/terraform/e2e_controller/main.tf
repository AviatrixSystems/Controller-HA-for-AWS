data "aws_ami" "latest_controller" {
  most_recent = true
  owners      = ["600530653622"]

  filter {
    name   = "name"
    values = ["avx-controller-g4-*"]
  }
}

data "http" "my_ip" {
  url = "http://ipv4.icanhazip.com"
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
  source = "git::https://github.com/terraform-aviatrix-modules/terraform-aviatrix-aws-controlplane"

  access_account_name       = ""
  account_email             = var.admin_email
  customer_id               = var.customer_id
  controller_admin_email    = var.admin_email
  controller_admin_password = local.admin_password
  incoming_ssl_cidrs        = length(var.incoming_ssl_cidrs) > 0 ? var.incoming_ssl_cidrs : ["${chomp(data.http.my_ip.response_body)}/32"]

  controller_ami_id               = var.controller_ami_id == "" ? data.aws_ami.latest_controller.id : var.controller_ami_id
  controller_version              = var.controller_version
  controller_use_existing_keypair = var.key_pair_name == "" ? false : true
  controller_key_pair_name        = var.key_pair_name == "" ? "" : var.key_pair_name

  module_config = {
    iam_roles                 = false
    account_onboarding        = false
    controller_deployment     = var.setup_controller
    controller_initialization = var.setup_controller
    copilot_deployment        = var.setup_copilot
    copilot_initialization    = var.setup_copilot
  }

  environment         = var.environment
  registry_auth_token = var.registry_auth_token
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
