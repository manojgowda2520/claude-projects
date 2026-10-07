data "aws_caller_identity" "current" {}

module "vpc" {
  source = "../../modules/vpc"

  project              = var.project
  environment          = var.environment
  cidr_block           = var.vpc_cidr
  availability_zones   = var.availability_zones
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
  enable_nat_gateway   = var.enable_nat_gateway
  enable_flow_logs     = var.enable_flow_logs
}

module "web_sg" {
  source = "../../modules/security-group"

  project     = var.project
  environment = var.environment
  name        = "web"
  description = "HTTP access to the application node"
  vpc_id      = module.vpc.vpc_id

  ingress_rules = [
    {
      description = "HTTP from admin network"
      from_port   = 80
      to_port     = 80
      protocol    = "tcp"
      cidr_ipv4   = var.admin_cidr
    },
  ]
}

module "app" {
  source   = "../../modules/ec2"
  count    = var.instance_count

  project            = var.project
  environment        = var.environment
  name               = "app-${count.index}"
  instance_type      = var.instance_type
  subnet_id          = module.vpc.public_subnet_ids[count.index % length(module.vpc.public_subnet_ids)]
  security_group_ids = [module.web_sg.security_group_id]

  user_data = file("${path.module}/../../scripts/bootstrap-app.sh")
}

module "artifacts" {
  source = "../../modules/s3-bucket"

  project     = var.project
  environment = var.environment
  bucket_name = "${var.project}-${var.environment}-artifacts-${data.aws_caller_identity.current.account_id}"

  # Lab environments get torn down often; production keeps its objects.
  force_destroy = var.environment != "prod"
}
