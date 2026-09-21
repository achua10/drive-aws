variable "project" {
  type    = string
  default = "drive"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "region" {
  type    = string
  default = "ap-south-1"
}

locals {
  name_prefix = "${var.project}-${var.environment}"
}