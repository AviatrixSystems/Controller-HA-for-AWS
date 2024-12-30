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
  default     = ["0.0.0.0/0"]
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
