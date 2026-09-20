output "alb_dns_name" {
  description = "Public DNS of the load balancer"
  value       = aws_lb.app.dns_name
}

output "web_instance_id" {
  value = aws_instance.web.id
}

output "db_endpoint" {
  description = "RDS endpoint (internal)"
  value       = aws_db_instance.postgres.endpoint
  sensitive   = true
}
