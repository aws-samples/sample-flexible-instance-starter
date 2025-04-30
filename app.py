#!/usr/bin/env python3
from aws_cdk import App
from stacks.instance_recovery_stack import InstanceRecoveryStack

app = App()
InstanceRecoveryStack(app, "InstanceRecoveryStack")
app.synth()