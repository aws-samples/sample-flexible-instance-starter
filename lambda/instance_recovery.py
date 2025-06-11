import json
import logging
import os
import boto3
from botocore.exceptions import ClientError
from typing import List, Dict, Any
from datetime import datetime, timedelta

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))
region = os.environ.get('AWS_REGION')
dedup_table_name = os.environ.get('DEDUP_TABLE_NAME', 'StartInstancesFailures')
class EC2InstanceManager:
    def __init__(self):
        self.region = region
        self.ec2_client = boto3.client('ec2', region_name=region)
        self.ec2_resource = boto3.resource('ec2', region_name=region)
        self.pricing_client = boto3.client('pricing', region_name='us-east-1')  # Pricing API is only available in us-east-1
    
    def get_instance_details(self, instance_id: str) -> Dict[str, Any]:
        """Get the current instance details including vCPU and Memory."""
        instance = self.ec2_resource.Instance(instance_id)
        return self.get_instance_type_details(instance.instance_type)

    def get_instance_type_details(self, instance_type: str) -> Dict[str, Any]:
        """Get instance type details including vCPU, Memory and on-demand price."""
        instance_type_info = self.ec2_client.describe_instance_types(
            InstanceTypes=[instance_type]
        )['InstanceTypes'][0]
        
        price = self.get_ondemand_price(instance_type)
        
        return {
            'instance_type': instance_type,
            'instance_type_info': instance_type_info,
            'vcpu': instance_type_info['VCpuInfo']['DefaultVCpus'],
            'memory_mib': instance_type_info['MemoryInfo']['SizeInMiB'],
            'ondemand_price': price
        }
        
    def get_ondemand_price(self, instance_type: str) -> float:
        """Get the on-demand price for a Linux instance of the given type."""
        try:
            filters = [
                {'Type': 'TERM_MATCH', 'Field': 'operation', 'Value': 'RunInstances'},
                {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': instance_type},
                {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': self.region},
                {'Type': 'TERM_MATCH', 'Field': 'tenancy', 'Value': 'Shared'},
                {'Type': 'TERM_MATCH', 'Field': 'preInstalledSw', 'Value': 'NA'},
                {'Type': 'TERM_MATCH', 'Field': 'capacitystatus', 'Value': 'Used'}
            ]
            
            response = self.pricing_client.get_products(
                ServiceCode='AmazonEC2',
                Filters=filters
            )

            for price_str in response['PriceList']:
                price_data = eval(price_str)  # Convert string to dict
                terms = price_data['terms']['OnDemand']
                # Get the first price dimension from the first term
                term_id = list(terms.keys())[0]
                price_dimensions = terms[term_id]['priceDimensions']
                dimension_id = list(price_dimensions.keys())[0]
                return float(price_dimensions[dimension_id]['pricePerUnit']['USD'])

            logger.error(f"Error getting price for {instance_type}")  
            return float('inf')  # Return infinity if no price found
            
        except Exception as e:
            logger.error(f"Error getting price for {instance_type}: {e}")
            return float('inf')  # Return infinity if there's an error
            
    def get_compatible_instance_types(self, vcpu: int, memory_mib: int, instance_type_info: Dict[str, Any], original_instance_type: str) -> List[str]:
        """Get compatible instance types based on original instance properties and requirements, sorted by on-demand price."""
        original_architecture = instance_type_info['ProcessorInfo']['SupportedArchitectures'][0]
        is_burstable = original_instance_type.startswith('t')
        try:
            response = self.ec2_client.get_instance_types_from_instance_requirements(
                ArchitectureTypes=[original_architecture],
                VirtualizationTypes=['hvm'],
                InstanceRequirements={
                    'VCpuCount': {
                        'Min': vcpu,
                        'Max': 2 * vcpu
                    },
                    'MemoryMiB': {
                        'Min': memory_mib,
                        'Max': 2 * memory_mib
                    },
                    'BurstablePerformance': 'included' if is_burstable else 'excluded',
                    'InstanceGenerations': ['current'],
                    'BareMetal': 'included'
                }
                #MaxResults=0  # Adjust as needed
            )
            
            # Get instance types with their prices
            instance_types_with_prices = []
            for instance in response['InstanceTypes']:
                instance_type = instance['InstanceType']
                price = self.get_ondemand_price(instance_type)
                instance_types_with_prices.append((instance_type, price))
            
            # Sort by price and return just the instance types
            sorted_instances = sorted(instance_types_with_prices, key=lambda x: x[1]) # Sort by price (second element in tuple)
            return [instance_type for instance_type, _ in sorted_instances] # Return list of just the instance types
            
        except ClientError as e:
            logger.error(f"Error getting compatible instance types: {e}")
            return []

    def start_instance_with_fallback(self, instance_id: str) -> bool:
        """
        Attempt to start an EC2 instance, falling back to different instance types if needed.
        Only processes instances with the 'flexible' tag set to 'true'.
        Returns True if successfully started, False otherwise.
        """
        try:
            # Get current instance details
            instance = self.ec2_resource.Instance(instance_id)
            
            # Check if instance has the flexible tag set to true
            instance_tags = {tag['Key']: tag['Value'] for tag in instance.tags or []}
            if instance_tags.get('flexible', '').lower() != 'true':
                logger.info(f"Instance {instance_id} does not have flexible=true tag. Skipping recovery.")
                return False
                
            instance_details = self.get_instance_details(instance_id)
            tags = instance.create_tags(
                Tags=[
                    {
                        'Key': 'OriginalType',
                        'Value': instance_details['instance_type']
                    }
                ]
            )

            # First attempt to start with current instance type
            try:
                logger.info(f"Attempting to start instance {instance_id} with current type {instance_details['instance_type']}")
                instance.start()
                # instance.wait_until_running()
                logger.info(f"Successfully started instance {instance_id}")
                return True
            except ClientError as e:
                if 'InsufficientInstanceCapacity' not in str(e):
                    logger.error(f"Error starting instance: {e}")
                    return False
                else:
                    logger.info(f"Attempt with type {instance_details['instance_type']} resulted in InsufficientInstanceCapacity error")

            
            # If we get here, we need to try different instance types
            compatible_types = self.get_compatible_instance_types(
                instance_details['vcpu'],
                instance_details['memory_mib'],
                instance_type_info=instance_details['instance_type_info'],
                original_instance_type=instance_details['instance_type']
            )

            logger.info(f"Original instance type {instance_details['instance_type']}")
            logger.info(f"We will attempt to start the instance with the following instance types: {compatible_types}")
            
            for new_type in compatible_types:
                if new_type == instance_details['instance_type']:
                    continue  # Skip current type as we already tried it
                    
                try:
                    logger.info(f"Attempting to modify instance type to {new_type}")
                    instance.modify_attribute(
                        InstanceType={
                            'Value': new_type
                        }
                    )
                    
                    # Try to start with new instance type
                    instance.start()
                    # instance.wait_until_running()
                    logger.info(f"Successfully started instance {instance_id} with new type {new_type}")
                    return True
                except ClientError as e:
                    logger.info(f"Failed to start with instance type {new_type}: {e}")
                    continue
            
            logger.error(f"Failed to start instance {instance_id} with any compatible instance type")
            return False
                
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return False

def handler(event: Dict[Any, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler function"""
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
        
    instance_manager = EC2InstanceManager()
    
    # Process each instance separately
    for item in instance_ids:
        instance_id = item.get('instanceId')
        if not instance_id:
            continue          
        # Use instance id as the deduplication key
        # This will be consistent across retry attempts within the ttl (5 minutes)
        dedup_key = f"{item}"

    
        try:
            table.put_item(
                Item={
                    'dedupKey': dedup_key,
                    'timestamp': detail['eventTime'],
                    'ttl': int((datetime.now() + timedelta(minutes=5)).timestamp())
                },
                ConditionExpression='attribute_not_exists(dedupKey)'
            )
        
        except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            logger.info("This is a duplicate event. Skipping.")
            return {
                'statusCode': 200,
                'body': 'Duplicate event, skipped processing'
            }
        
        logger.info("This is a unique event, continuing processing...")

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