import json
import logging
import os
import boto3
import time
from botocore.exceptions import ClientError
from typing import Dict, Any
from datetime import datetime, timedelta
from ec2_instance_manager import EC2InstanceManager

# Timeout configuration
LAMBDA_TIMEOUT_SECONDS = 270  # 4 minutes 30 seconds


# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))
dedup_table_name = os.environ.get('DEDUP_TABLE_NAME', 'StartInstancesFailures')
region = os.environ.get('AWS_REGION')

script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, 'config.json')

def handler(event: Dict[Any, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler function"""
    start_time = time.time()

    logger.info(f"Received event: {json.dumps(event)}")
    
    detail = event.get('detail', {})
    request_parameters = detail.get('requestParameters', {})
    instance_ids = request_parameters.get('instancesSet', {}).get('items', [])
    if not instance_ids:
        logger.error("No instance IDs found in the event")
        return {'statusCode': 400, 'body': 'No instance IDs found'}
    
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(dedup_table_name)

    results = []
        
    instance_manager = EC2InstanceManager(region, config_path)
    
    # Process each instance separately
    for item in instance_ids:
        elapsed_time = time.time() - start_time
        if elapsed_time >= LAMBDA_TIMEOUT_SECONDS:
            logger.warning(f"Lambda timeout approaching ({elapsed_time:.2f}s). Stopping processing.")
            results.append({
                'message': f'Processing stopped due to timeout after {elapsed_time:.2f} seconds',
                'remaining_instances': len(instance_ids) - len([r for r in results if 'instanceId' in r])
            })
            break

        instance_id = item.get('instanceId')
        if not instance_id:
            continue 

        current_time = int(datetime.now().timestamp())
        try:
            response = table.get_item(Key={'dedupKey': instance_id})
            if 'Item' in response:
                if response['Item']['ttl'] > current_time:
                    logger.info(f"{response['Item']['ttl']}, {current_time}")
                    logger.info(f"Duplicate event detected for instance {instance_id}. Skipping.")
                    continue
                else: 
                    logger.info(f"Old event detected for instance {instance_id}. Processing and updating TTL.")
        except ClientError as e:
            logger.error(f"Error checking DynamoDB for existing event: {e}")
            continue



        # Use instance id as the deduplication key
        # This will be consistent across retry attempts within the ttl (5 minutes)
        dedup_key = instance_id

    
        try:
            table.put_item(
                Item={
                    'dedupKey': dedup_key,
                    'timestamp': detail['eventTime'],
                    'ttl': int((datetime.now() + timedelta(minutes=5)).timestamp())
                }
            )
        
        except ClientError as e:
            logger.error(f"Error putting new event into DynamoDB: {e}")
            continue
        
        logger.info("TTL set, continuing processing...")

        try:
            # Try to start the instance
            if instance_manager.start_instance_with_fallback(instance_id):
                results.append({
                    'instanceId': instance_id,
                    'status': 'started',
                    'action': 'restart'
                })
                continue

            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Processing complete',
                    'results': results
                })
            }
        
        except Exception as e:
            logger.error(f"Error processing event: {str(e)}")
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'message': 'Error processing event',
                    'error': str(e)
                })
            }