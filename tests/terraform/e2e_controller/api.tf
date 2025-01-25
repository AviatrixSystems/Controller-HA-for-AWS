locals {
  cid = jsondecode(terracurl_request.login.response)["CID"]
}

data "aws_caller_identity" "current" {}

resource "terracurl_request" "login" {
  name            = "login"
  url             = "https://${module.my_controller.controller_public_ip}/v2/api"
  method          = "POST"
  destroy_url     = "https://checkip.amazonaws.com"
  destroy_method  = "GET"
  skip_tls_verify = true
  request_body = jsonencode({
    "action" : "login",
    "username" : "admin",
    "password" : local.admin_password,
  })

  headers = {
    Content-Type = "application/json"
  }

  response_codes = [
    200,
  ]

  max_retry      = 10
  retry_interval = 10

  lifecycle {
    postcondition {
      condition     = jsondecode(self.response)["return"]
      error_message = "Failed to login after initialization: ${jsondecode(self.response)["reason"]}"
    }

    ignore_changes = all
  }

  depends_on = [
    module.my_controller
  ]
}

resource "terracurl_request" "setup_account_profile" {
  name            = "setup_account_profile"
  url             = "https://${module.my_controller.controller_public_ip}/v2/api"
  method          = "POST"
  destroy_url     = "https://checkip.amazonaws.com"
  destroy_method  = "GET"
  skip_tls_verify = true
  request_body = jsonencode({
    "action" : "setup_account_profile",
    "CID" : local.cid,
    "account_name" : "aws",
    "cloud_type" : "1",
    "aws_iam" : "true",
    "aws_account_number" : data.aws_caller_identity.current.account_id,
    "aws_role_arn" : "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/aviatrix-role-app",
    "aws_role_ec2" : "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/aviatrix-role-ec2",
    "skip_sg_config" : "true",
  })

  headers = {
    Content-Type = "application/json"
  }

  response_codes = [
    200,
  ]

  lifecycle {
    postcondition {
      condition     = jsondecode(self.response)["return"]
      error_message = "Failed to create account: ${jsondecode(self.response)["reason"]}"
    }

    ignore_changes = all
  }

  depends_on = [
    terracurl_request.login
  ]
}

resource "terracurl_request" "enable_cloudn_backup_config" {
  name            = "enable_cloudn_backup_config"
  url             = "https://${module.my_controller.controller_public_ip}/v2/api"
  method          = "POST"
  destroy_url     = "https://checkip.amazonaws.com"
  destroy_method  = "GET"
  skip_tls_verify = true
  request_body = jsonencode({
    "action" : "enable_cloudn_backup_config",
    "CID" : local.cid,
    "cloud_type" : "1",
    "acct_name" : "aws",
    "region" : aws_s3_bucket.backup_bucket.region,
    "bucket_name" : aws_s3_bucket.backup_bucket.bucket,
  })

  headers = {
    Content-Type = "application/json"
  }

  response_codes = [
    200,
  ]

  timeout = 60

  lifecycle {
    postcondition {
      condition     = jsondecode(self.response)["return"]
      error_message = "Failed to configure backup: ${jsondecode(self.response)["reason"]}"
    }

    ignore_changes = all
  }

  depends_on = [
    terracurl_request.setup_account_profile
  ]
}
