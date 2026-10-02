variable "name" {
  description = "Name prefix; must match the main config's"
  type        = string
  default     = "archboard"
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "github_repo" {
  description = "owner/name of the repository whose main branch may deploy"
  type        = string
  default     = "JaimeSolisS/ai-dev-tools-zoomcamp"
}
