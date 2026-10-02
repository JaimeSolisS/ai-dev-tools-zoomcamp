output "deploy_role_arn" {
  description = "Role for the GitHub Actions deploy job (AWS_DEPLOY_ROLE_ARN in the workflow)"
  value       = aws_iam_role.deploy.arn
}

output "state_bucket" {
  value = aws_s3_bucket.state.bucket
}
