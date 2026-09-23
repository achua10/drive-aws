output "api_url" {
  value       = aws_apigatewayv2_api.http.api_endpoint
  description = "Base URL for the HTTP API"
}

output "bucket_name" {
  value = aws_s3_bucket.files.bucket
}

output "table_name" {
  value = aws_dynamodb_table.files.name
}

output "ecr_repository_url" {
  value = aws_ecr_repository.app.repository_url
}