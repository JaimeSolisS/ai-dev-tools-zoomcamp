output "url" {
  description = "Where the app is served"
  value       = "http://${aws_eip.app.public_ip}"
}

output "public_ip" {
  value = aws_eip.app.public_ip
}

output "instance_id" {
  value = aws_instance.app.id
}

output "ecr_repository_url" {
  value = aws_ecr_repository.app.repository_url
}

output "region" {
  value = var.region
}
