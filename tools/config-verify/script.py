#!/usr/bin/env python3

import argparse
import boto3
import csv
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lambda_start.ec2_instance_manager import EC2InstanceManager

def generate_compatibility_csv(config_path):
    """
    Generate a CSV file listing all EC2 instance types and their compatible alternatives.
    
    Args:
        config_path (str): Path to the configuration file
    """
    # Initialize EC2 client and EC2InstanceManager
    current_region = os.environ.get('AWS_REGION') or os.environ.get('AWS_DEFAULT_REGION')
    if not current_region:
        ec2_client = boto3.client('ec2')
        current_region = ec2_client.meta.region_name
    else:
        ec2_client = boto3.client('ec2', region_name=current_region)

    print(f"Using region: {current_region}")
    manager = EC2InstanceManager(current_region, config_path)
    
    # Get all available instance types
    paginator = ec2_client.get_paginator('describe_instance_types')
    all_instance_types = []
    
    print("Fetching all available instance types...")
    for page in paginator.paginate():
        for instance_type in page['InstanceTypes']:
            all_instance_types.append(instance_type)
    
    # Sort instance types by name
    all_instance_types.sort(key=lambda x: x['InstanceType'])
    
    # Prepare CSV output path
    config_dir = os.path.dirname(config_path)
    config_name = os.path.splitext(os.path.basename(config_path))[0]
    output_file = os.path.join(config_dir, f"{config_name}_{current_region}_compatibility.csv")
    
    # Create CSV file
    print(f"Generating compatibility matrix to {output_file}...")
    with open(output_file, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Instance Type', 'Compatible Instance Types'])
        
        total = len(all_instance_types)
        for idx, instance_type_info in enumerate(all_instance_types, 1):
            instance_type = instance_type_info['InstanceType']
            print(f"Processing {instance_type} ({idx}/{total})...")
            
            try:
                # Get instance details
                instance_details = {
                    'instance_type': instance_type,
                    'instance_type_info': instance_type_info,
                    'vcpu': instance_type_info['VCpuInfo']['DefaultVCpus'],
                    'memory_mib': instance_type_info['MemoryInfo']['SizeInMiB']
                }
                
                # Get compatible types
                compatible_types = manager.get_compatible_instance_types(instance_details)
                
                # Write to CSV
                writer.writerow([instance_type, ', '.join(compatible_types)])
                
            except Exception as e:
                print(f"Error processing {instance_type}: {e}")
                writer.writerow([instance_type, f"Error: {str(e)}"])
    
    print(f"\nCompatibility matrix has been saved to: {output_file}")

def main():
    parser = argparse.ArgumentParser(description='Generate EC2 instance type compatibility matrix')
    parser.add_argument('config_path', help='Path to the configuration file')
    args = parser.parse_args()
    
    if not os.path.exists(args.config_path):
        print(f"Error: Configuration file not found at {args.config_path}")
        sys.exit(1)
        
    generate_compatibility_csv(args.config_path)

if __name__ == '__main__':
    main()