"""SQS stack for OpenClaw SaaS"""
import aws_cdk as cdk
from aws_cdk import aws_sqs as sqs
from constructs import Construct


class SqsStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        config,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Dead Letter Queue for failed usage events
        self.dlq = sqs.Queue(
            self,
            "UsageEventsDlq",
            queue_name=f"{config.resource_prefix}-usage-events-dlq",
            retention_period=cdk.Duration.days(config.sqs_retention_period_days),
            encryption=sqs.QueueEncryption.SQS_MANAGED,
        )

        # Main usage events queue
        self.usage_queue = sqs.Queue(
            self,
            "UsageEventsQueue",
            queue_name=f"{config.resource_prefix}-usage-events",
            visibility_timeout=cdk.Duration.seconds(config.sqs_visibility_timeout),
            retention_period=cdk.Duration.days(config.sqs_retention_period_days),
            receive_message_wait_time=cdk.Duration.seconds(config.sqs_receive_wait_time),
            encryption=sqs.QueueEncryption.SQS_MANAGED,
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=config.sqs_max_receive_count,
                queue=self.dlq,
            ),
        )

        # Outputs
        cdk.CfnOutput(
            self,
            "UsageQueueUrl",
            value=self.usage_queue.queue_url,
            description="Usage events queue URL",
            export_name=f"{config.stack_prefix}-usage-queue-url",
        )

        cdk.CfnOutput(
            self,
            "UsageQueueArn",
            value=self.usage_queue.queue_arn,
            description="Usage events queue ARN",
            export_name=f"{config.stack_prefix}-usage-queue-arn",
        )

        cdk.CfnOutput(
            self,
            "UsageQueueName",
            value=self.usage_queue.queue_name,
            description="Usage events queue name",
            export_name=f"{config.stack_prefix}-usage-queue-name",
        )

        cdk.CfnOutput(
            self,
            "DlqArn",
            value=self.dlq.queue_arn,
            description="Dead letter queue ARN",
            export_name=f"{config.stack_prefix}-dlq-arn",
        )
