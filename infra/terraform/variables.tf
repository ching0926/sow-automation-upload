variable "aws_region" {
  description = "Deployment region. The shared RDS (sdx-ticket-database-1) lives in us-west-2, so the EC2 must be in the same region for VPC-internal connectivity."
  type        = string
  default     = "us-west-2"
}

variable "aws_profile" {
  description = "Profile name to use from the local ~/.aws/credentials file."
  type        = string
  default     = "intern"
}

variable "name_prefix" {
  description = "Naming prefix for all resources, to make them easy to spot in the console and to confirm scope before destroy."
  type        = string
  default     = "sow-app"
}

variable "instance_type" {
  description = "EC2 instance type. t4g.micro (Graviton/ARM) is cheaper than t3.micro; all packages here (FastAPI/uvicorn/psycopg2-binary/SQLAlchemy) ship arm64 wheels so it works fine. Note: the AMI data source in main.tf must match this architecture (arm64 for t4g, x86_64 for t3/t2/m5 etc.)."
  type        = string
  default     = "t4g.micro"
}

variable "root_volume_size_gb" {
  description = "Root volume size (GB) for running FastAPI + venv. 20GB is plenty."
  type        = number
  default     = 20
}

variable "app_port" {
  description = "Port uvicorn listens on, exposed directly to browsers (no nginx/ALB in front)."
  type        = number
  default     = 8000
}

variable "key_pair_name" {
  description = "Name of the EC2 key pair to create. Deliberately different from the existing sow-intern-nat-key to avoid any collision/overwrite."
  type        = string
  default     = "sow-app-deploy-key"
}

variable "allowed_ssh_cidr" {
  description = "CIDR allowed to SSH in (port 22). Leave as null to auto-detect the public IP of whoever runs `terraform apply` and allow only that /32; set explicitly if a different person applies or you need to SSH from elsewhere."
  type        = string
  default     = null
}

variable "rds_db_instance_identifier" {
  description = "Existing RDS instance identifier (a shared resource -- this terraform never modifies the instance itself, only reads its info and adds one ingress rule to one of its existing security groups)."
  type        = string
  default     = "sdx-ticket-database-1"
}

variable "rds_ingress_security_group_id" {
  description = <<-EOT
    Existing RDS security group ID to add the "allow this EC2 into 5432" rule to.
    This RDS currently has 5 SGs attached: default, local (sg-02d76ec44fcbdb952),
    rds-lambda-2, rds-lambda-3, rds-rdsproxy-1. The last three explicitly warn
    "Modification could lead to connection loss" -- they're dedicated to specific
    Lambda functions / RDS Proxy, so don't touch them. This picks local
    (sg-02d76ec44fcbdb952) instead, since it's already the SG meant for
    "non-Lambda external clients" -- the closest semantic fit. Using
    aws_vpc_security_group_ingress_rule only adds a single rule (it does not
    import/manage the whole SG), so destroy only removes this one rule and never
    affects the SG's other existing rules or other systems using it.
    To point at a different SG, confirm it first with
    `aws rds describe-db-instances --db-instance-identifier sdx-ticket-database-1 --region us-west-2`.
  EOT
  type        = string
  default     = "sg-02d76ec44fcbdb952"
}
