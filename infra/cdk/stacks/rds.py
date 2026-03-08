"""RDS stack for OpenClaw SaaS"""
import aws_cdk as cdk
from aws_cdk import aws_rds as rds
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct


class RdsStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.IVpc,
        eks_security_group: ec2.ISecurityGroup,
        config,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Security group for RDS
        self.db_security_group = ec2.SecurityGroup(
            self,
            "DbSecurityGroup",
            vpc=vpc,
            description="Security group for OpenClaw SaaS PostgreSQL database",
            allow_all_outbound=True,
        )

        # Allow EKS nodes to connect to RDS
        self.db_security_group.add_ingress_rule(
            peer=eks_security_group,
            connection=ec2.Port.tcp(5432),
            description="Allow PostgreSQL access from EKS nodes",
        )

        # Subnet group for RDS (private subnets only)
        subnet_group = rds.SubnetGroup(
            self,
            "DbSubnetGroup",
            description="Subnet group for OpenClaw SaaS PostgreSQL",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
        )

        # PostgreSQL parameter group
        parameter_group = rds.ParameterGroup(
            self,
            "DbParameterGroup",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_16
            ),
            description="Parameter group for OpenClaw SaaS PostgreSQL 16",
            parameters={
                "shared_preload_libraries": "pg_stat_statements",
                "log_statement": "all",
                "log_min_duration_statement": "1000",  # Log queries > 1s
            },
        )

        # Create PostgreSQL instance
        self.db_instance = rds.DatabaseInstance(
            self,
            "Database",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_16
            ),
            instance_type=ec2.InstanceType(config.db_instance_class),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[self.db_security_group],
            subnet_group=subnet_group,
            parameter_group=parameter_group,
            database_name=config.db_name,
            credentials=rds.Credentials.from_generated_secret(
                username="openclaw_admin",
                secret_name=f"{config.resource_prefix}-db-credentials",
            ),
            allocated_storage=config.db_allocated_storage,
            max_allocated_storage=config.db_max_allocated_storage,
            storage_type=rds.StorageType.GP3,
            storage_encrypted=True,
            multi_az=False,  # Single AZ for cost savings in dev
            publicly_accessible=False,
            deletion_protection=False,  # Allow deletion in dev/test
            backup_retention=cdk.Duration.days(7),
            preferred_backup_window="03:00-04:00",
            preferred_maintenance_window="mon:04:00-mon:05:00",
            removal_policy=cdk.RemovalPolicy.SNAPSHOT,  # Take snapshot on delete
            auto_minor_version_upgrade=True,
        )

        # Outputs
        cdk.CfnOutput(
            self,
            "DbEndpoint",
            value=self.db_instance.db_instance_endpoint_address,
            description="RDS PostgreSQL endpoint address",
            export_name=f"{config.stack_prefix}-db-endpoint",
        )

        cdk.CfnOutput(
            self,
            "DbPort",
            value=self.db_instance.db_instance_endpoint_port,
            description="RDS PostgreSQL port",
            export_name=f"{config.stack_prefix}-db-port",
        )

        cdk.CfnOutput(
            self,
            "DbSecretArn",
            value=self.db_instance.secret.secret_arn,
            description="ARN of the Secrets Manager secret containing DB credentials",
            export_name=f"{config.stack_prefix}-db-secret-arn",
        )

        cdk.CfnOutput(
            self,
            "DbName",
            value=config.db_name,
            description="Database name",
            export_name=f"{config.stack_prefix}-db-name",
        )
