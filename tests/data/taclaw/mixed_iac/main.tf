# mixed_iac — compute layer (Terraform)
# Lambda + SQS + RDS. Part of multi-adapter fixture.

provider "aws" {
  region = "eu-west-1"
}

resource "aws_lambda_function" "api_processor" {
  function_name = "api-processor"
  runtime       = "python3.11"
  role          = aws_iam_role.lambda_role.arn
  handler       = "handler.main"
  filename      = "lambda.zip"

  environment {
    variables = {
      DB_HOST   = aws_db_instance.postgres.endpoint
      QUEUE_URL = aws_sqs_queue.events.url
    }
  }
}

resource "aws_iam_role" "lambda_role" {
  name = "lambda-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "lambda_policy" {
  role = aws_iam_role.lambda_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:*", "sqs:*", "rds:*"]
      Resource = "*"
    }]
  })
}

resource "aws_db_instance" "postgres" {
  engine              = "postgres"
  engine_version      = "14"
  instance_class      = "db.t3.micro"
  allocated_storage   = 20
  db_name             = "appdb"
  username            = "admin"
  password            = "changeme"
  publicly_accessible = false
  skip_final_snapshot = true
}

resource "aws_sqs_queue" "events" {
  name                       = "event-queue"
  visibility_timeout_seconds = 30
}

resource "aws_sqs_queue" "dlq" {
  name = "event-dlq"
}
