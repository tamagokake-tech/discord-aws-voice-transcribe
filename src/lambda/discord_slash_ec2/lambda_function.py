import os
import json
import base64
import boto3
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError
from nacl.encoding import HexEncoder

INSTANCE_ID = "i-0ff70c1adaf1caf92"
ec2 = boto3.client("ec2", region_name="us-west-2")

def verify(pubkey, headers, raw_body):
    sig = headers.get("x-signature-ed25519")
    ts = headers.get("x-signature-timestamp")
    if not sig or not ts:
        return False

    vk = VerifyKey(pubkey, encoder=HexEncoder)
    try:
        vk.verify((ts + raw_body).encode(), bytes.fromhex(sig))
        return True
    except BadSignatureError:
        return False

def lambda_handler(event, context):
    pubkey = os.environ.get("DISCORD_PUBLIC_KEY")
    if not pubkey:
        return {"statusCode": 500, "body": "missing public key"}

    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}

    raw_body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw_body = base64.b64decode(raw_body).decode("utf-8")

    # ① 署名検証
    if not verify(pubkey, headers, raw_body):
        return {"statusCode": 401, "body": "invalid signature"}

    body = json.loads(raw_body)

    # ② PING → PONG
    if body.get("type") == 1:
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"type": 1}),
        }

    # ③ /ec2 action:xxx
    if body.get("type") == 2:
        options = body["data"].get("options", [])
        action = options[0]["value"] if options else None

        if action == "start":
            ec2.start_instances(InstanceIds=[INSTANCE_ID])
            content = "EC2 を起動しました"
        elif action == "stop":
            ec2.stop_instances(InstanceIds=[INSTANCE_ID])
            content = "EC2 を停止しました"
        elif action == "status":
            res = ec2.describe_instances(InstanceIds=[INSTANCE_ID])
            inst = res["Reservations"][0]["Instances"][0]
            state = inst["State"]["Name"]
            content = f"現在の状態: {state}"
        else:
            content = "不明な action です"

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "type": 4,
                "data": {"content": content}
            }),
        }

    return {"statusCode": 200, "body": "ok"}