"""
CDK Stack: API Gateway + Lambda for SCJ Sales Coach.

This stack creates:
- S3 bucket for data files (CSV, prompt templates)
- Lambda function for GET /api/actions-for-today
- Lambda function for GET / (health check)
- REST API Gateway with proxy integration to Lambda
- Proper IAM roles for Lambda → S3 and Lambda → Bedrock access
"""

from pathlib import Path

from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    CfnOutput,
    aws_apigateway as apigw,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
)
from constructs import Construct

LAMBDA_DIR = str(Path(__file__).resolve().parent.parent / "lambda")
DATA_DIR = str(Path(__file__).resolve().parent.parent.parent / "SCJ-sales-coach-BE" / "data")


class SalesCoachApiStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ─── S3 Bucket for data files ───────────────────────────────────
        data_bucket = s3.Bucket(
            self,
            "DataBucket",
            bucket_name=f"scj-sales-coach-data-{self.account}",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # Upload CSV and prompt files to S3
        s3deploy.BucketDeployment(
            self,
            "DeployData",
            sources=[s3deploy.Source.asset(DATA_DIR)],
            destination_bucket=data_bucket,
            destination_key_prefix="data",
        )

        # ─── Lambda Layer for shared code + dependencies ────────────────
        shared_layer = _lambda.LayerVersion(
            self,
            "SharedLayer",
            code=_lambda.Code.from_asset(
                str(Path(LAMBDA_DIR) / "shared"),
            ),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
            description="Shared utilities: scoring, helpers",
        )

        # ─── Lambda: Actions For Today ──────────────────────────────────
        actions_lambda = _lambda.Function(
            self,
            "ActionsForTodayHandler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            code=_lambda.Code.from_asset(
                LAMBDA_DIR,
                bundling={
                    "image": _lambda.Runtime.PYTHON_3_12.bundling_image,
                    "command": [
                        "bash", "-c",
                        "pip install pandas boto3 -t /asset-output && "
                        "cp -r /asset-input/actions /asset-output/actions && "
                        "cp -r /asset-input/shared /asset-output/shared"
                    ],
                },
            ),
            handler="actions.handler.handler",
            timeout=Duration.seconds(120),
            memory_size=512,
            environment={
                "DATA_BUCKET": data_bucket.bucket_name,
                "CSV_KEY": "data/store_issue_feature_matrix_ui_relevant_subset.csv",
                "PROMPT_KEY": "data/ai_sales_prompt_v7.txt",
                "BEDROCK_MODEL_ID": "anthropic.claude-3-sonnet-20240229-v1:0",
            },
        )

        # Grant S3 read access
        data_bucket.grant_read(actions_lambda)

        # Grant Bedrock invoke access
        actions_lambda.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["bedrock:InvokeModel"],
                resources=["arn:aws:bedrock:*::foundation-model/*"],
            )
        )

        # ─── Lambda: Health Check ───────────────────────────────────────
        health_lambda = _lambda.Function(
            self,
            "HealthCheckHandler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            code=_lambda.Code.from_asset(str(Path(LAMBDA_DIR) / "actions")),
            handler="health.handler",
            timeout=Duration.seconds(10),
            memory_size=128,
        )

        # ─── API Gateway REST API ───────────────────────────────────────
        api = apigw.RestApi(
            self,
            "SalesCoachApi",
            rest_api_name="SCJ Sales Coach API",
            description="REST API for SCJ Sales Coach (replaces FastAPI on Azure)",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["Content-Type"],
            ),
        )

        # GET / → Health check
        api.root.add_method(
            "GET",
            apigw.LambdaIntegration(health_lambda),
        )

        # GET /api/actions-for-today → Actions Lambda
        api_resource = api.root.add_resource("api")
        actions_resource = api_resource.add_resource("actions-for-today")
        actions_resource.add_method(
            "GET",
            apigw.LambdaIntegration(actions_lambda),
        )

        # ─── Outputs ───────────────────────────────────────────────────
        CfnOutput(self, "ApiUrl", value=api.url, description="API Gateway URL")
        CfnOutput(self, "BucketName", value=data_bucket.bucket_name, description="S3 Data Bucket")
