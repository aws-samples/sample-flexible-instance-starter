import json
import logging
import os
import boto3
from typing import List, Dict, Any

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

ec2 = boto3.client('ec2')

# Instance type mapping for comparable instances
INSTANCE_TYPE_MAPPING = {
    't3.': ['t2.', 't3a.'],
    'm5.': ['m4.', 'm5a.', 'm5n.'],
    'c5.': ['c4.', 'c5a.', 'c5n.'],
    'r5.': ['r4.', 'r5a.', 'r5n.'],
    'i3.': ['i3en.'],
    # Add more mappings as needed
}

def get_instance_size(instance_type: str) -> str:
    """Extract the size part of the instance type (e.g., 'large' from 't3.large')"""
    return instance_type.split('.')[-1]

def get_instance_family(instance_type: str) -> str:
    """Extract the family part of the instance type (e.g., 't3' from 't3.large')"""
    return instance_type.split('.')[0]

def get_alternative_instance_types(current_type: str) -> List[str]:
    """Get list of alternative instance types based on the current type"""
    size = get_instance_size(current_type)
    family_prefix = current_type.split('.')[0] + '.'
    
    alternative_types = []
    for prefix, alternatives in INSTANCE_TYPE_MAPPING.items():
        if current_type.startswith(prefix):
            for alt_prefix in alternatives:
                alternative_types.append(f"{alt_prefix}{size}")
    
    return alternative_types

def modify_instance_type(instance_id: str, new_type: str) -> bool:
    """Modify the instance type and return success status"""
    try:
        ec2.modify_instance_attribute(
            InstanceId=instance_id,
            InstanceType={'Value': new_type}
        )
        logger.info(f"Successfully modified instance {instance_id} to type {new_type}")
        return True
    except Exception as e:
        logger.error(f"Failed to modify instance {instance_id} to type {new_type}: {str(e)}")
        return False

def try_start_instance(instance_id: str) -> bool:
    """Attempt to start an instance and return success status"""
    try:
        ec2.start_instances(InstanceIds=[instance_id])
        logger.info(f"Successfully started instance {instance_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to start instance {instance_id}: {str(e)}")
        return False

def handler(event: Dict[Any, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler function"""
    logger.info(f"Received event: {json.dumps(event)}")
    
    try:
        # Extract instance IDs from the failed StartInstances call
        detail = event.get('detail', {})
        request_parameters = detail.get('requestParameters', {})
        instance_ids = request_parameters.get('instancesSet', {}).get('items', [])
        
        if not instance_ids:
            logger.error("No instance IDs found in the event")
            return {'statusCode': 400, 'body': 'No instance IDs found'}

        results = []
        
        # Process each instance separately
        for item in instance_ids:
            instance_id = item.get('instanceId')
            if not instance_id:
                continue
                
            # First attempt: Try to start the instance
            if try_start_instance(instance_id):
                results.append({
                    'instanceId': instance_id,
                    'status': 'started',
                    'action': 'restart'
                })
                continue
                
            # If start fails, get current instance type
            try:
                instance_info = ec2.describe_instances(InstanceIds=[instance_id])
                current_type = instance_info['Reservations'][0]['Instances'][0]['InstanceType']
            except Exception as e:
                logger.error(f"Failed to get instance info for {instance_id}: {str(e)}")
                continue
                
            # Get alternative instance types
            alternative_types = get_alternative_instance_types(current_type)
            
            # Try each alternative type
            success = False
            for new_type in alternative_types:
                if modify_instance_type(instance_id, new_type):
                    if try_start_instance(instance_id):
                        results.append({
                            'instanceId': instance_id,
                            'status': 'started',
                            'action': 'type_modified',
                            'oldType': current_type,
                            'newType': new_type
                        })
                        success = True
                        break
                    
            if not success:
                results.append({
                    'instanceId': instance_id,
                    'status': 'failed',
                    'action': 'all_attempts_failed'
                })
                
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