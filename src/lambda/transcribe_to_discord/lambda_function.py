import json
import urllib.request
import boto3
import os
from urllib.parse import urlparse

s3 = boto3.client("s3")

def send_to_discord(text):
    webhook_url = os.environ["DISCORD_WEBHOOK_URL"]
    payload = {"content": text}
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    }
    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    urllib.request.urlopen(req)

def lambda_handler(event, context):
    print("event:", json.dumps(event))
    
    job_name = event["detail"]["TranscriptionJobName"]
    status = event["detail"]["TranscriptionJobStatus"]

    if status != "COMPLETED":
        print("Job not complete. skip")
        return

    transcribe = boto3.client("transcribe")
    job = transcribe.get_transcription_job(TranscriptionJobName=job_name)
    uri = job["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]

    parsed = urlparse(uri)
    path = parsed.path.lstrip('/')
    bucket, key = path.split('/', 1)

    print(f"Fetch JSON from S3 -> bucket={bucket}, key={key}")

    obj = s3.get_object(Bucket=bucket, Key=key)
    body = obj["Body"].read().decode("utf-8")
    result = json.loads(body)

    text = result["results"]["transcripts"][0]["transcript"]

    if len(text) > 1900:
        text = text[:1900] + " ...(省略)"

    send_to_discord(f"🎤 文字起こし完了したよ！\n\n{text}")
