import os
import re
import time
from datetime import datetime

import aiohttp
import boto3
import discord

SAVE_DIR = "tmp_audio"
S3_BUCKET = os.getenv("S3_BUCKET")
S3_PREFIX = os.getenv("S3_PREFIX")
AWS_REGION = os.getenv("AWS_REGION", "us-west-2")

os.makedirs(SAVE_DIR, exist_ok=True)

intents = discord.Intents.default()
# 「変換」などメッセージ本文を読むために必要（Developer Portal側でも Message Content Intent を有効化する）
intents.message_content = True
client = discord.Client(intents=intents)

s3 = boto3.client("s3", region_name=AWS_REGION)
transcribe = boto3.client("transcribe", region_name=AWS_REGION)


def find_latest_audio_s3_key(bucket: str, prefix: str) -> str:
    resp = s3.list_objects_v2(Bucket=bucket, Prefix=f"{prefix}/")
    contents = resp.get("Contents", [])
    if not contents:
        raise Exception("S3に音声が見つかりません")
    latest = max(contents, key=lambda x: x["LastModified"])
    return latest["Key"]


def start_transcribe_for_s3_audio(bucket: str, s3_key: str) -> str:
    base = os.path.basename(s3_key)
    # Transcribe のジョブ名に使えない文字があると失敗するため安全化
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", base)
    job_name = f"discord-{int(time.time())}-{safe}"[:200]

    transcribe.start_transcription_job(
        TranscriptionJobName=job_name,
        LanguageCode="ja-JP",
        MediaFormat=base.split(".")[-1].lower(),
        Media={"MediaFileUri": f"s3://{bucket}/{s3_key}"},
        OutputBucketName=bucket,
        OutputKey=f"transcribe-output/{job_name}.json",
    )
    return job_name


@client.event
async def on_ready():
    print(f"Logged in as: {client.user}")


@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # 「変換」は添付が無いので最初に判定して早期returnする
    if message.content.strip() == "変換":
        try:
            if not S3_BUCKET or not S3_PREFIX:
                raise Exception("環境変数 S3_BUCKET / S3_PREFIX が未設定です")

            latest_key = find_latest_audio_s3_key(S3_BUCKET, S3_PREFIX)
            job_name = start_transcribe_for_s3_audio(S3_BUCKET, latest_key)

            await message.channel.send(
                "🎤 文字起こしを開始しました。\n"
                f"対象: s3://{S3_BUCKET}/{latest_key}\n"
                f"ジョブ名: {job_name}"
            )
        except Exception as e:
            await message.channel.send(f"❌ 変換開始に失敗: {e}")
        return

    if not message.attachments:
        return

    for attachment in message.attachments:
        if not attachment.filename.lower().endswith((".ogg", ".wav", ".mp3", ".m4a", ".webm")):
            continue

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_filename = f"{timestamp}_{message.id}_{attachment.filename}"
        save_path = os.path.join(SAVE_DIR, save_filename)

        async with aiohttp.ClientSession() as session:
            async with session.get(attachment.url) as resp:
                data = await resp.read()
        with open(save_path, "wb") as f:
            f.write(data)

        s3_key = f"{S3_PREFIX}/{save_filename}"
        s3.upload_file(save_path, S3_BUCKET, s3_key)

        await message.channel.send(f"音声を受信しました。\n" f"s3://{S3_BUCKET}/{s3_key}")


client.run(os.getenv("DISCORD_BOT_TOKEN"))
