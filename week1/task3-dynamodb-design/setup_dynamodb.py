"""
Provision the NovaCart food-order tracking DynamoDB design.

Creates two purpose-built tables with business-meaningful keys (no generic PK/SK):

  food-orders                  PK: OrderId
    GSI CustomerOrdersIndex    PK: CustomerId   SK: OrderCreatedAt
    GSI RestaurantOrdersIndex  PK: RestaurantId SK: OrderCreatedAt

  food-order-status-history    PK: OrderId      SK: StatusTimestamp

Usage:
  python setup_dynamodb.py create     # create both tables (+ GSIs)
  python setup_dynamodb.py seed       # insert sample orders and status events
  python setup_dynamodb.py demo       # run all four access-pattern queries
  python setup_dynamodb.py all        # create + seed + demo
  python setup_dynamodb.py teardown   # delete both tables
"""

import sys

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError, NoCredentialsError

# The corporate TLS proxy in this account is not verifiable, so disable SSL
# verification for the SDK client only.
import urllib3
urllib3.disable_warnings()

REGION = "ap-south-1"
ORDERS_TABLE = "food-orders"
STATUS_TABLE = "food-order-status-history"

_dynamodb = boto3.resource("dynamodb", region_name=REGION, verify=False)
_client = _dynamodb.meta.client


SAMPLE_ORDERS = [
    {
        "OrderId": "ORD-1001",
        "CustomerId": "C001",
        "RestaurantId": "R001",
        "OrderCreatedAt": "2026-06-10T14:30:00",
        "CurrentStatus": "DELIVERED",
        "TotalAmount": 450,
        "Items": [
            {"name": "Margherita Pizza", "qty": 1, "price": 300},
            {"name": "Garlic Bread", "qty": 1, "price": 150},
        ],
    },
    {
        "OrderId": "ORD-1002",
        "CustomerId": "C001",
        "RestaurantId": "R002",
        "OrderCreatedAt": "2026-06-12T19:15:00",
        "CurrentStatus": "OUT_FOR_DELIVERY",
        "TotalAmount": 720,
        "Items": [
            {"name": "Paneer Biryani", "qty": 2, "price": 360},
        ],
    },
    {
        "OrderId": "ORD-1003",
        "CustomerId": "C002",
        "RestaurantId": "R001",
        "OrderCreatedAt": "2026-06-11T13:00:00",
        "CurrentStatus": "PLACED",
        "TotalAmount": 300,
        "Items": [
            {"name": "Veg Burger", "qty": 2, "price": 150},
        ],
    },
]

SAMPLE_STATUS_EVENTS = [
    {"OrderId": "ORD-1001", "StatusTimestamp": "2026-06-10T14:30:00",
     "Status": "PLACED", "Note": "Order placed"},
    {"OrderId": "ORD-1001", "StatusTimestamp": "2026-06-10T14:35:00",
     "Status": "ACCEPTED", "Note": "Restaurant accepted"},
    {"OrderId": "ORD-1001", "StatusTimestamp": "2026-06-10T14:50:00",
     "Status": "OUT_FOR_DELIVERY", "Note": "Rider picked up the order"},
    {"OrderId": "ORD-1001", "StatusTimestamp": "2026-06-10T15:10:00",
     "Status": "DELIVERED", "Note": "Delivered to customer"},
    {"OrderId": "ORD-1002", "StatusTimestamp": "2026-06-12T19:15:00",
     "Status": "PLACED", "Note": "Order placed"},
    {"OrderId": "ORD-1002", "StatusTimestamp": "2026-06-12T19:20:00",
     "Status": "ACCEPTED", "Note": "Restaurant accepted"},
    {"OrderId": "ORD-1002", "StatusTimestamp": "2026-06-12T19:40:00",
     "Status": "OUT_FOR_DELIVERY", "Note": "Rider picked up the order"},
    {"OrderId": "ORD-1003", "StatusTimestamp": "2026-06-11T13:00:00",
     "Status": "PLACED", "Note": "Order placed"},
]


# ──────────────────────────────────────────────────────────────────────────
# Create
# ──────────────────────────────────────────────────────────────────────────
def _table_exists(name):
    try:
        _client.describe_table(TableName=name)
        return True
    except _client.exceptions.ResourceNotFoundException:
        return False


