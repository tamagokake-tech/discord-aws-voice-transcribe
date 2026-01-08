# 05_systemd_autostart_bot.md

## EC2 起動時に Discord Bot（Python）を自動起動する

（systemd による常駐化）

---

## 概要

本ドキュメントでは、**EC2 の起動と同時に Discord Bot（Python）を自動起動し、常駐させる方法**を説明する。

本章の目的は以下の通り。

* EC2 起動時に Bot を **自動起動**させる
* Discord に音声が投稿されたら **即座に処理できる状態**にする
* `python bot.py` を手動実行する運用を廃止する

---

## ゴール（到達状態）

* EC2 を起動すると Discord Bot が自動起動する
* Bot は常駐し続け、音声投稿を待ち受ける
* Discord に投稿された音声が自動で S3 に保存される

---

## 全体構成（本章で扱う範囲）

```
EC2 起動
   ↓
systemd
   ↓
Discord Bot（Python）
   ↓
Discord 音声投稿を常時待機
   ↓
S3 に自動保存
```

---

## 1. systemd サービスの作成

### 1.1 EC2 にログイン

```bash
ssh ec2-user@<EC2のIP>
# または
ssh root@<EC2のIP>
```

---

### 1.2 systemd ディレクトリへ移動

```bash
cd /etc/systemd/system/
```

---

### 1.3 サービスファイルを作成

```bash
vi discord-bot.service
```

---

## 2. discord-bot.service の内容
コード配置場所:systemd/discord-bot.service
```ini
[Unit]
Description=Discord Voice Transcribe Bot
# ネットワークが利用可能になってから起動
After=network.target

[Service]
Type=simple
User=root

# 実行時のカレントディレクトリ
WorkingDirectory=/root/discord-transcribe-bot-test

# 環境変数ファイルの読み込み
EnvironmentFile=/etc/systemd/system/discord-bot.env

# Bot 起動コマンド
ExecStart=/root/discord-transcribe-bot-test/venv/bin/python bot.py

# Bot が異常終了した場合は自動再起動
Restart=always

# 再起動までの待機秒数
RestartSec=5

[Install]
# マルチユーザー環境で起動
WantedBy=multi-user.target
```

### 補足

* `After=network.target`
  → Discord API / S3 へ通信するため、ネットワーク初期化後に起動する
* `Restart=always`
  → Bot が例外終了しても自動復旧する
* `WorkingDirectory`
  → 相対パス（bot.py / tmp_audio）の事故防止

---

## 3. 環境変数ファイルの作成（重要）

systemd から起動されるプロセスは、
**ログインシェルの `.env` を自動では読み込まない**。

そのため、systemd 用の環境変数ファイルを別途用意する。

---

### 3.1 systemd 用環境変数ファイル作成
コード配置場所:systemd/discord-bot.env
```bash
vi /etc/systemd/system/discord-bot.env
```

```env
DISCORD_BOT_TOKEN=xxxxxxxxxxxxxxxx
S3_BUCKET=your-bucket-name
S3_PREFIX=discord-audio
AWS_REGION=us-west-2
```

```bash
chmod 600 /etc/systemd/system/discord-bot.env
```

### 補足

* `discord-transcribe-bot-test/.env` と **同じ内容**
* `.env` は手動起動用として残しても問題なし
* 本ファイルは **systemd 用に昇格させた env** という位置づけ
* `bot.py` 側は `os.getenv()` のままで動作する

---

## 4. systemd に反映・自動起動設定

```bash
systemctl daemon-reload
systemctl enable discord-bot.service
systemctl restart discord-bot.service
```

### 状態確認

```bash
systemctl status discord-bot.service
```

以下が表示されれば成功。

```
Active: active (running)
```

---

## 5. 動作確認

### 5.1 Discord から EC2 を起動

* Slash Command + Lambda 経由で EC2 を起動する

---

### 5.2 EC2 起動と同時に Bot が自動起動

* systemd により Bot が自動で立ち上がる
* 手動実行は不要

---

### 5.3 Discord で音声を投稿

* Discord のボイスメモ機能で音声を投稿する

---

### 5.4 成功時の挙動

Discord 上に以下が表示される。

```
音声を受信しました。
s3://<バケット名>/<プレフィックス>/<ファイル名>
```

S3 側にも音声ファイルが保存されていれば完了。

---

👉 次章：`06_discord_convert_command_transcribe.md`

---
