# Discord×AWS　音声文字起こし Bot

Discordに投稿された音声をAWSに送信・保存を行い、
任意のタイミングで、文字起こしを実行・結果をDiscordに返すプログラムです

---

## 何ができるのか

- Discord に音声を投稿すると S3 に自動保存
- Discord の「変換」コマンドで文字起こしを開始
- Amazon Transcribe の完了イベントを EventBridge で検知
- Lambda 経由で文字起こし結果を Discord に通知
- Slash Command で EC2 の起動 / 停止 / 状態確認が可能

---

## 全体構成
Discord
├─ 音声投稿
└─ Slash Command
↓
EC2 (Discord Bot)
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

---

## 使用技術

- Discord Bot / Slash Command
- AWS EC2 / S3 / Lambda / EventBridge
- Amazon Transcribe
- Python / boto3 / discord.py
- systemd（EC2 起動時の自動起動）

---

## 📚 ドキュメント

- [① 全体概要](docs/01_overview.md)
- [② Discord Bot（音声保存）](docs/02_discord_bot.md)
- [③ Transcribe 完了イベント検知](docs/03_transcribe_flow.md)
- [④ Slash Command で EC2 操作](docs/04_slash_command.md)
- [⑤ systemd による自動起動](docs/05_systemd.md)
- [⑥ 「変換」コマンドで文字起こし](docs/06_convert_command.md)

---
## 学び・工夫した点

- EventBridgeを使い完了イベントを確実に検知
- BotとLambdaの役割分担（制御 / 通知）
- Transcribe を人の意思で起動し、利便性・コスト制御を可能に

---
