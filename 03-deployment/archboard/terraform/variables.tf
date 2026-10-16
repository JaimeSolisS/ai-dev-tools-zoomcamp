variable "name" {
  description = "Name prefix for this environment's resources (set in envs/<env>.tfvars)"
  type        = string
}

variable "environment" {
  description = "Environment name, e.g. dev or prod (set in envs/<env>.tfvars)"
  type        = string
}

variable "project" {
  description = "Project tag shared by all environments (the CI role may only roll out to instances tagged with it)"
  type        = string
  default     = "archboard"
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
