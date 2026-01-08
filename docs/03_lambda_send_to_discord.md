# 03_lambda_send_to_discord.md

## 文字起こし結果を Discord に通知

（Amazon Transcribe → Lambda → Discord Webhook）

---

## 概要

本ドキュメントでは、**Amazon Transcribe によって生成された文字起こし結果を、Discord に自動通知する仕組み**について説明する。

本章は、以下が **正常に動作していることを前提**とする。

* Amazon Transcribe のジョブが正常に完了する
* Transcribe の `COMPLETED` イベントを EventBridge が検知する
* EventBridge 経由で Lambda が起動する
  （※ 手順書②参照）

本章では、②で作成した Lambda に以下の処理を追加する。

* Transcribe ジョブ詳細の取得
* 出力された JSON ファイルの S3 取得
* 文字起こし本文の抽出
* Discord Webhook への通知

---

## ゴール（到達状態）

* Transcribe ジョブ完了時に Lambda が自動実行される
* Transcribe の出力 JSON を S3 から取得できる
* 文字起こし本文を抽出できる
* 抽出したテキストが Discord に自動投稿される

---

## 全体構成（本章で扱う範囲）

```
Amazon Transcribe（文字起こし完了）
   ↓
EventBridge（COMPLETED イベント）
   ↓
AWS Lambda
   ├─ Transcribe ジョブ詳細取得
   ├─ S3 から JSON 取得
   └─ Discord Webhook 通知
```

---

## 1. Lambda の役割（③で追加される処理）

本章で Lambda に追加される責務は以下の通り。

* EventBridge から Transcribe 完了イベントを受信
* Transcribe API を使用してジョブ詳細を取得
* 出力された JSON ファイルを S3 から取得
* 文字起こし本文を抽出
* Discord Webhook を使って通知


---

## 2. Discord Webhook の準備

### 2.1 Webhook 作成

1. Bot を追加した Discord サーバーで以下を実施

   * サーバー設定 → 連携サービス → Webhook
2. Webhook を作成し、URL をコピーする

---

### 2.2 Lambda 環境変数の設定

Lambda → 設定 → 環境変数 に以下を追加する。
※ EC2 上の Bot は .env で環境変数を管理するが、
Lambda はマネージドサービスのため、
環境変数は Lambda 設定画面で直接管理する。


| 変数名                 | 内容                       |
| ------------------- | ------------------------ |
| DISCORD_WEBHOOK_URL | 作成した Discord Webhook URL |

---

## 3. IAM 追加権限（Lambda 実行ロール）

手順書②では CloudWatch Logs 出力のみを許可していたが、
本章では以下の操作が必要となる。

* Transcribe ジョブ詳細の取得
* S3 上の文字起こし結果 JSON の取得

### 3.1 追加する IAM ポリシー

Lambda 実行ロールに **インラインポリシー**として以下を追加する。

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "transcribe:GetTranscriptionJob",
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "*"
    }
  ]
}
```

※ 学習用のため `Resource: "*"` を使用

---

## 4. Lambda コード（文字起こし取得 → Discord 通知）
コメントなし配置場所:src/lambda/transcribe_to_discord/lambda_function.py
※ 本章では理解しやすさのためコメント付きで掲載する。
GitHub 上のコードはコメントを最小限に整理して配置する。
```python
import json
import urllib.request
import boto3
import os
from urllib.parse import urlparse

# AWS SDK (boto3) を使って S3 にアクセスするためのクライアントを作成
# Lambda 実行ロールの IAM 権限で認証される
s3 = boto3.client("s3")

#Discord Webhook にメッセージを送信する関数
def send_to_discord(text):
    # Lambda の環境変数から Discord Webhook URL を取得
    webhook_url = os.environ["DISCORD_WEBHOOK_URL"]

    # Discord に送る本文（JSON形式）
    payload = {"content": text}

    # Discord が Bot 判定しないようにするための必須ヘッダ
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    }

    # HTTP POST リクエストを明示的に作成
    # method="POST" を指定しないと Discord 側で 403 になることがある
    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )

    # Webhook にリクエスト送信（成功すると Discord に投稿される）
    urllib.request.urlopen(req)


def lambda_handler(event, context):
    # EventBridge から呼び出される Lambda のエントリーポイント
    # EventBridge から渡されたイベント全体をログに出す（デバッグ用）
    print("event:", json.dumps(event))

    # Transcribe のジョブ名を取得
    # 例: test-job-20260106
    job_name = event["detail"]["TranscriptionJobName"]

    # Transcribe ジョブの状態を取得
    # COMPLETED / IN_PROGRESS / FAILED など
    status = event["detail"]["TranscriptionJobStatus"]

    # 完了以外のイベント（IN_PROGRESS 等）は処理しない
    if status != "COMPLETED":
        print("Job not complete. skip")
        return

    # --- Amazon Transcribe の詳細情報を取得 ---
    # job_name を使って Transcribe API からジョブ情報を取得
    transcribe = boto3.client("transcribe")
    job = transcribe.get_transcription_job(
        TranscriptionJobName=job_name
    )

    # Transcribe が出力した JSON ファイルの S3 URL を取得
    # 例: https://s3.us-west-2.amazonaws.com/bucket/path/result.json
    uri = job["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]

    # URL を分解して S3 の bucket 名と key を取り出す
    parsed = urlparse(uri)
    path = parsed.path.lstrip('/')      # 先頭の / を削除
    bucket, key = path.split('/', 1)    # bucket と key に分離

    print(f"Fetch JSON from S3 -> bucket={bucket}, key={key}")

    # --- S3 から文字起こし結果 JSON を取得 ---
    # boto3 を使うことで IAM 認証付きで安全に取得できる
    obj = s3.get_object(Bucket=bucket, Key=key)

    # JSON ファイルの中身を文字列として読み込む
    body = obj["Body"].read().decode("utf-8")

    # JSON を Python の dict に変換
    result = json.loads(body)

    # Transcribe の結果から本文（文字起こしテキスト）を取得
    text = result["results"]["transcripts"][0]["transcript"]

    # Discord の 2000文字制限対策
    # 長すぎる場合は 1900 文字でカット
    if len(text) > 1900:
        text = text[:1900] + " ...(省略)"

    # Discord Webhook に文字起こし結果を送信
    send_to_discord(f"🎤 文字起こし完了したよ！\n\n{text}")
```

---

## 5. 動作確認

1. S3 に保存されている音声ファイルを Transcribe で文字起こし
2. ジョブ完了（COMPLETED）時に EventBridge が発火
3. Lambda が自動実行される
4. Discord に文字起こし結果が投稿される

---
👉 次章：`04_slash_command_ec2_control.md`


---

