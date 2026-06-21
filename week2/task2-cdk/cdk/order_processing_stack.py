"""
CDK Stack: Step Functions Order Processing Workflow.

This stack creates:
- DynamoDB table for order storage
- SNS topic for order notifications (email subscription)
- 4 Lambda functions (validate, check-inventory, process-payment, update-order)
- Step Functions state machine orchestrating the full pipeline
- All IAM roles auto-managed by CDK
"""

from pathlib import Path

from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    CfnOutput,
    aws_dynamodb as dynamodb,
    aws_lambda as _lambda,
    aws_sns as sns,
    aws_sns_subscriptions as subs,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
)
from constructs import Construct

LAMBDA_DIR = Path(__file__).resolve().parent.parent / "lambda" / "step_functions"


def _read_code(filename):
    """Read Lambda source code from file."""
    return (LAMBDA_DIR / filename).read_text()


class OrderProcessingStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ─── DynamoDB Table ─────────────────────────────────────────────
        order_table = dynamodb.Table(
            self,
            "OrderTable",
            table_name="order-processing-cdk",
            partition_key=dynamodb.Attribute(
                name="orderId", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ─── SNS Topic ─────────────────────────────────────────────────
        notification_topic = sns.Topic(
            self,
            "OrderNotifications",
            topic_name="order-notifications-cdk",
            display_name="Order Processing Notifications",
        )

        notification_topic.add_subscription(
            subs.EmailSubscription("abhishek.a@fractal.ai")
        )

        # ─── Lambda Functions ───────────────────────────────────────────
        common_props = {
            "runtime": _lambda.Runtime.PYTHON_3_12,
            "timeout": Duration.seconds(15),
            "memory_size": 128,
        }

        validate_fn = _lambda.Function(
            self,
            "ValidateOrder",
            function_name="validate-order-cdk",
            handler="index.lambda_handler",
            code=_lambda.Code.from_inline(_read_code("validate_order.py")),
            **common_props,
        )

        check_inventory_fn = _lambda.Function(
            self,
            "CheckInventory",
            function_name="check-inventory-cdk",
            handler="index.lambda_handler",
            code=_lambda.Code.from_inline(_read_code("check_inventory.py")),
            **common_props,
        )

        process_payment_fn = _lambda.Function(
            self,
            "ProcessPayment",
            function_name="process-payment-cdk",
            handler="index.lambda_handler",
            code=_lambda.Code.from_inline(_read_code("process_payment.py")),
            **common_props,
        )

        update_order_fn = _lambda.Function(
            self,
            "UpdateOrder",
            function_name="update-order-cdk",
            handler="index.lambda_handler",
            code=_lambda.Code.from_inline(_read_code("update_order.py")),
            environment={
                "TABLE_NAME": order_table.table_name,
            },
            **common_props,
        )

        # ─── Permissions (CDK grant helpers) ────────────────────────────
        order_table.grant_read_write_data(update_order_fn)

        # ─── Step Functions Definition ──────────────────────────────────

        # Task: Validate Order
        validate_task = tasks.LambdaInvoke(
            self,
            "ValidateOrderTask",
            lambda_function=validate_fn,
            output_path="$.Payload",
        )

        # Task: Check Inventory
        check_inventory_task = tasks.LambdaInvoke(
            self,
            "CheckInventoryTask",
            lambda_function=check_inventory_fn,
            output_path="$.Payload",
        )

        # Task: Process Payment (with retry)
        process_payment_task = tasks.LambdaInvoke(
            self,
            "ProcessPaymentTask",
            lambda_function=process_payment_fn,
            output_path="$.Payload",
        )
        process_payment_task.add_retry(
            errors=["States.ALL"],
            interval=Duration.seconds(2),
            max_attempts=3,
            backoff_rate=2.0,
        )

        # Task: Save to DynamoDB
        save_to_db_task = tasks.LambdaInvoke(
            self,
            "SaveToDBTask",
            lambda_function=update_order_fn,
            output_path="$.Payload",
        )

        # Task: Send Confirmation Email
        send_confirmation = tasks.SnsPublish(
            self,
            "SendConfirmation",
            topic=notification_topic,
            subject="Order Confirmed!",
            message=sfn.TaskInput.from_json_path_at(
                "States.Format('Your order is confirmed! Total: INR {}. Shipping to: {}', States.JsonToString($.orderTotal), $.order.shippingAddress)"
            ),
        )

        # Task: Notify Backorder
        notify_backorder = tasks.SnsPublish(
            self,
            "NotifyBackorder",
            topic=notification_topic,
            subject="Order Backordered - Items Out of Stock",
            message=sfn.TaskInput.from_json_path_at(
                "States.Format('Items out of stock: {}. Customer: {}', States.JsonToString($.outOfStock), $.order.customerId)"
            ),
        )

        # Task: Notify Payment Failed
        notify_payment_failed = tasks.SnsPublish(
            self,
            "NotifyPaymentFailed",
            topic=notification_topic,
            subject="Payment Failed - Order Cancelled",
            message=sfn.TaskInput.from_json_path_at(
                "States.Format('Payment failed for customer: {}. Error: {}', $.order.customerId, $.paymentError.Cause)"
            ),
        )

        # Fail States
        order_rejected = sfn.Fail(
            self,
            "OrderRejected",
            cause="Order validation failed",
            error="ValidationError",
        )

        backorder_failed = sfn.Fail(
            self,
            "BackorderFailed",
            cause="Items out of stock",
            error="InventoryError",
        )

        payment_failed_state = sfn.Fail(
            self,
            "PaymentFailedState",
            cause="Payment processing failed after 3 retries",
            error="PaymentError",
        )

        # Wait State
        wait_for_confirmation = sfn.Wait(
            self,
            "WaitForConfirmation",
            time=sfn.WaitTime.duration(Duration.seconds(3)),
        )

        # Parallel: Save to DB + Send Email
        fulfill_order = sfn.Parallel(
            self, "FulfillOrder"
        )
        fulfill_order.branch(save_to_db_task)
        fulfill_order.branch(send_confirmation)

        # Pass State: Order Complete
        order_complete = sfn.Pass(
            self,
            "OrderComplete",
            parameters={
                "finalStatus": "Order processing completed successfully",
                "orderResult.$": "$[0]",
                "notificationResult.$": "$[1]",
            },
        )

        # ─── Chain: Choice after validation ─────────────────────────────
        is_order_valid = sfn.Choice(self, "IsOrderValid")
        is_order_valid.when(
            sfn.Condition.boolean_equals("$.valid", False),
            order_rejected,
        )
        is_order_valid.otherwise(check_inventory_task)

        # ─── Chain: Choice after inventory ──────────────────────────────
        is_in_stock = sfn.Choice(self, "IsInStock")
        is_in_stock.when(
            sfn.Condition.boolean_equals("$.inStock", False),
            notify_backorder.next(backorder_failed),
        )
        is_in_stock.otherwise(process_payment_task)

        # ─── Chain: Payment catch → notify + fail ───────────────────────
        process_payment_task.add_catch(
            notify_payment_failed.next(payment_failed_state),
            errors=["States.ALL"],
            result_path="$.paymentError",
        )

        # ─── Full Chain ─────────────────────────────────────────────────
        definition = (
            validate_task
            .next(is_order_valid)
        )

        # Wire inventory → payment → wait → parallel → complete
        check_inventory_task.next(is_in_stock)
        process_payment_task.next(wait_for_confirmation)
        wait_for_confirmation.next(fulfill_order)
        fulfill_order.next(order_complete)

        # ─── State Machine ──────────────────────────────────────────────
        state_machine = sfn.StateMachine(
            self,
            "OrderProcessingStateMachine",
            state_machine_name="OrderProcessingWorkflow-CDK",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            timeout=Duration.minutes(5),
        )

        # ─── Outputs ───────────────────────────────────────────────────
        CfnOutput(self, "StateMachineArn", value=state_machine.state_machine_arn)
        CfnOutput(self, "TableName", value=order_table.table_name)
        CfnOutput(self, "TopicArn", value=notification_topic.topic_arn)
