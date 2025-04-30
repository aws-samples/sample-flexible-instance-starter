# EC2 Instance Recovery Automation

This CDK project implements an automation solution that handles EC2 instance start failures due to insufficient capacity. When a StartInstances API call fails with "Server.InsufficientInstanceCapacity" error, the automation:

1. Splits multi-instance requests into individual StartInstances calls
2. Attempts to start each instance individually
3. If the start fails again, attempts to modify the instance type to a comparable alternative
4. Retries the start operation with the new instance type

## Architecture

The solution uses:
- CloudWatch Events Rule to monitor CloudTrail events for StartInstances failures
- Lambda function to handle the recovery logic
- IAM roles and permissions for the Lambda function
- Instance type mapping for finding comparable instance types

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

1. The CloudWatch Events Rule monitors CloudTrail for StartInstances API calls that fail with "Server.InsufficientInstanceCapacity"
2. When a matching event is detected, the Lambda function is triggered
3. The function:
   - Extracts the instance IDs from the failed request
   - Attempts to start each instance individually
   - If the start fails, looks up comparable instance types
   - Modifies the instance type and retries the start operation
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
