variable "name" {
  description = "Name prefix; must match the main config's"
  type        = string
  default     = "archboard"
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "github_sub_prefix" {
  description = <<-EOT
    Subject claim prefix of the repository whose main branch may deploy. The repo uses
    GitHub's immutable subject claims (owner and repo IDs, so a rename can't hijack it);
    get it with: gh api repos/OWNER/REPO/actions/oidc/customization/sub --jq .sub_claim_prefix
  EOT
  type        = string
  default     = "repo:JaimeSolisS@26722249/ai-dev-tools-zoomcamp@1355245122"
}
