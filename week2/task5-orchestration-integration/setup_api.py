"""Wire up API Gateway -> Lambda for the orchestration integration."""
import json
import subprocess
import sys

API_ID = "r6k62pk8oj"
REGION = "ap-south-1"
ACCOUNT = "353211646521"
LAMBDA_ARN = f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:order-api-orchestrator"
LAMBDA_URI = f"arn:aws:apigateway:{REGION}:lambda:path/2015-03-31/functions/{LAMBDA_ARN}/invocations"


def aws(*args):
    cmd = ["aws"] + list(args) + ["--region", REGION, "--no-verify-ssl"]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        # ignore "already exists" style errors, surface others
        err = out.stderr
        if "ConflictException" in err or "already exists" in err:
            return None
        print("ERROR:", " ".join(args), "\n", err[:300], file=sys.stderr)
        return None
    return json.loads(out.stdout) if out.stdout.strip() else {}


# 1. Root resource id
resources = aws("apigateway", "get-resources", "--rest-api-id", API_ID)
root_id = next(r["id"] for r in resources["items"] if r["path"] == "/")
print(f"root: {root_id}")

# 2. /orders resource
orders = aws("apigateway", "create-resource", "--rest-api-id", API_ID,
             "--parent-id", root_id, "--path-part", "orders")
orders_id = orders["id"]
print(f"/orders: {orders_id}")

# 3. /orders/{id} resource
order_id_res = aws("apigateway", "create-resource", "--rest-api-id", API_ID,
                   "--parent-id", orders_id, "--path-part", "{id}")
order_id = order_id_res["id"]
print(f"/orders/{{id}}: {order_id}")

# 4. POST /orders
aws("apigateway", "put-method", "--rest-api-id", API_ID, "--resource-id", orders_id,
    "--http-method", "POST", "--authorization-type", "NONE")
aws("apigateway", "put-integration", "--rest-api-id", API_ID, "--resource-id", orders_id,
    "--http-method", "POST", "--type", "AWS_PROXY",
    "--integration-http-method", "POST", "--uri", LAMBDA_URI)
print("POST /orders wired")

# 5. GET /orders/{id}
aws("apigateway", "put-method", "--rest-api-id", API_ID, "--resource-id", order_id,
    "--http-method", "GET", "--authorization-type", "NONE")
aws("apigateway", "put-integration", "--rest-api-id", API_ID, "--resource-id", order_id,
    "--http-method", "GET", "--type", "AWS_PROXY",
    "--integration-http-method", "POST", "--uri", LAMBDA_URI)
print("GET /orders/{id} wired")

# 6. Lambda permission for API Gateway
aws("lambda", "add-permission", "--function-name", "order-api-orchestrator",
    "--statement-id", "apigw-invoke", "--action", "lambda:InvokeFunction",
    "--principal", "apigateway.amazonaws.com",
    "--source-arn", f"arn:aws:execute-api:{REGION}:{ACCOUNT}:{API_ID}/*/*/*")
print("Lambda permission added")

# 7. Deploy to 'prod' stage
aws("apigateway", "create-deployment", "--rest-api-id", API_ID, "--stage-name", "prod")
print(f"Deployed. Base URL: https://{API_ID}.execute-api.{REGION}.amazonaws.com/prod")
