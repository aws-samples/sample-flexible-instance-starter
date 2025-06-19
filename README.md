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

Parameters can be configured in the `lambda/config.json`:
- memoryBufferPercentage: This parameter controls the memory allocation matching process. The tool compares the current instance specifications with potential new instances. By default, it selects new instances with memory equal to or greater than the current allocation. The buffer allows you to set a percentage that permits selecting instances with slightly less memory than the current instance. This provides more flexibility in instance selection while still meeting performance requirements. Default value: **5%**
- cpuManufacturers: Allows to specify the manufacture of the cpu on the target instances. Cpu from a different manufacture will be skipped. Default value **Intel**
- excludedInstanceTypes: The parameter allow to select entire families that will be skipped from the selection. You can use strings with one or more wild cards, represented by an asterisk (*), to exclude an instance family, type, size, or generation. The following are examples: m5.8xlarge, c5*.*, m5a.*, r*, *3*.
For example, if you specify c5*,Amazon EC2 will exclude the entire C5 instance family, which includes all C5a and C5n instance types. If you specify m5a.*, Amazon EC2 will exclude all the M5a instance types, but not the M5n instance types.
- bareMetal: Indicates whether bare metal instance types must be included, excluded, or required.
   - To include bare metal instance types, specify included.
   - To require only bare metal instance types, specify required.
   - To exclude bare metal instance types, specify excluded.
   Defalt value: **include**


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
