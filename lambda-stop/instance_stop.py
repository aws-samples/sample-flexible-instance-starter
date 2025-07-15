import json
import logging
import os
import boto3
from botocore.exceptions import ClientError
from typing import Dict, Any
from botocore.config import Config
import time

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))
region = os.environ.get('AWS_REGION')

# Create a custom configuration for User Agent
custom_config = Config(
    user_agent_extra='FlexibleInstanceStarter/1.0'
)

class EC2InstanceManager:
    def __init__(self):
        self.region = region
        self.ec2_client = boto3.client('ec2', region_name=region, config=custom_config)
        self.ec2_resource = boto3.resource('ec2', region_name=region, config=custom_config)

    def _is_valid_instance_type(self, instance_type: str) -> bool:
        """
        Validate if the given instance type is a valid EC2 instance type.
        
        Args:
            instance_type (str): The instance type to validate
            
        Returns:
            bool: True if the instance type is valid, False otherwise
        """
        try:
            # Use describe_instance_types to check if the instance type exists
            response = self.ec2_client.describe_instance_types(
                InstanceTypes=[instance_type]
            )
            return len(response['InstanceTypes']) > 0
        except ClientError as e:
            if e.response['Error']['Code'] == 'InvalidInstanceType':
                return False
            raise

    def wait_for_instance_stopped(self, instance_id: str, max_attempts: int = 30) -> tuple[bool, str]:
        """
        Wait for an instance to reach the 'stopped' state.
        
        Args:
            instance_id (str): The ID of the EC2 instance
            max_attempts (int): Maximum number of attempts to check instance state
            
        Returns:
            bool: True if instance reached stopped state, False otherwise
        """
        instance = self.ec2_resource.Instance(instance_id)
        attempt = 0
        
        while attempt < max_attempts:
            attempt += 1
            instance.reload()  # Get the latest instance state
            current_state = instance.state['Name']
            logger.info(f"Instance {instance_id} state check attempt {attempt}/{max_attempts}: {current_state}")
            
            if current_state == 'stopped':
                logger.info(f"Instance {instance_id} has reached stopped state")
                return True, current_state
            elif current_state == 'terminated':
                logger.info(f"Instance {instance_id} is terminated, no action needed")
                return False, current_state
            elif current_state in ['shutting-down', 'pending']:
                logger.info(f"Instance {instance_id} is in invalid state for modification: {current_state}")
                return False, current_state
            elif current_state == 'stopping':
                logger.info(f"Instance {instance_id} is still stopping, waiting...")
            else:
                logger.warning(f"Instance {instance_id} in unexpected state: {current_state} {attempt} {max_attempts}")
                
            # Wait 10 seconds before next check
            time.sleep(10)
            
        logger.error(f"Timeout after {max_attempts} attempts waiting for instance {instance_id} to stop")
        return False, current_state

    def reset_instance_type(self, instance_id: str) -> Dict[str, str]:
        """
        Reset instance type if it was changed by automation.
        
        Args:
            instance_id (str): The ID of the EC2 instance
            
        Returns:
            Dict[str, str]: Dictionary containing instance details and changes made
        """
        try:
            # Get the EC2 instance
            instance = self.ec2_resource.Instance(instance_id)
            
            # Get instance tags
            tags = {tag['Key']: tag['Value'] for tag in instance.tags or []}
            flexible = tags.get('Flexible', 'false').lower()
            
            # Log instance details and flexibility status
            logger.info(f"Processing instance {instance_id}: {instance.instance_type}")
            logger.info(f"Flexible flag: {flexible}")

            # Check if instance is flexible and has original type
            if flexible == 'true':
                if 'OriginalType' in tags:
                    original_type = tags['OriginalType']
                    current_type = instance.instance_type
                    
                    logger.info(f"Instance {instance_id} is flexible and has OriginalType tag")
                    logger.info(f"Original instance type: {original_type}")
                    logger.info(f"Current instance type: {current_type}")
                    
                    # Validate the original instance type
                    if not self._is_valid_instance_type(original_type):
                        logger.error(f"Invalid instance type in OriginalType tag: {original_type}")
                        return None
                    
                    # Only modify if types are different
                    if original_type != current_type:
                        logger.info(f"Resetting instance {instance_id} type from {current_type} to {original_type}")
                        
                        # Wait for instance to be in stopped state before modifying
                        stopped, current_state = self.wait_for_instance_stopped(instance_id)
                        if not stopped and current_state != 'terminated':
                            logger.error(f"Instance {instance_id} did not reach stopped state in time")
                            return None
                            
                        # Update instance type to original
                        instance.modify_attribute(
                            InstanceType={'Value': original_type}
                        )
                        
                        # Remove OriginalType tag
                        instance.delete_tags(
                            Tags=[{'Key': 'OriginalType'}]
                        )
                        logger.info(f"Successfully reset instance {instance_id} type and removed OriginalType tag")
                    else:
                        logger.info(f"Instance {instance_id} already has the original type {original_type}, no change needed")
                    
                    return {
                        'instance_id': instance_id,
                        'instance_type': current_type,
                        'new_instance_type': original_type
                    }
                else:
                    logger.info(f"Instance {instance_id} is flexible and but hasn't OriginalType tag")
            else:
                logger.info(f"Instance {instance_id} is not flexible")
            
            return None
            
        except ClientError as e:
            logger.error(f"Error resetting instance type for {instance_id}: {str(e)}")
            raise


def handler(event: Dict[Any, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler function"""
    logger.info(f"Received event: {json.dumps(event)}")
    
    try:
        # Extract instance IDs from the failed StopInstances call
        detail = event.get('detail', {})
        instance_id = detail.get('instance-id')
        
        if not instance_id:
            logger.error("No instance ID found in the event")
            return {'statusCode': 400, 'body': 'No instance ID found'}

        results = []
        
        instance_manager = EC2InstanceManager()
                
        # Reset Instance Type if it was changed by this automation
        result = instance_manager.reset_instance_type(instance_id)
        if result:
            results.append({
                'instanceId': result.get('instance_id'),
                'instanceType': result.get('instance_type'),
                'newInstanceType': result.get('new_instance_type')
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