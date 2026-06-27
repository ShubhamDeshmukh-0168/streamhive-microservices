resource "aws_db_subnet_group" "hive_rds_subnet_group" {
  name       = "hive-rds-subnet-group"
  subnet_ids = aws_subnet.private_subnet[*].id
}

resource "aws_security_group" "rds_sg" {
  name   = "hive-rds-sg"
  vpc_id = aws_vpc.hive_vpc.id

  ingress {
    from_port       = 3306
    to_port         = 3306
    protocol        = "tcp"
    cidr_blocks     = ["10.0.0.0/16"]   # <-- CHANGE: restrict further if needed, this allows the whole VPC
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_instance" "hive_rds" {
  identifier             = "hive-rds"
  engine                 = "mysql"
  engine_version         = "8.0"
  instance_class         = "db.t3.micro"   # <-- CHANGE: scale up for production workloads
  allocated_storage      = 20
  db_name                = "streamhive"
  username               = var.db_username
  password               = var.db_password
  db_subnet_group_name   = aws_db_subnet_group.hive_rds_subnet_group.name
  vpc_security_group_ids = [aws_security_group.rds_sg.id]
  multi_az               = false   # <-- CHANGE: set true for production high-availability
  skip_final_snapshot    = true    # <-- CHANGE: set false in production so you get a final snapshot on delete
  publicly_accessible    = false
}

output "rds_endpoint" {
  value = aws_db_instance.hive_rds.endpoint
}
