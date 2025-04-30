import unittest
from unittest.mock import patch, MagicMock
import json
import sys
import os

# Add the lambda directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'lambda'))

from instance_recovery import handler, get_alternative_instance_types

class TestInstanceRecovery(unittest.TestCase):
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

    @patch('instance_recovery.ec2')
    def test_handler_successful_restart(self, mock_ec2):
        # Mock successful start
        mock_ec2.start_instances.return_value = {'StartingInstances': []}
        
        response = handler(self.event, None)
        
        self.assertEqual(response['statusCode'], 200)
        results = json.loads(response['body'])['results']
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['status'], 'started')
        self.assertEqual(results[0]['action'], 'restart')

    @patch('instance_recovery.ec2')
    def test_handler_type_modification(self, mock_ec2):
        # Mock failed start followed by successful modification and start
        mock_ec2.start_instances.side_effect = [
            Exception("InsufficientInstanceCapacity"),
            {'StartingInstances': []}
        ]
        mock_ec2.describe_instances.return_value = {
            'Reservations': [{
                'Instances': [{
                    'InstanceType': 't3.large'
                }]
            }]
        }
        mock_ec2.modify_instance_attribute.return_value = {}
        
        response = handler(self.event, None)
        
        self.assertEqual(response['statusCode'], 200)
        results = json.loads(response['body'])['results']
        self.assertTrue(any(r['action'] == 'type_modified' for r in results))

    def test_get_alternative_instance_types(self):
        alternatives = get_alternative_instance_types('t3.large')
        self.assertTrue('t2.large' in alternatives)
        self.assertTrue('t3a.large' in alternatives)

if __name__ == '__main__':
    unittest.main()