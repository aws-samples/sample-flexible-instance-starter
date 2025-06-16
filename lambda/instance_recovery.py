import json
import logging
import os
import boto3
import ast
from botocore.exceptions import ClientError
from typing import List, Dict, Any
from datetime import datetime, timedelta

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))
region = os.environ.get('AWS_REGION')
dedup_table_name = os.environ.get('DEDUP_TABLE_NAME', 'StartInstancesFailures')

# Define instance families to exclude from fallback options
# Set to empty list if no instances should be excluded
EXCLUDED_INSTANCE_FAMILIES = [
    # 'c7gd',    # Graviton-based compute optimized with local SSD
    # 'u-',
]

# Memory buffer percentage - allows instances with less memory than original
# Set to 0 for no buffer (exact memory match or higher)
# Example: se 10 for 10% buffer
MEMORY_BUFFER_PERCENTAGE = 0


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
                price_data = ast.literal_eval(price_str)  # Convert string to dict
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
            
            # Get instance types with their prices, filtering out excluded families
            instance_types_with_prices = []
            for instance in response['InstanceTypes']:
                instance_type = instance['InstanceType']
                
                # Check if instance type should be excluded
                should_exclude = False
                for excluded_family in EXCLUDED_INSTANCE_FAMILIES:
                    if instance_type.startswith(excluded_family):
                        should_exclude = True
                        logger.debug(f"Excluding instance type {instance_type} (matches excluded family: {excluded_family})")
                        break
                
                if should_exclude:
                    continue
                    
                price = self.get_ondemand_price(instance_type)
                instance_types_with_prices.append((instance_type, price))
            
            # Sort by price and return just the instance types
            sorted_instances = sorted(instance_types_with_prices, key=lambda x: x[1]) # Sort by price (second element in tuple)
            
            logger.info(f"Found {len(sorted_instances)} compatible instance types after filtering")
            return [instance_type for instance_type, _ in sorted_instances] # Return list of just the instance types
            
        except ClientError as e:
            logger.error(f"Error getting compatible instance types: {e}")
            return []


    def get_compatible_instance_types(self, vcpu: int, memory_mib: int, instance_type_info: Dict[str, Any], original_instance_type: str) -> List[str]:
        """Get compatible instance types based on original instance properties and requirements, sorted by on-demand price."""
        original_architecture = instance_type_info['ProcessorInfo']['SupportedArchitectures'][0]
        is_burstable = original_instance_type.startswith('t')
        
        # Calculate minimum memory with buffer (if any)
        if MEMORY_BUFFER_PERCENTAGE > 0:
            memory_buffer_multiplier = (100 - MEMORY_BUFFER_PERCENTAGE) / 100
            min_memory_mib = int(memory_mib * memory_buffer_multiplier)
            logger.info(f"Original memory: {memory_mib} MiB, Buffer: {MEMORY_BUFFER_PERCENTAGE}%, Min memory: {min_memory_mib} MiB")
        else:
            min_memory_mib = memory_mib
            logger.info(f"Original memory: {memory_mib} MiB, No buffer applied")
        
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
                        'Min': min_memory_mib,
                        'Max': 2 * memory_mib
                    },
                    'BurstablePerformance': 'included' if is_burstable else 'excluded',
                    'InstanceGenerations': ['current'],
                    'BareMetal': 'included'
                }
                #MaxResults=0  # Adjust as needed
            )
            
            # Get instance types with their prices, filtering out excluded families (if any)
            instance_types_with_prices = []
            excluded_count = 0
            
            for instance in response['InstanceTypes']:
                instance_type = instance['InstanceType']
                
                # Check if instance type should be excluded (only if exclusions are defined)
                should_exclude = False
                if EXCLUDED_INSTANCE_FAMILIES:  # Only check if list is not empty
                    for excluded_family in EXCLUDED_INSTANCE_FAMILIES:
                        if instance_type.startswith(excluded_family):
                            should_exclude = True
                            excluded_count += 1
                            logger.debug(f"Excluding instance type {instance_type} (matches excluded family: {excluded_family})")
                            break
                
                if should_exclude:
                    continue
                    
                price = self.get_ondemand_price(instance_type)
                instance_types_with_prices.append((instance_type, price))
            
            # Sort by price and return just the instance types
            sorted_instances = sorted(instance_types_with_prices, key=lambda x: x[1]) # Sort by price (second element in tuple)
            
            if excluded_count > 0:
                logger.info(f"Found {len(sorted_instances)} compatible instance types after excluding {excluded_count} instances")
            else:
                logger.info(f"Found {len(sorted_instances)} compatible instance types (no exclusions applied)")
                
            return [instance_type for instance_type, _ in sorted_instances] # Return list of just the instance types
            
        except ClientError as e:
            logger.error(f"Error getting compatible instance types: {e}")
            return []

        
    instance_manager = EC2InstanceManager()
    
    # Process each instance separately
    for item in instance_ids:
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