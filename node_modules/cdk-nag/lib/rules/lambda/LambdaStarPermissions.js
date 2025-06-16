"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
/*
Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: Apache-2.0
*/
const path_1 = require("path");
const aws_cdk_lib_1 = require("aws-cdk-lib");
const aws_iam_1 = require("aws-cdk-lib/aws-iam");
const nag_rules_1 = require("../../nag-rules");
/**
 * Lambda functions have least privileged access permissions.
 * @param node the CfnResource to check
 */
exports.default = Object.defineProperty((node) => {
    // Only check IAM roles
    if (!(node instanceof aws_iam_1.CfnRole)) {
        return nag_rules_1.NagRuleCompliance.NOT_APPLICABLE;
    }
    // Check if this is a Lambda role
    if (!isLambdaRole(node)) {
        return nag_rules_1.NagRuleCompliance.NOT_APPLICABLE;
    }
    // Check if the role has any policies with wildcard permissions
    const inlinePolicies = aws_cdk_lib_1.Stack.of(node).resolve(node.policies);
    if (inlinePolicies && inlinePolicies.length > 0) {
        for (const policy of inlinePolicies) {
            const resolvedPolicy = aws_cdk_lib_1.Stack.of(node).resolve(policy);
            const policyDocument = aws_cdk_lib_1.Stack.of(node).resolve(resolvedPolicy.policyDocument);
            if (policyDocument.Statement) {
                for (const statement of policyDocument.Statement) {
                    if (statementContainsWildcard(statement)) {
                        return nag_rules_1.NagRuleCompliance.NON_COMPLIANT;
                    }
                }
            }
        }
    }
    // If we've checked all policies and found no wildcards, the role is compliant
    return nag_rules_1.NagRuleCompliance.COMPLIANT;
}, 'name', { value: (0, path_1.parse)(__filename).name });
/**
 * Checks if a role is assumed by the Lambda service
 * @param node The CfnRole to check
 * @returns true if the role is assumed by Lambda service
 */
function isLambdaRole(node) {
    const assumeRolePolicyDocument = aws_cdk_lib_1.Stack.of(node).resolve(node.assumeRolePolicyDocument);
    if (!assumeRolePolicyDocument || !assumeRolePolicyDocument.Statement) {
        return false;
    }
    for (const statement of assumeRolePolicyDocument.Statement) {
        if (statement.Principal && statement.Principal.Service) {
            const service = Array.isArray(statement.Principal.Service)
                ? statement.Principal.Service
                : [statement.Principal.Service];
            if (service.includes('lambda.amazonaws.com')) {
                return true;
            }
        }
    }
    return false;
}
/**
 * Checks if a policy statement contains wildcard permissions
 * @param statement The policy statement to check
 * @returns true if the statement contains wildcard permissions
 */
function statementContainsWildcard(statement) {
    // Only check Allow statements
    if (statement.Effect !== 'Allow') {
        return false;
    }
    // Check for wildcard in actions
    const actions = normalizeToArray(statement.Action);
    for (const action of actions) {
        if (typeof action === 'string') {
            // Check for full wildcard ('*')
            if (action === '*') {
                return true;
            }
            // Check for service level wildcard (e.g., 's3:*')
            // But allow service specific partial actions (e.g., 's3:Get*')
            if (action.endsWith(':*')) {
                return true;
            }
        }
    }
    // Check for full wildcard in resources
    // Only flag resources that are exactly '*'
    const resources = normalizeToArray(statement.Resource);
    for (const resource of resources) {
        if (typeof resource === 'string' && resource === '*') {
            return true;
        }
    }
    return false;
}
/**
 * Normalizes a value to an array
 * @param value The value to normalize
 * @returns An array containing the value(s)
 */
