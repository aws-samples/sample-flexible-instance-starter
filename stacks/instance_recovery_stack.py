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
from cdk_nag import NagSuppressions

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
        
        # Create a custom role for the start lambda function
        start_handler_role = iam.Role(
            self, "InstanceRecoveryLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com")
        )
        start_handler_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            resources=["arn:aws:logs:" + self.region + ":" + self.account + ":log-group:/aws/lambda/InstanceRecoveryHandler:*"]
        ))

        # Add SSM Parameter Store permissions
        start_handler_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "ssm:GetParameter"
            ],
            resources=[f"arn:aws:ssm:{self.region}:*:parameter/flexible-instance-starter/*"]
        ))

        # Create a log group for the recovery handler
        start_handler_loggroup = logs.LogGroup(
            self, "InstanceRecoveryHandlerLogGroup",
            log_group_name="/aws/lambda/InstanceRecoveryHandler",
            retention=logs.RetentionDays.ONE_MONTH
        )

        # Create Lambda function
        start_handler = lambda_.Function(
            self, "InstanceRecoveryHandler",
            runtime=lambda_.Runtime.PYTHON_3_13,
            code=lambda_.Code.from_asset("lambda_start"),
            handler="instance_recovery.handler",
            timeout=Duration.minutes(5),
            memory_size=256,
            role=start_handler_role,
            environment={
                "LOG_LEVEL": "INFO",
                "DEDUP_TABLE_NAME": dedup_table.table_name
            },
            log_group=start_handler_loggroup
        )

        # Add IAM permissions
        # Actions that require Flexible=true tag
        start_handler.add_to_role_policy(iam.PolicyStatement(
            actions=[
                "ec2:StartInstances",
            ],
            resources=[f"arn:aws:ec2:{self.region}:{self.account}:instance/*"],
            conditions={
                "StringEquals": {
                    "aws:ResourceTag/Flexible": "true"
                }
            }
        ))
        # Separate policy for ModifyInstanceAttribute with instanceType restriction
        start_handler.add_to_role_policy(iam.PolicyStatement(
            actions=[
                "ec2:ModifyInstanceAttribute",
            ],
            resources=[f"arn:aws:ec2:{self.region}:{self.account}:instance/*"],
            conditions={
                "StringEquals": {
                    "aws:ResourceTag/Flexible": "true"
                }
            }
        ))
        # Specific permission for creating only OriginalType tag
        start_handler.add_to_role_policy(iam.PolicyStatement(
            actions=[
                "ec2:CreateTags"
            ],
            resources=[f"arn:aws:ec2:{self.region}:{self.account}:instance/*"],
            conditions={
                "StringEquals": {
                    "aws:ResourceTag/Flexible": "true"
                },
                "ForAllValues:StringEquals": {
                    "aws:TagKeys": ["OriginalType"]
                }
            }
        ))
        # Actions that don't require tag condition
        start_handler.add_to_role_policy(iam.PolicyStatement(
            actions=[
                "ec2:DescribeInstances",
                "ec2:DescribeTags",
                "ec2:DescribeInstanceTypes",
                "ec2:GetInstanceTypesFromInstanceRequirements"
            ],
            resources=["*"],
            conditions={
                "StringEquals": {
                    "ec2:Region": self.region
                }
            }
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

        # Create a custom role for the start lambda function
        stop_handler_role = iam.Role(
            self, "InstanceStopLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com")
        )
        stop_handler_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            resources=["arn:aws:logs:" + self.region + ":" + self.account + ":log-group:/aws/lambda/InstanceStopHandler:*"]
        ))

        # Create a log group for the stop handler
        stop_handler_loggroup = logs.LogGroup(
            self, "InstanceStopHandlerLogGroup",
            log_group_name="/aws/lambda/InstanceStopHandler",
            retention=logs.RetentionDays.ONE_MONTH
        )

        # Create Stop Lambda function
        stop_handler = lambda_.Function(
            self, "InstanceStopHandler",
            runtime=lambda_.Runtime.PYTHON_3_13,
            code=lambda_.Code.from_asset("lambda-stop"),
            handler="instance_stop.handler",
            timeout=Duration.minutes(5),
            role=stop_handler_role,
            memory_size=256,
            environment={
                "LOG_LEVEL": "INFO"
            },
            log_group=stop_handler_loggroup
        )

        # Add IAM permissions
        # Actions that require Flexible=true tag
        stop_handler.add_to_role_policy(iam.PolicyStatement(
            actions=[
                "ec2:ModifyInstanceAttribute"
            ],
            resources=[f"arn:aws:ec2:{self.region}:{self.account}:instance/*"],
            conditions={
                "StringEquals": {
                    "aws:ResourceTag/Flexible": "true"
                }
            }
        ))
        # Specific permission for deleting only OriginalType tag
        stop_handler.add_to_role_policy(iam.PolicyStatement(
            actions=[
                "ec2:DeleteTags"
            ],
            resources=[f"arn:aws:ec2:{self.region}:{self.account}:instance/*"],
            conditions={
                "StringEquals": {
                    "aws:ResourceTag/Flexible": "true"
                },
                "ForAllValues:StringEquals": {
                    "aws:TagKeys": ["OriginalType"]
                }
            }
        ))
        # Actions that don't require tag condition
        stop_handler.add_to_role_policy(iam.PolicyStatement(
            actions=[
                "ec2:DescribeInstances",
                "ec2:DescribeTags",
                "ec2:DescribeInstanceTypes"
            ],
            resources=["*"],
            conditions={
                "StringEquals": {
                    "ec2:Region": self.region
                }
            }
        ))

        # Create CloudWatch Event Rule
        stop_rule = events.Rule(
            self, "StopInstancesResetRule",
            event_pattern=events.EventPattern(
                detail_type=["EC2 Instance State-change Notification"],
                detail={
                    "state": ["stopped"]
                }
            )
        )

        # Add Lambda as target
        stop_rule.add_target(targets.LambdaFunction(stop_handler))
        NagSuppressions.add_stack_suppressions(
            self,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "This is a wildcard policy for the Lambda function to allow access to the specified EC2 actions on all resources. This is required for the Lambda function to work properly."
                }
            ]
        )
