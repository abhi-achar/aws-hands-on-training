#!/usr/bin/env python3
"""CDK App entry point."""

import aws_cdk as cdk

from cdk.order_processing_stack import OrderProcessingStack

app = cdk.App()

OrderProcessingStack(
    app,
    "OrderProcessingStack",
    env=cdk.Environment(
        account="353211646521",
        region="ap-south-1",
    ),
)

app.synth()
# CI/CD pipeline trigger
