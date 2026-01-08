# Discord × AWS 音声文字起こし Bot

Discord に投稿された音声を AWS に保存し、  
**任意のタイミングで文字起こしを実行・結果を Discord に返す** システムです。

AWS サービス連携（EC2 / S3 / Lambda / EventBridge / Transcribe）を学ぶ目的で作成しました。

---

## 何ができるのか

- Discord に音声を投稿すると S3 に自動保存
- Discord の「変換」コマンドで文字起こしを開始
- Lambda 経由で文字起こし結果を Discord に自動通知
- Slash Command で EC2 の起動 / 停止 / 状態確認が可能

---

## 全体構成

```
Discord
├─ 音声投稿
└─ Slash Command
    ↓
EC2（Discord Bot）
├─ 音声を S3 に保存
└─ Transcribe ジョブ起動
    ↓
Amazon Transcribe
    ↓（COMPLETED）
EventBridge
    ↓
Lambda
    ↓
Discord Webhook（結果通知）
```

---

## 使用技術

* Discord Bot / Slash Command
* AWS EC2 / S3 / Lambda / EventBridge
* Amazon Transcribe
* Python / boto3 / discord.py
* systemd（EC2 起動時の自動起動）

---

## ドキュメント

* [① Discord 音声投稿 → S3 保存（Transcribe 実行前まで）](docs/01_discord-bot_to_s3.md)
* [② 文字起こし完了イベント検知](docs/02_transcribe_eventbridge_lambda.md)
* [③ 文字起こし結果を Discord に通知](docs/03_lambda_send_to_discord.md)
* [④ Discord Slash Command から EC2 を起動・停止・状態確認する](docs/04_slash_command_ec2_control.md)
* [⑤ EC2 起動時に Discord Bot（Python）を自動起動する](docs/05_systemd_autostart_bot.md)
* [⑥ Discord「変換」コマンドで最新音声を自動文字起こしする](docs/06_discord_convert_command_transcribe.md)

---
## 学び・工夫した点

- AWSサービス連携の理解を深めるため、設計・実装・検証を段階的に進めた
- 実装にあたっては公式ドキュメントやAIコード補助を活用しつつ、
  実際に動作確認・トラブルシュートを行いながら構成理解を深めた

