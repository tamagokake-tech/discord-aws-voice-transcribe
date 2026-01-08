# 06_discord_convert_command_transcribe.md

## Discord「変換」コマンドで最新音声を自動文字起こしする

（Bot → Amazon Transcribe → EventBridge → Lambda → Discord）

---

## 概要

本ドキュメントでは、**Discord 上で「変換」と送信することで、最新の音声ファイルを自動検出し、Amazon Transcribe による文字起こしを開始する仕組み**について説明する。

本章は以下の構成が **すでに正常に動作していることを前提**とする。

* Discord 音声投稿 → S3 保存（①）
* Amazon Transcribe 完了イベント検知（②）
* 文字起こし結果の Discord 通知（③）
* EC2 / Bot の常駐化（⑤）

---

## この手順書で実現すること

```
Discord に音声を投稿
   ↓
S3 に自動保存
   ↓
Discord で「変換」と送信
   ↓
最新の音声ファイルを自動検出
   ↓
Amazon Transcribe を起動
   ↓
（完了）
EventBridge → Lambda → Discord に結果通知
```

---

## 1. EC2 の IAM ロール権限確認

Bot が Transcribe を起動するため、EC2 にアタッチされた IAM ロールに
以下の権限が付与されていることを確認する。

* `AmazonS3FullAccess`
* `AmazonTranscribeFullAccess`

確認手順：

```
EC2 → 対象インスタンス
 → セキュリティ
 → IAM ロール
```

---

## 2. 「変換」機能の設計思想（重要）

### なぜ Bot 側で Transcribe を起動するのか

* EventBridge だけを使うと
  **「音声が S3 に置かれたら即文字起こし」** になる
* 本構成では **人間の意思（「変換」と打つ）をトリガー** にしたい

これにより、以下が可能になる。

* 不要な文字起こしを防ぐ（コスト制御）
* 誤って投稿した音声を変換しない
* 同じ音声を後から再実行できる

### 役割分担

* **Discord Bot（EC2）**

  * いつ変換するかを制御
  * どの音声を使うかを決定
* **Lambda（EventBridge 経由）**

  * 文字起こし完了の検知
  * 結果の通知のみを担当

---

## 3. 処理全体の流れ（⑥で追加される部分）

```
Discord で「変換」
   ↓
S3（discord-audio/）から最新音声を検索
   ↓
Amazon Transcribe を start
   ↓
（COMPLETED）
EventBridge → Lambda → Discord 通知
```

---

## 4. bot.py に追加する処理
コード配置場所：`src/bot/bot.py`

### 4.1 追加で使用するライブラリ

```python
import time   # ジョブ名に時刻を含めて衝突防止
import re     # S3キーから安全なジョブ名を生成するため
```

---

### 4.2 Transcribe 用クライアント初期化

```python
transcribe = boto3.client("transcribe", region_name=AWS_REGION)
```

---

### 4.3 最新の音声ファイルを S3 から取得する関数

```python
def find_latest_audio_s3_key(bucket: str, prefix: str) -> str:
    """
    S3の prefix（例: discord-audio/）配下にあるファイル一覧を取得し、
    LastModified が最も新しいオブジェクトの Key を返す。
    """
    resp = s3.list_objects_v2(Bucket=bucket, Prefix=f"{prefix}/")
    contents = resp.get("Contents", [])

    if not contents:
        raise Exception("S3に音声が見つかりません")

    latest = max(contents, key=lambda x: x["LastModified"])
    return latest["Key"]
```

---

### 4.4 Transcribe ジョブを開始する関数

```python
def start_transcribe_for_s3_audio(bucket: str, s3_key: str) -> str:
    base = os.path.basename(s3_key)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", base)

    job_name = f"discord-{int(time.time())}-{safe}"[:200]
    media_uri = f"s3://{bucket}/{s3_key}"
    output_key = f"transcribe-output/{job_name}.json"
    media_format = base.split(".")[-1].lower()

    transcribe.start_transcription_job(
        TranscriptionJobName=job_name,
        LanguageCode="ja-JP",
        MediaFormat=media_format,
        Media={"MediaFileUri": media_uri},
        OutputBucketName=bucket,
        OutputKey=output_key
    )

    return job_name
```

---

### 4.5 「変換」コマンド処理（on_message 内）

```python
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
```

※
この処理は **添付ファイル処理より前に配置**する。
（テキストメッセージのため、先に判定しないと無駄な処理が走る）

---

## 5. 実際の操作手順（重要）

### 手順①：EC2 を起動

```text
/ec2 action:start
```

Bot の返信例：

```
EC2 を起動しました
```

---

### 手順②：音声を収録

* Discord のマイクボタンで音声を投稿

Bot の返信例：

```
音声を受信しました。
s3://user-transcribe-audio/discord-audio/xxxx.ogg
```

---

### 手順③：「変換」と送信

```text
変換
```

Bot の返信例：

```
🎤 文字起こしを開始しました。
対象: s3://user-transcribe-audio/discord-audio/xxxx.ogg
ジョブ名: discord-1736060000-xxxx
```

---

### 手順④：待機（30秒〜数分）

* Amazon Transcribe が処理を実行
* ジョブが `COMPLETED` になると EventBridge が発火

---

### 手順⑤：文字起こし結果が Discord に届く

Lambda → Discord Webhook により通知される。

例：

```
🎤 文字起こし完了したよ！
今日は○○を行いました。
```

---



