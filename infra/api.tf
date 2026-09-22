resource "aws_lambda_function" "app" {
  function_name = "${local.name_prefix}-app"
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.app.repository_url}:v2"
  timeout       = 10
  memory_size   = 256

  environment {
    variables = {
      BUCKET_NAME = aws_s3_bucket.files.bucket
      TABLE_NAME  = aws_dynamodb_table.files.name
    }
  }

  depends_on = [aws_iam_role_policy_attachment.lambda_basic_execution]
}