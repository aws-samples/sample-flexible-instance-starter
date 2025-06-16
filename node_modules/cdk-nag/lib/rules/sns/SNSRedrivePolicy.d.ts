import { CfnResource } from 'aws-cdk-lib';
import { NagRuleCompliance } from '../../nag-rules';
/**
 * SNS subscriptions have a redrive policy configured.
 *
 * @see https://docs.aws.amazon.com/sns/latest/dg/sns-dead-letter-queues.html
 */
declare const _default: (node: CfnResource) => NagRuleCompliance;
export default _default;
