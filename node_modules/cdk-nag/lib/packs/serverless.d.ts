import { IConstruct } from 'constructs';
import { NagPack, NagPackProps } from '../nag-pack';
/**
 * Serverless Checks are a compilation of rules to validate infrastructure-as-code template against recommended practices.
 *
 */
export declare class ServerlessChecks extends NagPack {
    constructor(props?: NagPackProps);
    visit(node: IConstruct): void;
    /**
     * Check Lambda Resources
     * @param node the CfnResource to check
     * @param ignores list of ignores for the resource
     */
    private checkLambda;
    /**
     * Check Cloudwatch Resources
     * @param node the CfnResource to check
     * @param ignores list of ignores for the resource
     */
    private checkCloudwatch;
    /**
     * Check API Gateway Resources
     * @param node the CfnResource to check
     * @param ignores list of ignores for the resource
     */
    private checkApiGw;
    /**
     * Check AppSync Resources
     * @param node the CfnResource to check
     * @param ignores list of ignores for the resource
     */
    private checkAppSync;
    /**
     * Check EventBridge Resources
     * @param node the CfnResource to check
     * @param ignores list of ignores for the resource
     */
    private checkEventBridge;
    /**
     * Check SNS Resources
     * @param node the CfnResource to check
     * @param ignores list of ignores for the resource
     */
    private checkSNS;
    /**
     * Check SQS Resources
     * @param node the CfnResource to check
     * @param ignores list of ignores for the resource
     */
    private checkSQS;
    /**
     * Check StepFunctions Resources
     * @param node the CfnResource to check
     * @param ignores list of ignores for the resource
     */
    private checkStepFunctions;
}
