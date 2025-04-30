from aws_cdk import (
    Stack,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_events as events,
    aws_events_targets as targets,
    Duration
)
from constructs import Construct

class InstanceRecoveryStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create Lambda function
        handler = lambda_.Function(
            self, "InstanceRecoveryHandler",
            runtime=lambda_.Runtime.PYTHON_3_9,
            code=lambda_.Code.from_asset("lambda"),
            handler="instance_recovery.handler",
            timeout=Duration.minutes(5),
            memory_size=256,
            environment={
                "LOG_LEVEL": "INFO"
            }
        )

        # Add IAM permissions
        handler.add_to_role_policy(iam.PolicyStatement(
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
        handler.add_to_role_policy(iam.PolicyStatement(
            actions=[
                "pricing:GetProducts"
            ],
            resources=["*"]
        ))

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
        rule.add_target(targets.LambdaFunction(handler))