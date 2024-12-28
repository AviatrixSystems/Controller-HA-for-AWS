terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">=5.80"
    }
    terracurl = {
      source  = "devops-rob/terracurl"
      version = "1.2.1"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}
