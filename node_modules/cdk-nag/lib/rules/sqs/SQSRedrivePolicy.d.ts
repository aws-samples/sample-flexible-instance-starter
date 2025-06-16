import { CfnResource } from 'aws-cdk-lib';
import { NagRuleCompliance } from '../../nag-rules';
/**
 * SQS queues have a redrive policy configured
 *
 * @param node - the CfnResource to check
 */
export default function SQSRedrivePolicy(node: CfnResource): NagRuleCompliance;
