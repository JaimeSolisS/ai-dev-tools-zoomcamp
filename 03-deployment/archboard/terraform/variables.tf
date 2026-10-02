variable "name" {
  description = "Name prefix for all resources"
  type        = string
  default     = "archboard"
}

variable "aws_profile" {
  description = "AWS CLI profile to deploy with"
  type        = string
  default     = "jsolisdev"
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "instance_type" {
  description = "EC2 instance type (x86_64, to match the image built by deploy.sh)"
  type        = string
  default     = "t3.nano"
}
