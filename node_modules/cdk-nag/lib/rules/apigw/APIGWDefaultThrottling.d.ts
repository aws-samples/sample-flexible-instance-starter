import { CfnResource } from 'aws-cdk-lib';
import { NagRuleCompliance } from '../../nag-rules';
/**
 * API Gateway stages are not using default throttling settings
 * @param node The CfnStage or CfnHttpStage to check
 */
declare const _default: (node: CfnResource) => NagRuleCompliance;
export default _default;
