"""OpenClaw SaaS CDK Application"""
import os
import aws_cdk as cdk
from config import Config
from stacks.vpc import VpcStack
from stacks.eks import EksStack
from stacks.rds import RdsStack
from stacks.s3 import S3Stack
from stacks.cloudfront import DnsStack
from stacks.sqs import SqsStack
from stacks.ecr import EcrStack
from stacks.iam import IamStack

app = cdk.App()

# Load configuration
config = Config(app)

# Get AWS account and region from environment or context
# Note: CDK CLI sets CDK_DEFAULT_REGION from the default AWS profile, not --profile.
# For CN deployments, always set AWS_DEFAULT_REGION=cn-northwest-1 in your shell,
# or set aws_region in cdk.json context.
_region = os.environ.get("CDK_DEFAULT_REGION")
_ctx_region = app.node.try_get_context("aws_region")
if _ctx_region:
    _region = _ctx_region
if not _region:
    raise ValueError("AWS region not set. Set CDK_DEFAULT_REGION env var or aws_region in cdk.json context.")

env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=_region,
)

# Common tags for all stacks
tags = config.get_tags()
for key, value in tags.items():
    cdk.Tags.of(app).add(key, value)

# ========== Core Infrastructure ==========

# VPC Stack
vpc_stack = VpcStack(
    app,
    f"{config.stack_prefix}-vpc",
    config=config,
    env=env,
    description="OpenClaw SaaS VPC infrastructure",
)

# ECR Stack (independent)
ecr_stack = EcrStack(
    app,
    f"{config.stack_prefix}-ecr",
    config=config,
    env=env,
    description="OpenClaw SaaS ECR repositories",
)

# SQS Stack (independent)
sqs_stack = SqsStack(
    app,
    f"{config.stack_prefix}-sqs",
    config=config,
    env=env,
    description="OpenClaw SaaS SQS queues for usage events",
)

# S3 Stack (independent)
s3_stack = S3Stack(
    app,
    f"{config.stack_prefix}-s3",
    config=config,
    env=env,
    description="OpenClaw SaaS S3 buckets for backups",
)

# DNS/CloudFront Stack (optional, only if domain configured)
if config.has_custom_domain:
    dns_stack = DnsStack(
        app,
        f"{config.stack_prefix}-dns",
        config=config,
        vpc=vpc_stack.vpc,
        env=env,
        description="OpenClaw SaaS CloudFront, DNS, and NLB security group",
    )
    dns_stack.add_dependency(vpc_stack)

# ========== EKS and Related ==========

# EKS Stack (depends on VPC)
eks_stack = EksStack(
    app,
    f"{config.stack_prefix}-eks",
    vpc=vpc_stack.vpc,
    config=config,
    env=env,
    description="OpenClaw SaaS EKS cluster",
)
eks_stack.add_dependency(vpc_stack)

# IAM Stack (depends on EKS for IRSA)
iam_stack = IamStack(
    app,
    f"{config.stack_prefix}-iam",
    cluster=eks_stack.cluster,
    usage_queue_arn=sqs_stack.usage_queue.queue_arn,
    config=config,
    node_role=eks_stack.nodegroup.role,
    env=env,
    description="OpenClaw SaaS IAM roles and policies",
)
iam_stack.add_dependency(eks_stack)
iam_stack.add_dependency(sqs_stack)

# RDS Stack (depends on VPC and EKS for security groups)
rds_stack = RdsStack(
    app,
    f"{config.stack_prefix}-rds",
    vpc=vpc_stack.vpc,
    eks_security_group=eks_stack.node_security_group,
    config=config,
    env=env,
    description="OpenClaw SaaS PostgreSQL database",
)
rds_stack.add_dependency(vpc_stack)
rds_stack.add_dependency(eks_stack)

app.synth()
