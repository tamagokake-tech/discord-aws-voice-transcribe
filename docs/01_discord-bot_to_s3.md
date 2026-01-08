
# 01_discord-bot_to_s3.md

## Discord 音声投稿 → S3 保存（Transcribe 実行前まで）
---

## 概要

本ドキュメントでは、**Discord に投稿された音声ファイルを検知し、AWS S3 に自動保存するまで**の構成と手順を説明する。

本章の範囲は以下までとする。

- Discord Bot の作成
- 音声ファイルの検知
- EC2 上での Bot 実行
- 音声ファイルのローカル保存
- S3 へのアップロード

※
Amazon Transcribe の自動実行・完了通知（EventBridge / Lambda）は **本章では扱わない**。
※ 本構成では EC2 / S3 / Amazon Transcribe は同一リージョン（us-west-2）で構成する。

---

## ゴール（到達状態）

- Discord に音声メッセージを投稿できる
- Discord Bot が音声ファイルを検知する
- 音声ファイルが EC2 ローカルに一時保存される
- 音声ファイルが S3 にアップロードされる
- Amazon Transcribe を **手動で実行して検証できる状態**になっている

---

## 全体構成（この章で扱う範囲）

```
Discord（音声投稿）
   ↓
Discord Bot（Python / EC2）
   ↓
ローカル保存（tmp_audio）
   ↓
Amazon S3（音声入力用バケット）
```

※ S3 以降の Transcribe / EventBridge / Lambda は次章以降で扱う。

---

## 1. Discord Bot の作成

### 1.1 Discord Developer Portal

