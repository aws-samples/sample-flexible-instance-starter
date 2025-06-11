from aws_cdk import (
    Stack,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_iam as iam,
    aws_events as events,
    aws_events_targets as targets,
    aws_dynamodb as dynamodb,
    Duration,
    RemovalPolicy
)
from constructs import Construct

class InstanceRecoveryStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Create DynamoDB table for deduplication
        dedup_table = dynamodb.Table(
            self, "StartInstancesFailuresTable",
            table_name="StartInstancesFailures",
            partition_key=dynamodb.Attribute(
                name="dedupKey",
                type=dynamodb.AttributeType.STRING
            ),
            time_to_live_attribute="ttl",
            removal_policy=RemovalPolicy.DESTROY,  # For easy cleanup in development
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST
        )

        # Create Lambda function
        start_handler = lambda_.Function(
            self, "InstanceRecoveryHandler",
            runtime=lambda_.Runtime.PYTHON_3_9,
            code=lambda_.Code.from_asset("lambda"),
            handler="instance_recovery.handler",
            timeout=Duration.minutes(5),
            memory_size=256,
            environment={
                "LOG_LEVEL": "INFO",
                "DEDUP_TABLE_NAME": dedup_table.table_name
            }
            log_retention=logs.RetentionDays.ONE_MONTH
        )

        # Add IAM permissions
        start_handler.add_to_role_policy(iam.PolicyStatement(
            actions=[
                "ec2:StartInstances",
                "ec2:DescribeInstances",
                "ec2:ModifyInstanceAttribute",
                "ec2:CreateTags",
                "ec2:DescribeTags",
                "ec2:DescribeInstanceTypes",
                "ec2:GetInstanceTypesFromInstanceRequirements"
            ],
            resources=["*"]
        ))
        start_handler.add_to_role_policy(iam.PolicyStatement(
            actions=[
                "pricing:GetProducts"
            ],
            resources=["*"]
        ))
        
        # Grant DynamoDB permissions to Lambda
        dedup_table.grant_read_write_data(start_handler)

        # Create CloudWatch Event Rule
        rule = events.Rule(
            self, "StartInstancesFailureRule",
            event_pattern=events.EventPattern(
                detail_type=["AWS API Call via CloudTrail"],
                detail={
                    "eventSource": ["ec2.amazonaws.com"],
                    "eventName": ["StartInstances"],
                    "errorCode": ["Server.InsufficientInstanceCapacity"],
                    "userIdentity": {
                        "sessionContext": {
                            "sessionIssuer": {
                                "userName": [ { "anything-but": { "prefix": [ self.stack_name] } } ]
                            }
                        }
                    }
                }
            )
        )

        # Add Lambda as target
        rule.add_target(targets.LambdaFunction(start_handler))

        # Create Stop Lambda function
        stop_handler = lambda_.Function(
            self, "InstanceStopHandler",
            runtime=lambda_.Runtime.PYTHON_3_9,
            code=lambda_.Code.from_asset("lambda-stop"),
            handler="instance_stop.handler",
            timeout=Duration.minutes(5),
            memory_size=256,
            environment={
                "LOG_LEVEL": "INFO"
            },
            log_retention=logs.RetentionDays.ONE_MONTH
        )

        # Add IAM permissions
        stop_handler.add_to_role_policy(iam.PolicyStatement(
            actions=[
                "ec2:DescribeInstances",
                "ec2:ModifyInstanceAttribute",
                "tag:UntagResource",
                "ec2:DeleteTags",
                "ec2:DescribeTags",
                "ec2:DescribeInstanceTypes"
            ],
            resources=["*"]
        ))

        # Create CloudWatch Event Rule
        stop_rule = events.Rule(
            self, "StopInstancesResetRule",
            event_pattern=events.EventPattern(
                detail_type=["AWS API Call via CloudTrail"],
                detail={
                    "eventSource": ["ec2.amazonaws.com"],
                    "eventName": ["StopInstances"]
                }
            )
        )

        # Add Lambda as target
        stop_rule.add_target(targets.LambdaFunction(stop_handler))
