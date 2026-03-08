"""ECR stack for OpenClaw SaaS"""
import aws_cdk as cdk
from aws_cdk import aws_ecr as ecr
from constructs import Construct


class EcrStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        config,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Repository names
        repo_names = ["platform", "metrics-exporter", "billing-consumer"]
        self.repositories = {}

        # Create ECR repositories
        for repo_name in repo_names:
            full_repo_name = f"{config.resource_prefix}-{repo_name}"
            repo = ecr.Repository(
                self,
                f"{repo_name.title().replace('-', '')}Repo",
                repository_name=full_repo_name,
                image_scan_on_push=True,
                removal_policy=cdk.RemovalPolicy.RETAIN,  # Keep repos on stack deletion
                lifecycle_rules=[
                    ecr.LifecycleRule(
                        description=f"Keep only last {config.ecr_image_count_limit} images",
                        max_image_count=config.ecr_image_count_limit,
                        rule_priority=1,
                    )
                ],
            )

            self.repositories[repo_name] = repo

            # Output repository URI
            cdk.CfnOutput(
                self,
                f"{repo_name.title().replace('-', '')}RepoUri",
                value=repo.repository_uri,
                description=f"ECR repository URI for {repo_name}",
                export_name=f"{config.stack_prefix}-ecr-{repo_name}",
            )

        # Export platform repo URI for easy access
        cdk.CfnOutput(
            self,
            "PlatformRepoUriOutput",
            value=self.repositories["platform"].repository_uri,
            description="Platform API ECR repository URI",
        )
