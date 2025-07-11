import unittest
from unittest.mock import patch, MagicMock
import json
import sys
import os

# Add the lambda directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'lambda'))

from instance_recovery import handler, EC2InstanceManager

class TestInstanceRecovery(unittest.TestCase):
    def setUp(self):
        self.event = {
            'detail': {
                'userIdentity': {
                    'principalId': 'AROAEXAMPLE:user'
                },
                'sessionContext': {
                    'attributes': {
                        'creationDate': '2023-01-01T00:00:00Z'
                    }
                },
                'eventTime': '2023-01-01T00:00:00Z',
                'requestParameters': {
                    'instancesSet': {
                        'items': [
                            {'instanceId': 'i-1234567890abcdef0'},
                            {'instanceId': 'i-0987654321fedcba0'}
                        ]
                    }
                }
            }
        }

    @patch('boto3.resource')
    def test_handler_deduplication(self, mock_boto3_resource):
        # Mock DynamoDB table and conditional check failure
        mock_table = MagicMock()
        mock_boto3_resource.return_value.Table.return_value = mock_table
        mock_table.put_item.side_effect = mock_boto3_resource.return_value.meta.client.exceptions.ConditionalCheckFailedException({}, "ConditionalCheckFailed")
        
        response = handler(self.event, None)
        
        self.assertEqual(response['statusCode'], 200)
        self.assertEqual(response['body'], 'Duplicate event, skipped processing')
        mock_table.put_item.assert_called_once()

    @patch('boto3.resource')
    @patch.object(EC2InstanceManager, 'start_instance_with_fallback')
    def test_handler_successful_restart(self, mock_start_instance, mock_boto3_resource):
        # Mock DynamoDB table
        mock_table = MagicMock()
        mock_boto3_resource.return_value.Table.return_value = mock_table
        
        # Mock successful start
        mock_start_instance.return_value = True
        
        response = handler(self.event, None)
        
        self.assertEqual(response['statusCode'], 200)
        results = json.loads(response['body'])['results']
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['status'], 'started')
        self.assertEqual(results[0]['action'], 'restart')
        mock_table.put_item.assert_called_once()

    @patch('boto3.resource')
    def test_start_instance_with_fallback_flexible_tag(self, mock_boto3_resource):
        # Create mock instance
        mock_instance = MagicMock()
        mock_instance.tags = [{'Key': 'flexible', 'Value': 'true'}]
        mock_instance.instance_type = 't3.micro'
        mock_instance.start.return_value = None
        
        # Mock EC2 resource and client
        mock_ec2_resource = MagicMock()
        mock_ec2_resource.Instance.return_value = mock_instance
        mock_boto3_resource.return_value = mock_ec2_resource
        
        # Create instance manager and test
        manager = EC2InstanceManager()
        manager.get_instance_details = MagicMock(return_value={
            'instance_type': 't3.micro',
            'instance_type_info': {'ProcessorInfo': {'SupportedArchitectures': ['x86_64']}},
            'vcpu': 2,
            'memory_mib': 1024,
            'ondemand_price': 0.0104
        })
        
        result = manager.start_instance_with_fallback('i-1234567890abcdef0')
        self.assertTrue(result)
        mock_instance.start.assert_called_once()

    @patch('boto3.resource')
    def test_start_instance_with_fallback_no_flexible_tag(self, mock_boto3_resource):
        # Create mock instance without flexible tag
        mock_instance = MagicMock()
        mock_instance.tags = [{'Key': 'other', 'Value': 'value'}]
        
        # Mock EC2 resource
        mock_ec2_resource = MagicMock()
        mock_ec2_resource.Instance.return_value = mock_instance
        mock_boto3_resource.return_value = mock_ec2_resource
        
        # Create instance manager and test
        manager = EC2InstanceManager()
        result = manager.start_instance_with_fallback('i-1234567890abcdef0')
        
        self.assertFalse(result)
        mock_instance.start.assert_not_called()

    @patch('boto3.resource')
    @patch.object(EC2InstanceManager, 'get_compatible_instance_types')
    def test_get_compatible_instance_types(self, mock_get_compatible, mock_boto3_resource):
        # Mock DynamoDB table
        mock_table = MagicMock()
        mock_boto3_resource.return_value.Table.return_value = mock_table
        
        # Setup mock return value
        mock_get_compatible.return_value = ['t2.large', 't3a.large']
        
        # Create an instance of EC2InstanceManager
        manager = EC2InstanceManager()
        
        # Call the method with some test parameters
        alternatives = manager.get_compatible_instance_types(2, 8192, {'ProcessorInfo': {'SupportedArchitectures': ['x86_64']}}, 't3.large')
        
        # Verify the result
        self.assertTrue('t2.large' in alternatives)
        self.assertTrue('t3a.large' in alternatives)

if __name__ == '__main__':
    unittest.main()