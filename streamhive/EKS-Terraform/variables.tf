variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-west-2"   # <-- CHANGE: your preferred AWS region
}

variable "bastion_key_name" {
  description = "EC2 key pair name used to SSH into the bastion host"
  type        = string
  default     = "REPLACE_WITH_YOUR_KEY_PAIR_NAME"   # <-- CHANGE: must exist in your AWS account already
}

variable "db_username" {
  description = "Master username for the RDS MySQL instance"
  type        = string
  default     = "admin"   # <-- CHANGE: choose your own DB admin username
}

variable "db_password" {
  description = "Master password for the RDS MySQL instance"
  type        = string
  sensitive   = true
  default     = "Cloud123"   # <-- CHANGE: never commit a real password, use TF_VAR_db_password env var or a secrets manager instead
}
