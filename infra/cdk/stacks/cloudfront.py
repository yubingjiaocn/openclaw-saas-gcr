"""CloudFront, DNS, and NLB Security Group stack for OpenClaw SaaS

This stack handles:
- CloudFront Distribution (origin placeholder, updated by deploy.sh after NLB ready)
- NLB Security Group restricted to CloudFront managed prefix list
- Route53 A record pointing domain to CloudFront
- ACM certificate import/creation

Note: This is OPTIONAL - only created if domain_name is configured.
"""
import aws_cdk as cdk
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_route53_targets as route53_targets
from constructs import Construct


class DnsStack(cdk.Stack):
    """CloudFront, DNS, and NLB security group management"""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        config,
        vpc: ec2.IVpc,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.certificate = None
        self.hosted_zone = None
        self.distribution = None
        self.nlb_security_group = None

        # Only create resources if domain is configured
        if not config.has_custom_domain:
            cdk.CfnOutput(
                self,
                "Status",
                value="No custom domain configured - skipping DNS/CloudFront setup",
            )
            return

        # --- Security Group for NLB (CloudFront prefix list only) ---
        self.nlb_security_group = ec2.SecurityGroup(
            self,
            "NlbSecurityGroup",
            vpc=vpc,
            description="NLB SG - allows inbound HTTP from CloudFront only",
            allow_all_outbound=True,
        )

        # Allow TCP:80 from CloudFront managed prefix list
        self.nlb_security_group.add_ingress_rule(
            peer=ec2.Peer.prefix_list("pl-82a045eb"),
            connection=ec2.Port.tcp(80),
            description="Allow HTTP from CloudFront managed prefix list",
        )

        # Allow TCP:80 from VPC CIDR for NLB health checks.
        # NLB IP-mode health checks originate from NLB nodes inside the VPC,
        # which are NOT covered by the CloudFront prefix list.
        self.nlb_security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(80),
            description="Allow NLB health checks from within VPC",
        )

        cdk.CfnOutput(
            self,
            "NlbSecurityGroupId",
            value=self.nlb_security_group.security_group_id,
            description="Security Group ID for NLB (CloudFront prefix list restricted)",
            export_name=f"{config.stack_prefix}-nlb-sg-id",
        )

        # --- ACM Certificate ---
        if config.has_acm_cert:
            self.certificate = acm.Certificate.from_certificate_arn(
                self,
                "ImportedCertificate",
                certificate_arn=config.acm_cert_arn,
            )
            cert_arn_output = config.acm_cert_arn
        else:
            if not config.has_hosted_zone:
                raise ValueError(
                    "Cannot create ACM certificate without hosted_zone_id. "
                    "Either provide acm_cert_arn or both domain_name and hosted_zone_id."
                )

            self.hosted_zone = route53.HostedZone.from_hosted_zone_attributes(
                self,
                "HostedZone",
                hosted_zone_id=config.hosted_zone_id,
                zone_name=config.hosted_zone_name,
            )

            self.certificate = acm.Certificate(
                self,
                "Certificate",
                domain_name=config.domain_name,
                validation=acm.CertificateValidation.from_dns(self.hosted_zone),
            )
            cert_arn_output = self.certificate.certificate_arn

        cdk.CfnOutput(
            self,
            "CertificateArn",
            value=cert_arn_output,
            description="ACM Certificate ARN",
            export_name=f"{config.stack_prefix}-acm-cert-arn",
        )

        # --- CloudFront Distribution ---
        # Origin is a placeholder; deploy.sh updates it after NLB is provisioned
        placeholder_origin = origins.HttpOrigin(
            "placeholder.elb.us-west-2.amazonaws.com",
            protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY,
            http_port=80,
        )

        self.distribution = cloudfront.Distribution(
            self,
            "Distribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=placeholder_origin,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
            ),
            domain_names=[config.domain_name],
            certificate=self.certificate,
            http_version=cloudfront.HttpVersion.HTTP2_AND_3,
            price_class=cloudfront.PriceClass.PRICE_CLASS_ALL,
        )

        cdk.CfnOutput(
            self,
            "CloudFrontDomainName",
            value=self.distribution.distribution_domain_name,
            description="CloudFront Distribution domain name",
            export_name=f"{config.stack_prefix}-cf-domain",
        )

        cdk.CfnOutput(
            self,
            "CloudFrontDistributionId",
            value=self.distribution.distribution_id,
            description="CloudFront Distribution ID",
            export_name=f"{config.stack_prefix}-cf-dist-id",
        )

        # --- Route53 A Record → CloudFront ---
        if not self.hosted_zone and config.has_hosted_zone:
            self.hosted_zone = route53.HostedZone.from_hosted_zone_attributes(
                self,
                "HostedZone",
                hosted_zone_id=config.hosted_zone_id,
                zone_name=config.hosted_zone_name,
            )

        if self.hosted_zone:
            route53.ARecord(
                self,
                "CloudFrontAliasRecord",
                zone=self.hosted_zone,
                record_name=config.domain_name,
                target=route53.RecordTarget.from_alias(
                    route53_targets.CloudFrontTarget(self.distribution)
                ),
            )

        cdk.CfnOutput(
            self,
            "DomainName",
            value=config.domain_name,
            description="Custom domain name",
            export_name=f"{config.stack_prefix}-domain-name",
        )
