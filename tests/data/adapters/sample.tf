terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

resource "aws_api_gateway_rest_api" "api" {
  name = "ta-sip-test-api"
}

resource "aws_lambda_function" "handler" {
  function_name = "ta-sip-handler"
  runtime       = "python3.11"
  handler       = "main.handler"
  role          = aws_iam_role.lambda_exec.arn
}

resource "aws_iam_role" "lambda_exec" {
  name               = "ta-sip-lambda-exec"
  assume_role_policy = "{}"
}

resource "aws_db_instance" "main" {
  identifier        = "ta-sip-db"
  engine            = "postgres"
  instance_class    = "db.t3.micro"
  allocated_storage = 20
  depends_on        = [aws_lambda_function.handler]
}

resource "aws_s3_bucket" "artifacts" {
  bucket = "ta-sip-artifacts"
}

resource "aws_sqs_queue" "jobs" {
  name = "ta-sip-jobs"
}