以下にアクセスする。
[https://discord.com/developers/applications](https://discord.com/developers/applications)

1. 「New Application」を選択
2. アプリ名を入力（例：`voice-transcribe-bot`）
3. 作成後、「Bot」→「Add Bot」を選択

---

### 1.2 Bot Token の取得

- Bot 画面にて「Reset Token」を選択
- 表示されたトークンを控える

⚠ **このトークンは外部に漏らさないこと**

---

### 1.3 Bot 権限設定

#### Privileged Gateway Intents

- MESSAGE CONTENT INTENT：**有効**

#### Bot Permissions

- Send Messages
- Read Message History

---

### 1.4 Bot をサーバーに招待

1. OAuth2 → URL Generator
2. Scopes：`bot`
3. Permissions：

   - Send Messages
   - Read Message History

4. 生成された URL からサーバーに招待する

---

## 2. Bot 実行環境（EC2）

### 2.1 EC2 作成と作業ディレクトリ

AWS 上で EC2 を作成し、SSH 接続する。

```bash
mkdir discord-transcribe-bot-test
cd discord-transcribe-bot-test
```

---

### 2.2 Python 仮想環境（venv）作成

```bash
sudo dnf update
python3 --version
python3 -m venv venv
```

※ Amazon Linux 標準の Python 3.9 を使用
※ 学習用途のため警告は問題なし

---

### 2.3 仮想環境の有効化

```bash
source venv/bin/activate
```

プロンプト例：

```text
(venv) [root@discord-test discord-transcribe-bot-test]#
```

---

### 2.4 必要ライブラリのインストール

```bash
pip install discord.py aiohttp boto3
```

| ライブラリ | 用途                             |
| ---------- | -------------------------------- |
| discord.py | Discord Bot 実装                 |
| aiohttp    | 音声ファイルの非同期ダウンロード |
| boto3      | AWS（S3 / Transcribe 等）操作    |

---

## 3. AWS 側の準備

### 3.1 S3 バケット作成

- バケット名例：`user-transcribe-audio`
- リージョン：`us-west-2`
- パブリックアクセス：すべてブロック
- SSE：SSE-S3

---

### 3.2 バケット内構成

```
user-transcribe-audio/
├─ discord-audio/        # Bot がアップロードする音声
└─ transcribe-output/    # Transcribe 出力（次章以降）
```

---

### 3.3 IAM（Bot 用ロール）

EC2 に IAM ロールをアタッチする。

※ 学習目的のため、以下を使用：

- AmazonS3FullAccess
- AmazonTranscribeFullAccess

---

## 4. Bot プログラム（音声検知 → S3）

### 4.1 ディレクトリ構成

```
discord-transcribe-bot/
├─ bot.py
├─ tmp_audio/
├─ .env
└─ venv/
```

---

### 4.2 .env ファイル作成

```bash
vi .env
```

```env
DISCORD_BOT_TOKEN=xxxxxxxx
S3_BUCKET=example-transcribe-audio
S3_PREFIX=discord-audio
AWS_REGION=us-west-2
```

```bash
chmod 600 .env
```

---

### 4.3 bot.py（音声検知〜S3 アップロード）

コメントなし配置場所:
src/bot/bot.py

※ 本章では理解するために役割コメント付きで掲載します。

```python
import discord
import aiohttp
import os
from datetime import datetime
import boto3

# ========================
# 設定（音声を一時保存してから S3 にアップロードする）
# ========================

# ローカル（EC2）の一時保存ディレクトリ
SAVE_DIR = "tmp_audio"

# アップロード先の S3 バケット名（固定）
S3_BUCKET = os.getenv("S3_BUCKET")

# S3 内の保存先プレフィックス名（S3内のフォルダのようなもの）
S3_PREFIX = os.getenv("S3_PREFIX")

# リージョン設定
AWS_REGION = os.getenv("AWS_REGION", "us-west-2")

# 一時保存用フォルダが無ければ作成
os.makedirs(SAVE_DIR, exist_ok=True)

# ========================
# Discord クライアント初期化
# ========================

# Bot がどのイベント（通知）を受け取るかを設定
intents = discord.Intents.default()

# メッセージ本文や添付ファイルに反応するために記載
# ※ Developer Portal 側でも "Message Content Intent" を ON にする
intents.message_content = True

# Discord クライアント（Discordにつなぎつつ待機する部分）を作成
client = discord.Client(intents=intents)

# ========================
# AWS S3 クライアント初期化
# ========================

# boto3 で S3 にアップロードするためのクライアントを作成
s3 = boto3.client("s3", region_name=AWS_REGION)

# ========================
# Discord イベント: 起動完了時
# ========================
@client.event
async def on_ready():
    # Bot が Discord にログインできたら表示
    print(f"ログインしました: {client.user}")

# ========================
# Discord イベント: メッセージ受信時
# ========================
@client.event
async def on_message(message):
    # Bot 自身や他の Bot の投稿には反応しない（無限ループ防止）
    if message.author.bot:
        return

    # 添付ファイル（attachments）がある投稿だけ処理
    if message.attachments:
        for attachment in message.attachments:

            # 音声っぽい拡張子だけ対象にする
            if attachment.filename.lower().endswith(
                (".ogg", ".wav", ".mp3", ".m4a", ".webm")
            ):
                # 例: 20260105_171530_ のようなタイムスタンプを作成
                now = datetime.now()
                timestamp = now.strftime("%Y%m%d_%H%M%S")

                # 保存ファイル名を一意にする（時刻 + message.id + 元ファイル名）
                save_filename = f"{timestamp}_{message.id}_{attachment.filename}"

                # ローカル保存パス（ディレクトリとファイル名を結合）
                save_path = os.path.join(SAVE_DIR, save_filename)

                # Discord の添付ファイル URL からデータをダウンロード
                async with aiohttp.ClientSession() as session:
                    async with session.get(attachment.url) as resp:
                        data = await resp.read()

                        # ローカルにバイナリとして保存
                        with open(save_path, "wb") as f:
                            f.write(data)

                # S3 にアップロードするキー（保存先パス）
                # 例: discord-audio/20260105_..._sample.ogg
                s3_key = f"{S3_PREFIX}/{save_filename}"

                # ローカルに保存したファイルを S3 にアップロード
                s3.upload_file(save_path, S3_BUCKET, s3_key)

                # Discord に「アップロード完了」を通知
                await message.channel.send(
                    f"音声を受信しました。\n"
                    f"s3://{S3_BUCKET}/{s3_key}"
                )

# ========================
# 起動（環境変数から Bot トークンを取得してログイン）
# ========================

# 環境変数 DISCORD_BOT_TOKEN を読み取って Discord にログインして常駐開始
client.run(os.getenv("DISCORD_BOT_TOKEN"))
```

---

## 5. 動作確認（手動起動）

### 5.1 環境変数読み込み

```bash
source venv/bin/activate
set -a
source .env
set +a
```

---

### 5.2 Bot 起動

```bash
python bot.py
```

---

### 5.3 確認内容

- Discord に音声を投稿
- Bot が反応する
- S3 にファイルが保存される

```
s3://user-transcribe-audio/discord-audio/
└─ 20251224_113721_xxxxx_voice-message.ogg
```

---

👉 次章：`02_transcribe_eventbridge_lambda.md`
