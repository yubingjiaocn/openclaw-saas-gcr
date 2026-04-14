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
# Priority: AWS_REGION / AWS_ACCOUNT_ID (.env) → CDK_DEFAULT_* (AWS profile) → cdk.json context
_region = (
    os.environ.get("AWS_REGION")
    or os.environ.get("CDK_DEFAULT_REGION")
    or app.node.try_get_context("aws_region")
)
if not _region:
    raise ValueError(
        "AWS region not set. Set AWS_REGION in .env, CDK_DEFAULT_REGION, or aws_region in cdk.json."
    )

_account = (
    os.environ.get("AWS_ACCOUNT_ID")
    or os.environ.get("CDK_DEFAULT_ACCOUNT")
)
if not _account:
    raise ValueError(
        "AWS account not set. Set AWS_ACCOUNT_ID in .env or CDK_DEFAULT_ACCOUNT."
    )

# Auto-infer target partition from region (aws-cn for China, aws otherwise)
_partition = "aws-cn" if _region.startswith("cn-") else "aws"
app.node.set_context("@aws-cdk/core:target-partitions", [_partition])

env = cdk.Environment(
    account=_account,
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
