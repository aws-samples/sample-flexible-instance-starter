# EC2 Instance Recovery Automation

This CDK project implements an automation solution that handles EC2 instance start failures due to insufficient capacity. When a StartInstances API call fails with "Server.InsufficientInstanceCapacity" error, the automation:

1. Splits multi-instance requests into individual StartInstances calls
2. Attempts to start each instance individually
3. If the start fails again, attempts to modify the instance type to a comparable alternative
4. Retries the start operation with the new instance type

When the instances are stopped, the instance type is reverted to the original one.

Only instances with the Tag flexible=true are managed by this automation.

## Architecture

The solution uses:
- CloudWatch Events Rule to monitor CloudTrail events for StartInstances failures
- Lambda function to handle the recovery logic
- IAM roles and permissions for the recovery Lambda function
- Instance type mapping for finding comparable instance types
- CloudWatch Events Rule to monitor CloudTrail events for StopInstances events
- Lambda function to handle the revert logic upon instance stop event
- IAM roles and permissions for the stop Lambda function

![iamge](docs/architecture.png)

## Prerequisites

- Python 3.9 or later
- AWS CDK CLI
- AWS credentials configured

## Setup

1. Create and activate a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Deploy the stack:
```bash
cdk deploy
```

## How it works

### StartInstances workflow
1. The CloudWatch Events Rule monitors CloudTrail for EC2 StartInstances API calls that fail with "Server.InsufficientInstanceCapacity"
2. When a matching event is detected, the Lambda function is triggered
3. The function:
   - Extracts the instance IDs from the failed request
   - Check if the instances are managed by this automation
   - Attempts to start each instance individually
   - If the start fails, looks up comparable instance types
   - Modifies the instance type and retries the start operation
   - Adds a Tag on the EC2 instance with the original instance type
   - Logs all actions and results

### StopInstances workflow
1. The CloudWatch Events Rule monitors CloudTrail for EC2 StopInstances API calls
2. When a matching event is detected, the Lambda function is triggered
3. The function:
   - Extracts the instance IDs from the request
   - Check if the instances are managed by this automation
   - Waits that the instances are fully stopped
   - Revert the instance type to the original one
   - Remoevs the OriginalType Tag on the EC2 instance
   - Logs all actions and results

## Configuration

The instance type mappings can be modified in the Lambda function code (`lambda/instance_recovery.py`). The current mappings include common EC2 instance families, but you can add more based on your needs.

## Monitoring

The solution logs all actions to CloudWatch Logs. You can monitor:
- Instance start attempts
- Instance type modifications
- Success/failure of operations

## Cleanup

To remove all resources:
```bash
cdk destroy
```
