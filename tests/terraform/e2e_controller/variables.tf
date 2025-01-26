variable "admin_email" {
  description = "Email address of the administrator"
  type        = string
  default     = "nobody@aviatrix.com"
}

variable "customer_id" {
  description = "Customer ID"
  type        = string
}

variable "incoming_ssl_cidrs" {
  description = "List of CIDRs to allow incoming connections from"
  type        = list(string)
  default     = []
}

variable "controller_ami_id" {
  description = "Controller AMI ID"
  type        = string
  default     = ""
}

variable "controller_version" {
  description = "Controller version"
  type        = string
  default     = "latest"
}

variable "use_containerized_gateway" {
  description = "Whether or not to use containerized gateway"
  type        = bool
  default     = false
}

variable "key_pair_name" {
  description = "Key pair name (if not provided, one will be created)"
  type        = string
  default     = ""
}

variable "setup_controller" {
  description = "Whether or not to setup controller"
  type        = bool
  default     = true
}

variable "setup_copilot" {
  description = "Whether or not to setup copilot"
  type        = bool
  default     = false
}

# terraform-docs-ignore
variable "environment" {
  description = "Determines the deployment environment. For internal use only."
  type        = string
  default     = "prod"
  nullable    = false

  validation {
    condition     = contains(["prod", "staging"], var.environment)
    error_message = "The environment must be either 'prod' or 'staging'."
  }
}

# terraform-docs-ignore
variable "registry_auth_token" {
  description = "The token used to authenticate to the controller artifact registry. For internal use only."
  type        = string
  default     = ""
  nullable    = false
}
