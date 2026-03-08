"""VPC stack for OpenClaw SaaS"""
import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from constructs import Construct


class VpcStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        config,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create VPC with configurable AZs and NAT gateways
        nat_gateways = config.nat_gateways if config.enable_nat_gateway else 0

        self.vpc = ec2.Vpc(
            self,
            "OpenClawVpc",
            max_azs=config.vpc_max_azs,
            nat_gateways=nat_gateways,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
            ],
            enable_dns_hostnames=True,
            enable_dns_support=True,
        )

        # Add VPC Endpoints for cost savings and security

        # S3 Gateway Endpoint (free)
        self.vpc.add_gateway_endpoint(
            "S3Endpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3,
            subnets=[ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)],
        )

        # ECR API Endpoint (for pulling container images)
        self.vpc.add_interface_endpoint(
            "EcrApiEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.ECR,
            private_dns_enabled=True,
        )

        # ECR Docker Endpoint (for pulling container layers)
        self.vpc.add_interface_endpoint(
            "EcrDockerEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER,
            private_dns_enabled=True,
        )

        # STS Endpoint (for IAM roles for service accounts)
        self.vpc.add_interface_endpoint(
            "StsEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.STS,
            private_dns_enabled=True,
        )

        # Output VPC ID
        cdk.CfnOutput(
            self,
            "VpcId",
            value=self.vpc.vpc_id,
            description="VPC ID",
        )

        # Output CIDR
        cdk.CfnOutput(
            self,
            "VpcCidr",
            value=self.vpc.vpc_cidr_block,
            description="VPC CIDR Block",
        )