def create_tables():
    if _table_exists(ORDERS_TABLE):
        print(f"  {ORDERS_TABLE} already exists")
    else:
        _client.create_table(
            TableName=ORDERS_TABLE,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "OrderId", "AttributeType": "S"},
                {"AttributeName": "CustomerId", "AttributeType": "S"},
                {"AttributeName": "RestaurantId", "AttributeType": "S"},
                {"AttributeName": "OrderCreatedAt", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "OrderId", "KeyType": "HASH"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "CustomerOrdersIndex",
                    "KeySchema": [
                        {"AttributeName": "CustomerId", "KeyType": "HASH"},
                        {"AttributeName": "OrderCreatedAt", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "RestaurantOrdersIndex",
                    "KeySchema": [
                        {"AttributeName": "RestaurantId", "KeyType": "HASH"},
                        {"AttributeName": "OrderCreatedAt", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
        )
        print(f"  creating {ORDERS_TABLE} (with CustomerOrdersIndex, RestaurantOrdersIndex) ...")

    if _table_exists(STATUS_TABLE):
        print(f"  {STATUS_TABLE} already exists")
    else:
        _client.create_table(
            TableName=STATUS_TABLE,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "OrderId", "AttributeType": "S"},
                {"AttributeName": "StatusTimestamp", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "OrderId", "KeyType": "HASH"},
                {"AttributeName": "StatusTimestamp", "KeyType": "RANGE"},
            ],
        )
        print(f"  creating {STATUS_TABLE} ...")

    for name in (ORDERS_TABLE, STATUS_TABLE):
        _client.get_waiter("table_exists").wait(TableName=name)
        print(f"  {name} is ACTIVE")


# ──────────────────────────────────────────────────────────────────────────
# Seed
# ──────────────────────────────────────────────────────────────────────────
def seed_data():
    orders = _dynamodb.Table(ORDERS_TABLE)
    with orders.batch_writer() as batch:
        for order in SAMPLE_ORDERS:
            batch.put_item(Item=order)
    print(f"  inserted {len(SAMPLE_ORDERS)} orders into {ORDERS_TABLE}")

    status = _dynamodb.Table(STATUS_TABLE)
    with status.batch_writer() as batch:
        for event in SAMPLE_STATUS_EVENTS:
            batch.put_item(Item=event)
    print(f"  inserted {len(SAMPLE_STATUS_EVENTS)} status events into {STATUS_TABLE}")


# ──────────────────────────────────────────────────────────────────────────
# Demo: exercise every access pattern
# ──────────────────────────────────────────────────────────────────────────
def demo():
    orders = _dynamodb.Table(ORDERS_TABLE)
    status = _dynamodb.Table(STATUS_TABLE)

    print("\n[1] All orders for customer C001 (CustomerOrdersIndex, newest first)")
    resp = orders.query(
        IndexName="CustomerOrdersIndex",
        KeyConditionExpression=Key("CustomerId").eq("C001"),
        ScanIndexForward=False,
    )
    for item in resp["Items"]:
        print(f"    {item['OrderId']}  {item['OrderCreatedAt']}  "
              f"{item['CurrentStatus']}  INR {item['TotalAmount']}")

    print("\n[2] Status timeline for ORD-1001 (food-order-status-history)")
    resp = status.query(KeyConditionExpression=Key("OrderId").eq("ORD-1001"))
    for item in resp["Items"]:
        print(f"    {item['StatusTimestamp']}  {item['Status']:16}  {item['Note']}")

    print("\n[3] Order details for ORD-1001 (GetItem by OrderId)")
    item = orders.get_item(Key={"OrderId": "ORD-1001"}).get("Item", {})
    print(f"    Customer={item.get('CustomerId')}  Restaurant={item.get('RestaurantId')}  "
          f"Status={item.get('CurrentStatus')}  Total=INR {item.get('TotalAmount')}")

    print("\n[4] Restaurant dashboard for R001 (RestaurantOrdersIndex, newest first)")
    resp = orders.query(
        IndexName="RestaurantOrdersIndex",
        KeyConditionExpression=Key("RestaurantId").eq("R001"),
        ScanIndexForward=False,
    )
    for item in resp["Items"]:
        print(f"    {item['OrderId']}  {item['OrderCreatedAt']}  "
              f"from {item['CustomerId']}  {item['CurrentStatus']}")


# ──────────────────────────────────────────────────────────────────────────
# Teardown
# ──────────────────────────────────────────────────────────────────────────
def teardown():
    for name in (ORDERS_TABLE, STATUS_TABLE):
        if _table_exists(name):
            _client.delete_table(TableName=name)
            _client.get_waiter("table_not_exists").wait(TableName=name)
            print(f"  deleted {name}")
        else:
            print(f"  {name} does not exist")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    command = sys.argv[1]
    try:
        if command == "create":
            create_tables()
        elif command == "seed":
            seed_data()
        elif command == "demo":
            demo()
        elif command == "all":
            create_tables()
            seed_data()
            demo()
        elif command == "teardown":
            teardown()
        else:
            print(__doc__)
    except NoCredentialsError:
        print("Error: AWS credentials not found. Set AWS_ACCESS_KEY_ID, "
              "AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN, and AWS_REGION, then retry.")
        sys.exit(1)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "Unknown")
        if code in {"ExpiredTokenException", "InvalidClientTokenId", "UnrecognizedClientException"}:
            print("Error: AWS credentials are invalid or expired. Refresh them and retry.")
        else:
            print(f"Error: DynamoDB request failed ({code}): {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
