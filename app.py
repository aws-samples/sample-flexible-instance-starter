#!/usr/bin/env python3
from aws_cdk import (
    App,
    Aspects
    )
from stacks.instance_recovery_stack import InstanceRecoveryStack
import cdk_nag

app = App()
InstanceRecoveryStack(app, "InstanceRecoveryStack")
Aspects.of(app).add(cdk_nag.AwsSolutionsChecks(verbose=True))
app.synth()