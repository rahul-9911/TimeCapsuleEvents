# ── API Gateway HTTP API — Entry point for all traffic ────────────────────────

resource "aws_apigatewayv2_api" "main" {
  name          = "snapevent-${var.env}"
  protocol_type = "HTTP"
  description   = "SnapEvent ${var.env} API"



  tags = {
    Name = "snapevent-${var.env}-api"
  }
}

# Lambda integration (proxy mode — all requests forwarded to Lambda)
resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = var.lambda_invoke_arn
  payload_format_version = "2.0"
}

# Default route — catch-all, sends everything to Lambda
resource "aws_apigatewayv2_route" "default" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

# Auto-deploy stage
resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.main.id
  name        = "$default"
  auto_deploy = true

  tags = {
    Name = "snapevent-${var.env}-default-stage"
  }
}

# Permission: Allow API Gateway to invoke the Lambda function
resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}
