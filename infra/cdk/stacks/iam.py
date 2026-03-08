"""IAM stack for OpenClaw SaaS"""
import aws_cdk as cdk
from aws_cdk import aws_iam as iam
from aws_cdk import aws_eks as eks
from constructs import Construct


class IamStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        cluster: eks.Cluster,
        usage_queue_arn: str,
        config,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # IRSA role for platform-api service account
        # This role allows the platform API to manage K8s resources and send to SQS
        oidc_provider = cluster.open_id_connect_provider

        conditions = cdk.CfnJson(
            self,
            "PlatformApiCondition",
            value={
                f"{oidc_provider.open_id_connect_provider_issuer}:sub":
                    "system:serviceaccount:openclaw-platform:platform-api",
                f"{oidc_provider.open_id_connect_provider_issuer}:aud":
                    "sts.amazonaws.com",
            },
        )

        self.platform_api_role = iam.Role(
            self,
            "PlatformApiRole",
            role_name=f"{config.resource_prefix}-platform-api-role",
            assumed_by=iam.FederatedPrincipal(
                oidc_provider.open_id_connect_provider_arn,
                conditions={"StringEquals": conditions},
                assume_role_action="sts:AssumeRoleWithWebIdentity",
            ),
            description="IRSA role for OpenClaw platform API",
        )

        # SQS permissions for usage events
        self.platform_api_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "sqs:SendMessage",
                    "sqs:GetQueueUrl",
                    "sqs:GetQueueAttributes",
                ],
                resources=[usage_queue_arn],
            )
        )

        # Kubernetes API access (for managing tenant resources)
        # Note: K8s RBAC is defined separately in k8s/platform/rbac.yaml
        # This is just for pod logs access
        self.platform_api_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:GetLogEvents",
                    "logs:FilterLogEvents",
                ],
                resources=[
                    f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/eks/{cluster.cluster_name}/cluster:*",
                    f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/containerinsights/{cluster.cluster_name}/*:*",
                ],
            )
        )

        # Additional policies for EKS node groups (Bedrock access)
        # These are attached to the node IAM role, not IRSA
        # We'll just create a policy that can be attached to node roles
        self.node_bedrock_policy = iam.ManagedPolicy(
            self,
            "NodeBedrockPolicy",
            managed_policy_name=f"{config.resource_prefix}-node-bedrock-policy",
            description="Allow EKS nodes to access AWS Bedrock",
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "bedrock:InvokeModel",
                        "bedrock:InvokeModelWithResponseStream",
                    ],
                    resources=["*"],  # Bedrock doesn't support resource-level permissions
                )
            ],
        )

        # Outputs
        cdk.CfnOutput(
            self,
            "PlatformApiRoleArn",
            value=self.platform_api_role.role_arn,
            description="ARN of the platform API IRSA role",
            export_name=f"{config.stack_prefix}-platform-api-role-arn",
        )

        cdk.CfnOutput(
            self,
            "NodeBedrockPolicyArn",
            value=self.node_bedrock_policy.managed_policy_arn,
            description="ARN of the Bedrock policy for EKS nodes",
            export_name=f"{config.stack_prefix}-node-bedrock-policy-arn",
        )
