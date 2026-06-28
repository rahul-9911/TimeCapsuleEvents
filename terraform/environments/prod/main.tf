terraform {
  backend "s3" {
    bucket         = "snapevent-terraform-state"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "snapevent-terraform-locks"
    encrypt        = true
  }
  required_version = ">= 1.6"
  required_providers {
    aws    = { source = "hashicorp/aws"; version = "~> 5.0" }
    random = { source = "hashicorp/random"; version = "~> 3.0" }
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = { Project = "snapevent", Environment = "prod", ManagedBy = "terraform" }
  }
}

module "networking" {
  source = "../../modules/networking"
  env    = var.env
}

module "ecs_cluster" {
  source = "../../modules/ecs-cluster"
  env    = var.env
  vpc_id = module.networking.vpc_id
}

module "storage" {
  source                   = "../../modules/storage"
  env                      = var.env
  vpc_id                   = module.networking.vpc_id
  private_subnet_ids       = module.networking.private_subnet_ids
  sg_efs_id                = module.networking.sg_efs_id
  s3_photos_lifecycle_days = 365
}

module "event_worker" {
  source             = "../../modules/event-worker"
  env                = var.env
  aws_region         = var.aws_region
  execution_role_arn = module.ecs_cluster.execution_role_arn
  task_role_arn      = module.ecs_cluster.event_task_role_arn
  private_subnet_ids = module.networking.private_subnet_ids
  sg_event_worker_id = module.networking.sg_event_worker_id
  s3_bucket          = module.storage.bucket_name
  efs_id             = module.storage.efs_id
  image_url          = module.ecs_cluster.ecr_event_url
  image_tag          = var.image_tag
}

module "control_plane" {
  source                = "../../modules/control-plane"
  env                   = var.env
  aws_region            = var.aws_region
  cluster_arn           = module.ecs_cluster.cluster_arn
  cluster_name          = module.ecs_cluster.cluster_name
  execution_role_arn    = module.ecs_cluster.execution_role_arn
  task_role_arn         = module.ecs_cluster.control_task_role_arn
  private_subnet_ids    = module.networking.private_subnet_ids
  sg_control_plane_id   = module.networking.sg_control_plane_id
  sg_rds_id             = module.networking.sg_rds_id
  target_group_arn      = module.networking.target_group_arn
  s3_bucket             = module.storage.bucket_name
  efs_id                = module.storage.efs_id
  image_url             = module.ecs_cluster.ecr_control_url
  image_tag             = var.image_tag
  db_instance_class     = "db.t3.medium"   # bigger for prod
  base_url              = "https://${var.domain_name}"
  smtp_user             = var.smtp_user
  smtp_pass             = var.smtp_pass
  event_task_definition = module.event_worker.task_definition_family
  event_sg_id           = module.networking.sg_event_worker_id
}

output "alb_dns"    { value = module.networking.alb_dns_name }
output "ecr_control"{ value = module.ecs_cluster.ecr_control_url }
output "ecr_event"  { value = module.ecs_cluster.ecr_event_url }
