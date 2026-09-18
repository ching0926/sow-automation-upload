output "instance_id" {
  value = aws_instance.app.id
}

output "public_ip" {
  description = "Elastic IP, stays fixed -- deploy.py always connects to this IP"
  value       = aws_eip.app.public_ip
}

output "app_url" {
  value = "http://${aws_eip.app.public_ip}:${var.app_port}/"
}

output "app_url_dns" {
  description = "Same app, addressed by the AWS-assigned *.compute.amazonaws.com hostname instead of the raw IP. Some corporate web proxies block bare IP:port URLs as an unrecognized category; an amazonaws.com hostname is usually recognized/allowed."
  value       = "http://${aws_instance.app.public_dns}:${var.app_port}/"
}

output "review_dri_url_example" {
  description = "Example DRI review page URL -- replace jobcode with the actual job_code to review"
  value       = "http://${aws_eip.app.public_ip}:${var.app_port}/review/dri.html?jobcode=E1122345678"
}

output "ssh_command" {
  value = "ssh -i ${local_sensitive_file.private_key.filename} ec2-user@${aws_eip.app.public_ip}"
}

output "private_key_path" {
  value = local_sensitive_file.private_key.filename
}

output "rds_endpoint" {
  description = "Shared RDS connection address -- use this for .env's DB_HOST (remember DB_NAME is SDXINTERN)"
  value       = data.aws_db_instance.sow_rds.address
}

output "rds_port" {
  value = data.aws_db_instance.sow_rds.port
}

output "security_group_id" {
  value = aws_security_group.app.id
}
