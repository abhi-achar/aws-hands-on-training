"""Wire API Gateway POST /search -> retrieval Lambda, then deploy to prod."""
import json
import subprocess

API_ID = "tdf4du7z9g"
REGION = "ap-south-1"
ACCOUNT = "353211646521"
LAMBDA_ARN = f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:novacart-kb-retrieve"
LAMBDA_URI = f"arn:aws:apigateway:{REGION}:lambda:path/2015-03-31/functions/{LAMBDA_ARN}/invocations"


def aws(*args):
    cmd = ["aws"] + list(args) + ["--region", REGION, "--no-verify-ssl"]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0 and "ConflictException" not in out.stderr:
        print("ERR:", args[1] if len(args) > 1 else args, out.stderr[:200])
        return None
    return json.loads(out.stdout) if out.stdout.strip() else {}


resources = aws("apigateway", "get-resources", "--rest-api-id", API_ID)
root_id = next(r["id"] for r in resources["items"] if r["path"] == "/")
print("root:", root_id)

search = aws("apigateway", "create-resource", "--rest-api-id", API_ID,
             "--parent-id", root_id, "--path-part", "search")
search_id = search["id"]
print("/search:", search_id)

aws("apigateway", "put-method", "--rest-api-id", API_ID, "--resource-id", search_id,
    "--http-method", "POST", "--authorization-type", "NONE")
aws("apigateway", "put-integration", "--rest-api-id", API_ID, "--resource-id", search_id,
    "--http-method", "POST", "--type", "AWS_PROXY",
    "--integration-http-method", "POST", "--uri", LAMBDA_URI)
print("POST /search wired")

aws("lambda", "add-permission", "--function-name", "novacart-kb-retrieve",
    "--statement-id", "apigw-invoke", "--action", "lambda:InvokeFunction",
    "--principal", "apigateway.amazonaws.com",
    "--source-arn", f"arn:aws:execute-api:{REGION}:{ACCOUNT}:{API_ID}/*/*/*")
print("permission added")

aws("apigateway", "create-deployment", "--rest-api-id", API_ID, "--stage-name", "prod")
print(f"Deployed: https://{API_ID}.execute-api.{REGION}.amazonaws.com/prod/search")
