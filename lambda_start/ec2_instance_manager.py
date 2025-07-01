import json
import logging
import os
import boto3
import ast
from botocore.exceptions import ClientError
from typing import List, Dict, Any

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))


class EC2InstanceManager:
    def __init__(self, region, config_path):
        self.region = region
        self.ec2_client = boto3.client('ec2', region_name=region)
        self.ec2_resource = boto3.resource('ec2', region_name=region)
        self.pricing_client = boto3.client('pricing', region_name='us-east-1')  # Pricing API is only available in us-east-1
        self.ssm_client = boto3.client('ssm', region_name=region)
        self._price_cache = {}  # In-memory cache for instance type prices

        with open(config_path) as json_data:
            self.current_config = json.load(json_data)
    
    def get_instance_details(self, instance_id: str) -> Dict[str, Any]:
        """Get the current instance details including vCPU and Memory."""
        instance = self.ec2_resource.Instance(instance_id)
        return self.get_instance_type_details(instance.instance_type, instance.tags or [])

    def get_instance_type_details(self, instance_type: str, tags: List[Dict[str, str]]) -> Dict[str, Any]:
        """Get instance type details including vCPU, Memory and on-demand price."""
        instance_type_info = self.ec2_client.describe_instance_types(
            InstanceTypes=[instance_type]
        )['InstanceTypes'][0]
        
        price = self.get_ondemand_price(instance_type)
        
        return {
            'instance_type': instance_type,
            'tags': tags,
            'instance_type_info': instance_type_info,
            'vcpu': instance_type_info['VCpuInfo']['DefaultVCpus'],
            'memory_mib': instance_type_info['MemoryInfo']['SizeInMiB'],
            'ondemand_price': price
        }
        
    def get_ondemand_price(self, instance_type: str) -> float:
        """Get the on-demand price for a Linux instance of the given type."""
        # Check cache first
        if instance_type in self._price_cache:
            return self._price_cache[instance_type]

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
                price = float(price_dimensions[dimension_id]['pricePerUnit']['USD'])
                # Cache the price before returning
                self._price_cache[instance_type] = price
                return price

            logger.error(f"Error getting price for {instance_type}")  
            return float('inf')  # Return infinity if no price found
            
        except Exception as e:
            logger.error(f"Error getting price for {instance_type}: {e}")
            return float('inf')  # Return infinity if there's an error
        
    def get_flexible_configuration(self, parameter_arn):
        """
        Retrieve configuration from SSM Parameter Store with fallback logic:
        1. Try using the provided parameter_arn if available
        2. If that fails, try using '/flexible-instance-starter/default'
        3. If both fail, use self.current_config
        
        Args:
            parameter_arn: The ARN of the SSM parameter to retrieve
            
        Returns:
            dict: The configuration dictionary
        """
        def try_get_parameter(param_name):
            if not param_name:
                return None
                
            try:
                response = self.ssm_client.get_parameter(Name=param_name)
                parameter_value = response['Parameter']['Value']
                return json.loads(parameter_value)
            except json.JSONDecodeError as e:
                logger.error(f"Parameter {param_name} contains invalid JSON: {e}")
                return None
            except Exception as e:
                logger.error(f"Error retrieving parameter {param_name}: {e}")
                return None

        # First try with provided parameter_arn
        if parameter_arn:
            config = try_get_parameter(parameter_arn)
            if config:
                logger.info(f"Configuration retrieved from {parameter_arn}")
                return config
            logger.info(f"Failed to get configuration from {parameter_arn}, trying default parameter")

        # Then try with default parameter
        default_param = '/flexible-instance-starter/default'
        config = try_get_parameter(default_param)
        if config:
            logger.info(f"Configuration retrieved from {default_param}")
            return config
        
        logger.info(f"Failed to get configuration from {default_param}, using local config")
        return self.current_config
            
    def get_compatible_instance_types(self, instance_details: Dict[str, Any]) -> List[str]:
        """Get compatible instance types based on original instance properties and requirements, sorted by on-demand price."""

        vcpu = instance_details['vcpu']
        memory_mib = instance_details['memory_mib']
        instance_type_info=instance_details['instance_type_info']
        original_instance_type=instance_details['instance_type']
        tags=instance_details['tags']

        if original_instance_type.startswith('g') or original_instance_type.startswith('p') or original_instance_type.startswith('f') or original_instance_type.startswith('inf') or original_instance_type.startswith('trn'):
            return []

        original_architecture = instance_type_info['ProcessorInfo']['SupportedArchitectures'][0]
        is_burstable = original_instance_type.startswith('t')
        is_flex = '-flex' in original_instance_type

        # Get flexible configuration ARN from tags if present
        flexible_config_arn = next((tag['Value'] for tag in tags if tag['Key'] == 'FlexibleConfigurationArn'), None)
        current_config = self.get_flexible_configuration(flexible_config_arn)
        
        # Calculate minimum memory with buffer (if any)
        memoryBufferPercentage = current_config.get('memoryBufferPercentage', 0)
        if memoryBufferPercentage > 0:
            memory_buffer_multiplier = (100 - memoryBufferPercentage) / 100
            min_memory_mib = int(memory_mib * memory_buffer_multiplier)
            logger.info(f"Original memory: {memory_mib} MiB, Buffer: {memoryBufferPercentage}%, Min memory: {min_memory_mib} MiB")
        else:
            min_memory_mib = memory_mib
            logger.info(f"Original memory: {memory_mib} MiB, No buffer applied")
            
        try:
            instance_requirements = {
                'VCpuCount': {
                    'Min': vcpu,
                    'Max': current_config.get('maxCpuMultiplier', 2) * vcpu
                },
                'MemoryMiB': {
                    'Min': min_memory_mib,
                    'Max': current_config.get('maxMemoryMultiplier', 2) * memory_mib
                },
                'BurstablePerformance': 'included' if is_burstable or is_flex else 'excluded',
                'InstanceGenerations': ['current'],
                'BareMetal': current_config.get('bareMetal', 'included'),
                'CpuManufacturers': current_config.get('cpuManufacturers', ['amazon-web-services', 'amd', 'intel', 'apple']),
                'ExcludedInstanceTypes': current_config.get('excludedInstanceTypes', []),
            }

            localStorageBuffer = current_config.get('localStorageBufferPercentage', 0)
            if localStorageBuffer < 100 and instance_type_info.get('InstanceStorageInfo', {}).get('TotalSizeInGB', 0) > 0:
                instance_requirements['TotalLocalStorageGB'] = {
                    'Min': instance_type_info.get('InstanceStorageInfo', {}).get('TotalSizeInGB', 0) * (100 - localStorageBuffer) / 100, 
                }

            response = self.ec2_client.get_instance_types_from_instance_requirements(
                ArchitectureTypes=[original_architecture],
                VirtualizationTypes=['hvm'],
                InstanceRequirements=instance_requirements
                #MaxResults=0  # Adjust as needed
            )
            
            # Get instance types with their prices
            instance_types_with_prices = []
            for instance in response['InstanceTypes']:
                instance_type = instance['InstanceType']
                if is_flex or is_burstable or not is_flex and '-flex' not in instance_type:
                    price = self.get_ondemand_price(instance_type)
                    instance_types_with_prices.append((instance_type, price))
                    
            
            # Sort by price and return just the instance types
            sorted_instances = sorted(instance_types_with_prices, key=lambda x: x[1]) # Sort by price (second element in tuple)
            
            #compatible_types = [instance_type for instance_type, _ in sorted_instances]
            return [instance_type for instance_type, _ in sorted_instances] # Return list of just the instance types
        
            # Add original instance type at the end as fallback
            compatible_types.append(original_instance_type)
            
            return compatible_types


            
        except ClientError as e:
            logger.error(f"Error getting compatible instance types: {e}")
            return []

    def start_instance_with_fallback(self, instance_id: str) -> bool:
        """
        Attempt to start an EC2 instance, falling back to different instance types if needed.
        Only processes instances with the 'Flexible' tag set to 'true'.
        Returns True if successfully started, False otherwise.
        """
        try:
            # Get current instance details
            instance = self.ec2_resource.Instance(instance_id)
            
            # Check if instance has the flexible tag set to true
            instance_tags = {tag['Key']: tag['Value'] for tag in instance.tags or []}
            if instance_tags.get('Flexible', '').lower() != 'true':
                logger.info(f"Instance {instance_id} does not have Flexible=true tag. Skipping recovery.")
                return False
                
            instance_details = self.get_instance_details(instance_id)
            instance.create_tags(
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
            compatible_types = self.get_compatible_instance_types(instance_details)

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