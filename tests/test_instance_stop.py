import unittest
from unittest.mock import patch, MagicMock
import json
import sys
import os

# Add the lambda-stop directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'lambda-stop'))

from instance_stop import handler, EC2InstanceManager

class TestInstanceStop(unittest.TestCase):
    def setUp(self):
        self.event = {
            'detail': {
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

    def test_handler_no_instances(self):
        event_without_instances = {
            'detail': {
                'requestParameters': {
                    'instancesSet': {
                        'items': []
                    }
                }
            }
        }
        response = handler(event_without_instances, None)
        self.assertEqual(response['statusCode'], 400)
        self.assertEqual(response['body'], 'No instance IDs found')

    @patch('boto3.resource')
    @patch('boto3.client')
    def test_reset_instance_type_not_flexible(self, mock_boto3_client, mock_boto3_resource):
        # Mock EC2 instance
        mock_instance = MagicMock()
        mock_instance.tags = [{'Key': 'Flexible', 'Value': 'false'}]
        mock_instance.instance_type = 't3.large'
        mock_boto3_resource.return_value.Instance.return_value = mock_instance

        manager = EC2InstanceManager()
        result = manager.reset_instance_type('i-1234567890abcdef0')
        
        self.assertIsNone(result)

    @patch('boto3.resource')
    @patch('boto3.client')
    def test_reset_instance_type_flexible_no_original(self, mock_boto3_client, mock_boto3_resource):
        # Mock EC2 instance
        mock_instance = MagicMock()
        mock_instance.tags = [{'Key': 'Flexible', 'Value': 'true'}]
        mock_instance.instance_type = 't3.large'
        mock_boto3_resource.return_value.Instance.return_value = mock_instance

        manager = EC2InstanceManager()
        result = manager.reset_instance_type('i-1234567890abcdef0')
        
        self.assertIsNone(result)

    @patch('boto3.resource')
    @patch('boto3.client')
    def test_reset_instance_type_successful(self, mock_boto3_client, mock_boto3_resource):
        # Mock EC2 instance
        mock_instance = MagicMock()
        mock_instance.tags = [
            {'Key': 'Flexible', 'Value': 'true'},
            {'Key': 'OriginalType', 'Value': 't3.medium'}
        ]
        mock_instance.instance_type = 't3.large'
        mock_boto3_resource.return_value.Instance.return_value = mock_instance

        # Mock instance type validation
        mock_boto3_client.return_value.describe_instance_types.return_value = {
            'InstanceTypes': [{'InstanceType': 't3.medium'}]
        }

        manager = EC2InstanceManager()
        with patch.object(manager, 'wait_for_instance_stopped', return_value=(True, 'stopped')):
            result = manager.reset_instance_type('i-1234567890abcdef0')

        self.assertIsNotNone(result)
        self.assertEqual(result['instance_id'], 'i-1234567890abcdef0')
        self.assertEqual(result['instance_type'], 't3.large')
        self.assertEqual(result['new_instance_type'], 't3.medium')
        mock_instance.modify_attribute.assert_called_once_with(
            InstanceType={'Value': 't3.medium'}
        )
        mock_instance.delete_tags.assert_called_once_with(
            Tags=[{'Key': 'OriginalType'}]
        )

    @patch('boto3.resource')
    @patch('boto3.client')
    def test_reset_instance_type_invalid_type(self, mock_boto3_client, mock_boto3_resource):
        # Mock EC2 instance
        mock_instance = MagicMock()
        mock_instance.tags = [
            {'Key': 'Flexible', 'Value': 'true'},
            {'Key': 'OriginalType', 'Value': 'invalid.type'}
        ]
        mock_instance.instance_type = 't3.large'
        mock_boto3_resource.return_value.Instance.return_value = mock_instance

        # Mock instance type validation failure
        mock_boto3_client.return_value.describe_instance_types.side_effect = \
            mock_boto3_resource.return_value.meta.client.exceptions.ClientError(
                {'Error': {'Code': 'InvalidInstanceType', 'Message': 'Invalid instance type'}},
                'DescribeInstanceTypes'
            )

        manager = EC2InstanceManager()
        result = manager.reset_instance_type('i-1234567890abcdef0')
        
        self.assertIsNone(result)

    @patch('boto3.resource')
    @patch('boto3.client')
    def test_wait_for_instance_stopped_success(self, mock_boto3_client, mock_boto3_resource):
        # Mock EC2 instance
        mock_instance = MagicMock()
        mock_instance.state = {'Name': 'stopped'}
        mock_boto3_resource.return_value.Instance.return_value = mock_instance

        manager = EC2InstanceManager()
        success, state = manager.wait_for_instance_stopped('i-1234567890abcdef0')
        
        self.assertTrue(success)
        self.assertEqual(state, 'stopped')

    @patch('boto3.resource')
    @patch('boto3.client')
    def test_wait_for_instance_stopped_terminated(self, mock_boto3_client, mock_boto3_resource):
        # Mock EC2 instance
        mock_instance = MagicMock()
        mock_instance.state = {'Name': 'terminated'}
        mock_boto3_resource.return_value.Instance.return_value = mock_instance

        manager = EC2InstanceManager()
        success, state = manager.wait_for_instance_stopped('i-1234567890abcdef0')
        
        self.assertFalse(success)
        self.assertEqual(state, 'terminated')

    @patch('boto3.resource')
    @patch('boto3.client')
    def test_handler_successful_reset(self, mock_boto3_client, mock_boto3_resource):
        # Mock EC2 instance
        mock_instance = MagicMock()
        mock_instance.tags = [
            {'Key': 'Flexible', 'Value': 'true'},
            {'Key': 'OriginalType', 'Value': 't3.medium'}
        ]
        mock_instance.instance_type = 't3.large'
        mock_boto3_resource.return_value.Instance.return_value = mock_instance

        # Mock instance type validation
        mock_boto3_client.return_value.describe_instance_types.return_value = {
            'InstanceTypes': [{'InstanceType': 't3.medium'}]
        }

        with patch.object(EC2InstanceManager, 'wait_for_instance_stopped', return_value=(True, 'stopped')):
            response = handler(self.event, None)

        self.assertEqual(response['statusCode'], 200)
        results = json.loads(response['body'])['results']
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['instanceId'], 'i-1234567890abcdef0')
        self.assertEqual(results[0]['instanceType'], 't3.large')
        self.assertEqual(results[0]['newInstanceType'], 't3.medium')

if __name__ == '__main__':
    unittest.main()