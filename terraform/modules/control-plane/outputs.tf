output "control_task_definition_arn" { value = aws_ecs_task_definition.control.arn }
output "rds_endpoint"               { value = aws_db_instance.control.endpoint }