function normalizeToArray(value) {
    return Array.isArray(value) ? value : [value];
}
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiTGFtYmRhU3RhclBlcm1pc3Npb25zLmpzIiwic291cmNlUm9vdCI6IiIsInNvdXJjZXMiOlsiLi4vLi4vLi4vc3JjL3J1bGVzL2xhbWJkYS9MYW1iZGFTdGFyUGVybWlzc2lvbnMudHMiXSwibmFtZXMiOltdLCJtYXBwaW5ncyI6Ijs7QUFBQTs7O0VBR0U7QUFDRiwrQkFBNkI7QUFDN0IsNkNBQWlEO0FBQ2pELGlEQUE4QztBQUM5QywrQ0FBb0Q7QUFZcEQ7OztHQUdHO0FBQ0gsa0JBQWUsTUFBTSxDQUFDLGNBQWMsQ0FDbEMsQ0FBQyxJQUFpQixFQUFxQixFQUFFO0lBQ3ZDLHVCQUF1QjtJQUN2QixJQUFJLENBQUMsQ0FBQyxJQUFJLFlBQVksaUJBQU8sQ0FBQyxFQUFFLENBQUM7UUFDL0IsT0FBTyw2QkFBaUIsQ0FBQyxjQUFjLENBQUM7SUFDMUMsQ0FBQztJQUVELGlDQUFpQztJQUNqQyxJQUFJLENBQUMsWUFBWSxDQUFDLElBQUksQ0FBQyxFQUFFLENBQUM7UUFDeEIsT0FBTyw2QkFBaUIsQ0FBQyxjQUFjLENBQUM7SUFDMUMsQ0FBQztJQUVELCtEQUErRDtJQUMvRCxNQUFNLGNBQWMsR0FBRyxtQkFBSyxDQUFDLEVBQUUsQ0FBQyxJQUFJLENBQUMsQ0FBQyxPQUFPLENBQUMsSUFBSSxDQUFDLFFBQVEsQ0FBQyxDQUFDO0lBRTdELElBQUksY0FBYyxJQUFJLGNBQWMsQ0FBQyxNQUFNLEdBQUcsQ0FBQyxFQUFFLENBQUM7UUFDaEQsS0FBSyxNQUFNLE1BQU0sSUFBSSxjQUFjLEVBQUUsQ0FBQztZQUNwQyxNQUFNLGNBQWMsR0FBRyxtQkFBSyxDQUFDLEVBQUUsQ0FBQyxJQUFJLENBQUMsQ0FBQyxPQUFPLENBQUMsTUFBTSxDQUFDLENBQUM7WUFDdEQsTUFBTSxjQUFjLEdBQXNCLG1CQUFLLENBQUMsRUFBRSxDQUFDLElBQUksQ0FBQyxDQUFDLE9BQU8sQ0FDOUQsY0FBYyxDQUFDLGNBQWMsQ0FDOUIsQ0FBQztZQUVGLElBQUksY0FBYyxDQUFDLFNBQVMsRUFB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Q0FBQyxDQUFDLENBQUMsQ0FBQyxLQUFLLENBQUMsQ0FBQyxDQUFDLENBQUMsS0FBSyxDQUFDLENBQUM7QUFDaEQsQ0FBQyIsInNvdXJjZXNDb250ZW50IjpbIi8qXG5Db3B5cmlnaHQgQW1hem9uLmNvbSwgSW5jLiBvciBpdHMgYWZmaWxpYXRlcy4gQWxsIFJpZ2h0cyBSZXNlcnZlZC5cblNQRFgtTGljZW5zZS1JZGVudGlmaWVyOiBBcGFjaGUtMi4wXG4qL1xuaW1wb3J0IHsgcGFyc2UgfSBmcm9tICdwYXRoJztcbmltcG9ydCB7IENmblJlc291cmNlLCBTdGFjayB9IGZyb20gJ2F3cy1jZGstbGliJztcbmltcG9ydCB7IENmblJvbGUgfSBmcm9tICdhd3MtY2RrLWxpYi9hd3MtaWFtJztcbmltcG9ydCB7IE5hZ1J1bGVDb21wbGlhbmNlIH0gZnJvbSAnLi4vLi4vbmFnLXJ1bGVzJztcblxuaW50ZXJmYWNlIElBTVBvbGljeURvY3VtZW50IHtcbiAgU3RhdGVtZW50PzogSUFNUG9saWN5U3RhdGVtZW50W107XG59XG5cbmludGVyZmFjZSBJQU1Qb2xpY3lTdGF0ZW1lbnQge1xuICBBY3Rpb246IHN0cmluZyB8IHN0cmluZ1tdO1xuICBFZmZlY3Q6ICdBbGxvdycgfCAnRGVueSc7XG4gIFJlc291cmNlOiB1bmtub3duO1xufVxuXG4vKipcbiAqIExhbWJkYSBmdW5jdGlvbnMgaGF2ZSBsZWFzdCBwcml2aWxlZ2VkIGFjY2VzcyBwZXJtaXNzaW9ucy5cbiAqIEBwYXJhbSBub2RlIHRoZSBDZm5SZXNvdXJjZSB0byBjaGVja1xuICovXG5leHBvcnQgZGVmYXVsdCBPYmplY3QuZGVmaW5lUHJvcGVydHkoXG4gIChub2RlOiBDZm5SZXNvdXJjZSk6IE5hZ1J1bGVDb21wbGlhbmNlID0+IHtcbiAgICAvLyBPbmx5IGNoZWNrIElBTSByb2xlc1xuICAgIGlmICghKG5vZGUgaW5zdGFuY2VvZiBDZm5Sb2xlKSkge1xuICAgICAgcmV0dXJuIE5hZ1J1bGVDb21wbGlhbmNlLk5PVF9BUFBMSUNBQkxFO1xuICAgIH1cblxuICAgIC8vIENoZWNrIGlmIHRoaXMgaXMgYSBMYW1iZGEgcm9sZVxuICAgIGlmICghaXNMYW1iZGFSb2xlKG5vZGUpKSB7XG4gICAgICByZXR1cm4gTmFnUnVsZUNvbXBsaWFuY2UuTk9UX0FQUExJQ0FCTEU7XG4gICAgfVxuXG4gICAgLy8gQ2hlY2sgaWYgdGhlIHJvbGUgaGFzIGFueSBwb2xpY2llcyB3aXRoIHdpbGRjYXJkIHBlcm1pc3Npb25zXG4gICAgY29uc3QgaW5saW5lUG9saWNpZXMgPSBTdGFjay5vZihub2RlKS5yZXNvbHZlKG5vZGUucG9saWNpZXMpO1xuXG4gICAgaWYgKGlubGluZVBvbGljaWVzICYmIGlubGluZVBvbGljaWVzLmxlbmd0aCA+IDApIHtcbiAgICAgIGZvciAoY29uc3QgcG9saWN5IG9mIGlubGluZVBvbGljaWVzKSB7XG4gICAgICAgIGNvbnN0IHJlc29sdmVkUG9saWN5ID0gU3RhY2sub2Yobm9kZSkucmVzb2x2ZShwb2xpY3kpO1xuICAgICAgICBjb25zdCBwb2xpY3lEb2N1bWVudDogSUFNUG9saWN5RG9jdW1lbnQgPSBTdGFjay5vZihub2RlKS5yZXNvbHZlKFxuICAgICAgICAgIHJlc29sdmVkUG9saWN5LnBvbGljeURvY3VtZW50XG4gICAgICAgICk7XG5cbiAgICAgICAgaWYgKHBvbGljeURvY3VtZW50LlN0YXRlbWVudCkge1xuICAgICAgICAgIGZvciAoY29uc3Qgc3RhdGVtZW50IG9mIHBvbGljeURvY3VtZW50LlN0YXRlbWVudCkge1xuICAgICAgICAgICAgaWYgKHN0YXRlbWVudENvbnRhaW5zV2lsZGNhcmQoc3RhdGVtZW50KSkge1xuICAgICAgICAgICAgICByZXR1cm4gTmFnUnVsZUNvbXBsaWFuY2UuTk9OX0NPTVBMSUFOVDtcbiAgICAgICAgICAgIH1cbiAgICAgICAgICB9XG4gICAgICAgIH1cbiAgICAgIH1cbiAgICB9XG5cbiAgICAvLyBJZiB3ZSd2ZSBjaGVja2VkIGFsbCBwb2xpY2llcyBhbmQgZm91bmQgbm8gd2lsZGNhcmRzLCB0aGUgcm9sZSBpcyBjb21wbGlhbnRcbiAgICByZXR1cm4gTmFnUnVsZUNvbXBsaWFuY2UuQ09NUExJQU5UO1xuICB9LFxuICAnbmFtZScsXG4gIHsgdmFsdWU6IHBhcnNlKF9fZmlsZW5hbWUpLm5hbWUgfVxuKTtcblxuLyoqXG4gKiBDaGVja3MgaWYgYSByb2xlIGlzIGFzc3VtZWQgYnkgdGhlIExhbWJkYSBzZXJ2aWNlXG4gKiBAcGFyYW0gbm9kZSBUaGUgQ2ZuUm9sZSB0byBjaGVja1xuICogQHJldHVybnMgdHJ1ZSBpZiB0aGUgcm9sZSBpcyBhc3N1bWVkIGJ5IExhbWJkYSBzZXJ2aWNlXG4gKi9cbmZ1bmN0aW9uIGlzTGFtYmRhUm9sZShub2RlOiBDZm5Sb2xlKTogYm9vbGVhbiB7XG4gIGNvbnN0IGFzc3VtZVJvbGVQb2xpY3lEb2N1bWVudCA9IFN0YWNrLm9mKG5vZGUpLnJlc29sdmUoXG4gICAgbm9kZS5hc3N1bWVSb2xlUG9saWN5RG9jdW1lbnRcbiAgKTtcblxuICBpZiAoIWFzc3VtZVJvbGVQb2xpY3lEb2N1bWVudCB8fCAhYXNzdW1lUm9sZVBvbGljeURvY3VtZW50LlN0YXRlbWVudCkge1xuICAgIHJldHVybiBmYWxzZTtcbiAgfVxuXG4gIGZvciAoY29uc3Qgc3RhdGVtZW50IG9mIGFzc3VtZVJvbGVQb2xpY3lEb2N1bWVudC5TdGF0ZW1lbnQpIHtcbiAgICBpZiAoc3RhdGVtZW50LlByaW5jaXBhbCAmJiBzdGF0ZW1lbnQuUHJpbmNpcGFsLlNlcnZpY2UpIHtcbiAgICAgIGNvbnN0IHNlcnZpY2UgPSBBcnJheS5pc0FycmF5KHN0YXRlbWVudC5QcmluY2lwYWwuU2VydmljZSlcbiAgICAgICAgPyBzdGF0ZW1lbnQuUHJpbmNpcGFsLlNlcnZpY2VcbiAgICAgICAgOiBbc3RhdGVtZW50LlByaW5jaXBhbC5TZXJ2aWNlXTtcblxuICAgICAgaWYgKHNlcnZpY2UuaW5jbHVkZXMoJ2xhbWJkYS5hbWF6b25hd3MuY29tJykpIHtcbiAgICAgICAgcmV0dXJuIHRydWU7XG4gICAgICB9XG4gICAgfVxuICB9XG5cbiAgcmV0dXJuIGZhbHNlO1xufVxuXG4vKipcbiAqIENoZWNrcyBpZiBhIHBvbGljeSBzdGF0ZW1lbnQgY29udGFpbnMgd2lsZGNhcmQgcGVybWlzc2lvbnNcbiAqIEBwYXJhbSBzdGF0ZW1lbnQgVGhlIHBvbGljeSBzdGF0ZW1lbnQgdG8gY2hlY2tcbiAqIEByZXR1cm5zIHRydWUgaWYgdGhlIHN0YXRlbWVudCBjb250YWlucyB3aWxkY2FyZCBwZXJtaXNzaW9uc1xuICovXG5mdW5jdGlvbiBzdGF0ZW1lbnRDb250YWluc1dpbGRjYXJkKHN0YXRlbWVudDogSUFNUG9saWN5U3RhdGVtZW50KTogYm9vbGVhbiB7XG4gIC8vIE9ubHkgY2hlY2sgQWxsb3cgc3RhdGVtZW50c1xuICBpZiAoc3RhdGVtZW50LkVmZmVjdCAhPT0gJ0FsbG93Jykge1xuICAgIHJldHVybiBmYWxzZTtcbiAgfVxuXG4gIC8vIENoZWNrIGZvciB3aWxkY2FyZCBpbiBhY3Rpb25zXG4gIGNvbnN0IGFjdGlvbnMgPSBub3JtYWxpemVUb0FycmF5KHN0YXRlbWVudC5BY3Rpb24pO1xuICBmb3IgKGNvbnN0IGFjdGlvbiBvZiBhY3Rpb25zKSB7XG4gICAgaWYgKHR5cGVvZiBhY3Rpb24gPT09ICdzdHJpbmcnKSB7XG4gICAgICAvLyBDaGVjayBmb3IgZnVsbCB3aWxkY2FyZCAoJyonKVxuICAgICAgaWYgKGFjdGlvbiA9PT0gJyonKSB7XG4gICAgICAgIHJldHVybiB0cnVlO1xuICAgICAgfVxuXG4gICAgICAvLyBDaGVjayBmb3Igc2VydmljZSBsZXZlbCB3aWxkY2FyZCAoZS5nLiwgJ3MzOionKVxuICAgICAgLy8gQnV0IGFsbG93IHNlcnZpY2Ugc3BlY2lmaWMgcGFydGlhbCBhY3Rpb25zIChlLmcuLCAnczM6R2V0KicpXG4gICAgICBpZiAoYWN0aW9uLmVuZHNXaXRoKCc6KicpKSB7XG4gICAgICAgIHJldHVybiB0cnVlO1xuICAgICAgfVxuICAgIH1cbiAgfVxuXG4gIC8vIENoZWNrIGZvciBmdWxsIHdpbGRjYXJkIGluIHJlc291cmNlc1xuICAvLyBPbmx5IGZsYWcgcmVzb3VyY2VzIHRoYXQgYXJlIGV4YWN0bHkgJyonXG4gIGNvbnN0IHJlc291cmNlcyA9IG5vcm1hbGl6ZVRvQXJyYXkoc3RhdGVtZW50LlJlc291cmNlKTtcbiAgZm9yIChjb25zdCByZXNvdXJjZSBvZiByZXNvdXJjZXMpIHtcbiAgICBpZiAodHlwZW9mIHJlc291cmNlID09PSAnc3RyaW5nJyAmJiByZXNvdXJjZSA9PT0gJyonKSB7XG4gICAgICByZXR1cm4gdHJ1ZTtcbiAgICB9XG4gIH1cblxuICByZXR1cm4gZmFsc2U7XG59XG5cbi8qKlxuICogTm9ybWFsaXplcyBhIHZhbHVlIHRvIGFuIGFycmF5XG4gKiBAcGFyYW0gdmFsdWUgVGhlIHZhbHVlIHRvIG5vcm1hbGl6ZVxuICogQHJldHVybnMgQW4gYXJyYXkgY29udGFpbmluZyB0aGUgdmFsdWUocylcbiAqL1xuZnVuY3Rpb24gbm9ybWFsaXplVG9BcnJheTxUPih2YWx1ZTogVCB8IFRbXSk6IFRbXSB7XG4gIHJldHVybiBBcnJheS5pc0FycmF5KHZhbHVlKSA/IHZhbHVlIDogW3ZhbHVlXTtcbn1cbiJdfQ==