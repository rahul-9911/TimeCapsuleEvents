output "api_url" {
  value       = aws_apigatewayv2_api.main.api_endpoint
  description = "The public invoke URL for the API (https://xxxxx.execute-api.region.amazonaws.com)"
}

output "api_id" {
  value = aws_apigatewayv2_api.main.id
}
