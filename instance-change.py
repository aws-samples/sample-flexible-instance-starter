import boto3
import time
from botocore.exceptions import ClientError
from typing import List, Dict, Any

class EC2InstanceManager:
    def __init__(self, region: str = 'us-east-1'):
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

            print(f"Error getting price for {instance_type}")  
            return float('inf')  # Return infinity if no price found
            
        except Exception as e:
            print(f"Error getting price for {instance_type}: {e}")
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
                    'BurstablePerformance': 'included' if is_burstable else 'included',
                    'InstanceGenerations': ['current']
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
            sorted_instances = sorted(instance_types_with_prices, key=lambda x: x[1])
            return sorted_instances
            
        except ClientError as e:
            print(f"Error getting compatible instance types: {e}")
            return []

    def start_instance_with_fallback(self, instance_id: str) -> bool:
        """
        Attempt to start an EC2 instance, falling back to different instance types if needed.
        Returns True if successfully started, False otherwise.
        """
        try:
            # Get current instance details
            instance_details = self.get_instance_details(instance_id)
            instance = self.ec2_resource.Instance(instance_id)
            
            # First attempt to start with current instance type
            try:
                print(f"Attempting to start instance {instance_id} with current type {instance_details['instance_type']}")
                instance.start()
                instance.wait_until_running()
                print(f"Successfully started instance {instance_id}")
                return True
            except ClientError as e:
                if 'InsufficientInstanceCapacity' not in str(e):
                    print(f"Error starting instance: {e}")
                    return False
            
            # If we get here, we need to try different instance types
            compatible_types = self.get_compatible_instance_types(
                instance_details['vcpu'],
                instance_details['memory_mib']
            )
            
            for new_type in compatible_types:
                if new_type == instance_details['instance_type']:
                    continue  # Skip current type as we already tried it
                    
                try:
                    print(f"Attempting to modify instance type to {new_type}")
                    instance.modify_attribute(
                        InstanceType={
                            'Value': new_type
                        }
                    )
                    
                    # Try to start with new instance type
                    instance.start()
                    instance.wait_until_running()
                    print(f"Successfully started instance {instance_id} with new type {new_type}")
                    return True
                except ClientError as e:
                    print(f"Failed to start with instance type {new_type}: {e}")
                    continue
            
            print(f"Failed to start instance {instance_id} with any compatible instance type")
            return False
                
        except Exception as e:
            print(f"Unexpected error: {e}")
            return False

def main():
    import argparse
    
    # Set up argument parser
    parser = argparse.ArgumentParser(description='EC2 Instance Manager')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--instance-id', help='The ID of the EC2 instance')
    group.add_argument('--instance-type', help='The EC2 instance type (e.g., t2.micro)')
    parser.add_argument('--region', default='us-east-1', help='AWS region (default: us-east-1)')
    
    args = parser.parse_args()
    
    # Initialize manager with provided region
    instance_manager = EC2InstanceManager(region=args.region)
    
    # Get instance details and compatible types based on input type
    if args.instance_id:
        instance_details = instance_manager.get_instance_details(args.instance_id)
        print(f"Instance details for {args.instance_id}:")
    else:
        instance_details = instance_manager.get_instance_type_details(args.instance_type)
        print(f"Instance type details for {args.instance_type}:")
    
    print(instance_details)
    compatible_types = instance_manager.get_compatible_instance_types(
        instance_details['vcpu'],
        instance_details['memory_mib'],
        instance_type_info=instance_details['instance_type_info'],
        original_instance_type=instance_details['instance_type']
    )
    print(f"\nCompatible instance types in region {args.region}:")
    print(compatible_types)

'''
    success = instance_manager.start_instance_with_fallback(instance_id)
    if success:
        print("Instance successfully started")
    else:
        print("Failed to start instance")
'''    

if __name__ == '__main__':
    main()




