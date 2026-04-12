"""Central configuration for OpenClaw SaaS Infrastructure

All configuration values are read from cdk.json context.
Override via cdk.json or CLI: cdk deploy -c key=value
"""
import aws_cdk as cdk


class Config:
    """Configuration container for OpenClaw SaaS infrastructure"""

    def __init__(self, app: cdk.App):
        self.app = app

        # Project identification
        self.project_name = self._get_context("project_name", "openclaw-saas")
        self.environment = self._get_context("environment", "dev")

        # Domain and DNS configuration
        self.domain_name = self._get_context("domain_name", "")
        self.hosted_zone_id = self._get_context("hosted_zone_id", "")
        self.hosted_zone_name = self._get_context("hosted_zone_name", "")
        self.acm_cert_arn = self._get_context("acm_cert_arn", "")

        # RDS configuration
        self.db_instance_class = self._get_context("db_instance_class", "db.t4g.micro")
        self.db_name = self._get_context("db_name", "openclawsaas")
        self.db_allocated_storage = self._get_context("db_allocated_storage", 20)
        self.db_max_allocated_storage = self._get_context("db_max_allocated_storage", 100)

        # EKS configuration
        self.eks_node_instance_type = self._get_context("eks_node_instance_type", "t4g.medium")
        self.eks_node_min = self._get_context("eks_node_min", 2)
        self.eks_node_max = self._get_context("eks_node_max", 5)
        self.eks_node_desired = self._get_context("eks_node_desired", 2)
        self.eks_node_disk_size = self._get_context("eks_node_disk_size", 50)
        self.eks_version = self._get_context("eks_version", "1.30")

        # VPC configuration
        self.vpc_max_azs = self._get_context("vpc_max_azs", 2)
        self.enable_nat_gateway = self._get_context("enable_nat_gateway", True)
        self.nat_gateways = self._get_context("nat_gateways", 1)

        # SQS configuration
        self.sqs_visibility_timeout = self._get_context("sqs_visibility_timeout", 60)
        self.sqs_retention_period_days = self._get_context("sqs_retention_period_days", 14)
        self.sqs_receive_wait_time = self._get_context("sqs_receive_wait_time", 20)
        self.sqs_max_receive_count = self._get_context("sqs_max_receive_count", 5)

        # S3 configuration
        self.s3_lifecycle_transition_days = self._get_context("s3_lifecycle_transition_days", 30)

        # ECR configuration
        self.ecr_image_count_limit = self._get_context("ecr_image_count_limit", 10)

    def _get_context(self, key: str, default=None):
        """Get context value with fallback to default"""
        value = self.app.node.try_get_context(key)
        return value if value is not None else default

    @property
    def stack_prefix(self) -> str:
        """Get stack name prefix"""
        if self.environment:
            return f"{self.project_name}-{self.environment}"
        return self.project_name

    @property
    def resource_prefix(self) -> str:
        """Get resource name prefix"""
        if self.environment:
            return f"{self.project_name}-{self.environment}"
        return self.project_name

    @property
    def has_custom_domain(self) -> bool:
        """Check if custom domain is configured"""
        return bool(self.domain_name)

    @property
    def has_hosted_zone(self) -> bool:
        """Check if Route53 hosted zone is configured"""
        return bool(self.hosted_zone_id and self.hosted_zone_name)

    @property
    def has_acm_cert(self) -> bool:
        """Check if ACM certificate is configured"""
        return bool(self.acm_cert_arn)

    def get_tags(self) -> dict:
        """Get common tags for all resources"""
        return {
            "Project": self.project_name,
            "Environment": self.environment,
            "ManagedBy": "CDK",
        }
