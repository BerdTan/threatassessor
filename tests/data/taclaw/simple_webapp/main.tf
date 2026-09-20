# simple_webapp — internet-facing web app on AWS (TAclaw test fixture)
# 3-tier: ALB → EC2 → RDS. Port 80 open to internet. No WAF, no HTTPS.

provider "aws" {
  region = "us-east-1"
}

resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  map_public_ip_on_launch = true
  availability_zone       = "us-east-1a"
}

resource "aws_subnet" "private" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.2.0/24"
  availability_zone = "us-east-1b"
}

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id
}

resource "aws_lb" "app" {
  name               = "webapp-alb"
  internal           = false
  load_balancer_type = "application"
  subnets            = [aws_subnet.public.id]
}

resource "aws_lb_target_group" "app" {
  port     = 80
  protocol = "HTTP"
  vpc_id   = aws_vpc.main.id
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.app.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}

resource "aws_instance" "web" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "t3.micro"
  subnet_id     = aws_subnet.public.id

  user_data = <<-EOF
    #!/bin/bash
    yum install -y python3
    python3 -m http.server 8080
  EOF

  tags = {
    Name = "webapp-server"
    Role = "web"
  }
}
