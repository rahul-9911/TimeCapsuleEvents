output "cluster_arn"             { value = aws_ecs_cluster.main.arn }
output "cluster_name"            { value = aws_ecs_cluster.main.name }
output "execution_role_arn"      { value = aws_iam_role.execution.arn }
output "control_task_role_arn"   { value = aws_iam_role.control_task.arn }
output "event_task_role_arn"     { value = aws_iam_role.event_task.arn }
output "ecr_control_url"         { value = aws_ecr_repository.control.repository_url }
output "ecr_event_url"           { value = aws_ecr_repository.event.repository_url }
