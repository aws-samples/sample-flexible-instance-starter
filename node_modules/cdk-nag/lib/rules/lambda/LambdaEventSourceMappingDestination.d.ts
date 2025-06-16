import { CfnResource } from 'aws-cdk-lib';
import { NagRuleCompliance } from '../../nag-rules';
/**
 * Lambda Event Source Mappings must have a destination configured for failed invocations.
 *
 * @param node - The CfnResource to check
 */
export default function LambdaEventSourceMappingDestination(node: CfnResource): NagRuleCompliance;
