"""DNS and ACM Certificate stack for OpenClaw SaaS

This stack handles:
- ACM certificate creation/import for custom domains
- Route53 DNS records (optional)

Note: This is OPTIONAL - only created if domain_name is configured.
The certificate is used by ALB Ingress Controller, not CloudFront.
"""
import aws_cdk as cdk
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_route53 as route53
from constructs import Construct


class DnsStack(cdk.Stack):
    """DNS and certificate management for custom domains"""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        config,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.certificate = None
        self.hosted_zone = None

        # Only create resources if domain is configured
        if not config.has_custom_domain:
            cdk.CfnOutput(
                self,
                "Status",
                value="No custom domain configured - skipping DNS/ACM setup",
            )
            return

        # Import or create ACM certificate
        if config.has_acm_cert:
            # Import existing certificate
            self.certificate = acm.Certificate.from_certificate_arn(
                self,
                "ImportedCertificate",
                certificate_arn=config.acm_cert_arn,
            )
            cert_arn_output = config.acm_cert_arn
        else:
            # Create new certificate with DNS validation
            # Note: This requires a hosted zone for DNS validation
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

        # Output certificate ARN
        cdk.CfnOutput(
            self,
            "CertificateArn",
            value=cert_arn_output,
            description="ACM Certificate ARN for ALB",
            export_name=f"{config.stack_prefix}-acm-cert-arn",
        )

        cdk.CfnOutput(
            self,
            "DomainName",
            value=config.domain_name,
            description="Custom domain name",
            export_name=f"{config.stack_prefix}-domain-name",
        )
