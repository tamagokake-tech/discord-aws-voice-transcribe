# 04_slash_command_ec2_control.md

## Discord Slash Command から EC2 を起動・停止・状態確認する

（署名検証あり / Lambda Function URL）

---

## 概要

本ドキュメントでは、Discord の Slash Command（例：`/ec2`）を実行した際に、Discord から送信される **署名付きリクエスト（ed25519）**を AWS Lambda 側で検証し、検証に成功したリクエストのみを受け付けて **EC2 の起動・停止・状態確認**を行う仕組みを説明する。

この構成のポイントは以下。

* **API_KEY は不要**（Discord は自動で署名して送信する）
* Lambda は **署名検証できたリクエストのみ処理**する
* 受信口は **Lambda Function URL** を使用する

---

## ゴール（到達状態）

* Discord で `/ec2 action:start|stop|status` が実行できる
* Discord → Lambda Function URL に署名付きリクエストが送られる
* Discord に実行結果がメッセージとして返る

---

## 全体像（本章で扱う構成）

```
Discord (/ec2 コマンド)
   ↓（Discordが署名付きリクエスト送信）
Lambda Function URL
   ├─ 署名検証（PyNaCl / ed25519）
   ├─ PING → PONG 応答（Verify用）
   └─ /ec2 action に応じて EC2 API 呼び出し
        ├─ start
        ├─ stop
        └─ status（DescribeInstances）
```

---

## 前提条件

* 操作対象の EC2 インスタンスが存在する（インスタンスIDが確定している）
* Lambda / EC2 は同じリージョンに存在する（推奨）
* Discord Developer Portal にログインできる

---

## 1. Lambda（Slash Command 受信用）の作成

### 1.1 Lambda 関数を作成

* サービス：AWS Lambda
* 関数名：`discord-instance`
* ランタイム：Python 3.12
* アーキテクチャ：x86_64

---

### 1.2 PyNaCl レイヤーを追加（署名検証）

Discord の署名（ed25519）を検証するために `PyNaCl` を使用する。
ただし Lambda の標準環境には含まれないため、**Lambda Layer として追加する**。

#### （AWSコンソール側の設定）

1. Lambda → レイヤー → レイヤーを作成

   * 名前：`discord-sig-layer`
   * 互換性のあるアーキテクチャ：x86_64
   * 互換性のあるランタイム：Python 3.12

2. Lambda 関数 `discord-instance` → レイヤー → 「レイヤーの追加」

   * カスタムレイヤー：`discord-sig-layer`

---

### 1.3 IAM 権限を追加（EC2 操作用）

Lambda 実行ロールに以下の権限を追加する（インラインポリシー）。

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:StartInstances",
        "ec2:StopInstances",
        "ec2:DescribeInstances"
      ],
      "Resource": "*"
    }
  ]
}
```

※ 学習用途のため `Resource: "*"`

---

### 1.4 環境変数を設定

Lambda → 設定 → 環境変数

| 変数名                | 内容                            |
| ------------------ | ----------------------------- |
| DISCORD_PUBLIC_KEY | Discord アプリの Public Key（後で取得） |


---

### 1.5 Function URL を作成

Lambda → 設定 → Function URL → 作成

* 認証タイプ：**NONE**（Discord から直接呼ばれるため）
* CORS：不要（Discord からのサーバー間通信のため）

作成後に表示される URL を控える（後で Discord 側に貼る）。

---

## 2. Lambda コード（署名検証 + /ec2 処理）

コメントなし配置場所：`src/lambda/discord_slash_ec2/lambda_function.py`

```python
# ========================
# 必要なライブラリの読み込み
# ========================

import os
# 環境変数（DISCORD_PUBLIC_KEY など）を読む用

import json
# Discord / Lambda の JSON データを扱う用

import base64
# Function URL 経由の body が base64 の場合にデコードする用

import boto3
# AWS API（今回は EC2）を操作する用

from nacl.signing import VerifyKey
# Discord の署名を確認する用

from nacl.exceptions import BadSignatureError
# 署名が一致しなかった時用のエラー

from nacl.encoding import HexEncoder
# Discordの公開鍵は hex 形式なので、その変換用


# ========================
# EC2 関連の初期設定
# ========================

INSTANCE_ID = "xxxxxx"
# 操作対象の EC2 インスタンス ID（固定）

ec2 = boto3.client("ec2", region_name="us-west-2")
# EC2 を操作するための AWS クライアント


# ========================
# Discord の署名検証関数
# ========================

def verify(pubkey, headers, raw_body):
    # Discord が送ってくる署名をヘッダーから取得
    sig = headers.get("x-signature-ed25519")

    # リクエスト送信時刻（署名計算に含まれる）
    ts = headers.get("x-signature-timestamp")

    # どちらか無ければ Discord からの正規リクエストではない
    if not sig or not ts:
        return False

    # Discord の公開鍵を使って検証用装置を作成
    vk = VerifyKey(pubkey, encoder=HexEncoder)

    try:
        # Discord の仕様timestamp + bodyで正しい物か検証
        vk.verify((ts + raw_body).encode(), bytes.fromhex(sig))
        return True
    except BadSignatureError:
        # 署名が合わなければ改ざん or 偽リクエスト
        return False


# ========================
# Lambda のエントリーポイント
# ========================

def lambda_handler(event, context):

    # 環境変数から Discord の公開鍵を取得
    pubkey = os.environ.get("DISCORD_PUBLIC_KEY")

    # 公開鍵が設定されていなければ即エラー
    if not pubkey:
        return {"statusCode": 500, "body": "missing public key"}

    # HTTP ヘッダーをすべて小文字に変換（エラー防止）
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}

    # リクエストボディを取得
    raw_body = event.get("body") or ""

    # Function URL 経由の場合、base64 で来ることがある
    if event.get("isBase64Encoded"):
        raw_body = base64.b64decode(raw_body).decode("utf-8")

    # ========================
    # ① Discord 署名検証
    # ========================

    # Discord 本人から来たリクエストかをチェック
    if not verify(pubkey, headers, raw_body):
        return {"statusCode": 401, "body": "invalid signature"}

    # JSON文字列 → Python dict に変換
    body = json.loads(raw_body)

    # ========================
    # ② Discord の PING 処理
    # ========================

    # type=1 はエンドポイントがあるか確認
    if body.get("type") == 1:
        # Discord 仕様：同じ {"type":1} を返すと OK
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"type": 1}),
        }

    # ========================
    # ③ Slash Command (/ec2) の処理
    # ========================

    # type=2 はSlash Command が実行された
    if body.get("type") == 2:

        # /ec2 action:xxx の options を取得
        options = body["data"].get("options", [])

        # action の値（start / stop / status）
        action = options[0]["value"] if options else None

        # ---------- EC2 起動 ----------
        if action == "start":
            ec2.start_instances(InstanceIds=[INSTANCE_ID])
            content = "EC2 を起動しました"

        # ---------- EC2 停止 ----------
        elif action == "stop":
            ec2.stop_instances(InstanceIds=[INSTANCE_ID])
            content = "EC2 を停止しました"

        # ---------- EC2 状態確認 ----------
        elif action == "status":
            res = ec2.describe_instances(InstanceIds=[INSTANCE_ID])
            inst = res["Reservations"][0]["Instances"][0]
            state = inst["State"]["Name"]
            content = f"現在の状態: {state}"

        # ---------- 不正な action ----------
        else:
            content = "不明な action です"

        # Discord に「コマンド結果」を返す
        # type=4 は「チャンネルにメッセージ表示」
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "type": 4,
                "data": {"content": content}
            }),
        }

    # 想定外の入力ても壊れない用
    return {"statusCode": 200, "body": "ok"}


```

---

## 3. Discord Developer Portal 側の設定

### 3.1 Discord アプリを作成

[https://discord.com/developers/applications](https://discord.com/developers/applications)

1. 「New Application」を選択
2. 名前例：`EC2_Control_Bot`
3. 「Bot」→「Add Bot」

---
### 3.2 Bot Token の取得

1. Discord Developer Portal → Bot
2. 「Reset Token」を選択
3. 表示されたトークンを控える

⚠ トークンは外部に漏らさないこと
---
### 3.3 Bot 権限設定

**Privileged Gateway Intents**
- MESSAGE CONTENT INTENT：有効

**Bot Permissions**
- Send Messages
- Read Message History
---
### 3.4 Bot をサーバーに招待

1. OAuth2 → URL Generator
2. Scopes：`bot`
3. Permissions：
   - Send Messages
   - Read Message History
4. 生成された URL から対象サーバーに招待する
---

### 3.5 Public Key を取得 → Lambda に設定

Discord Developer Portal 左メニュー：
**General Information → Public Key** をコピー

Lambda → `discord-instance` → 設定 → 環境変数へ設定

* `DISCORD_PUBLIC_KEY=<Public Key>`

---

### 3.6 Interactions Endpoint URL を設定（Verify）

Discord Developer Portal 左メニュー：
**General Information → Interactions Endpoint URL** に以下を設定する。

* `Lambda Function URL` を貼り付け → Save Changes

Discord が PING を送信し、Lambda が正しく PONG（type=1）を返すと
画面上で **Verified** となる。

---

## 4. /ec2 コマンドの登録（guild command）

### 4.1 GUILD_ID の取得

Discord → ユーザー設定（歯車）→ 詳細設定 → 開発者モード ON
対象サーバーを右クリック → サーバーIDをコピー

---

### 4.2 register_command.py の作成

コメントなし配置場所：`scripts/register_command.py`
※ 本章では理解しやすさのためコメント付きで掲載する。
GitHub 上のコードはコメントを最小限に整理して配置する。
```python
import requests
import json

##Discord アプリ情報
APPLICATION_ID = "xxxxx"
GUILD_ID = "xxxxx"
BOT_TOKEN = "xxxxx（bot作成時に控えたtokenを貼る）"

url = f"https://discord.com/api/v10/applications/{APPLICATION_ID}/guilds/{GUILD_ID}/commands"

# 今回は /ec2 の１コマンドだけ作る
command = {
    "name": "ec2",                # /ec2 というコマンド名
    "description": "EC2 を操作します",
    "options": [
        {
            "name": "action",
            "description": "start / stop / status を指定",
            "type": 3,           # STRING
            "required": True,
            "choices": [
                {"name": "起動", "value": "start"},
                {"name": "停止", "value": "stop"},
                {"name": "状態確認", "value": "status"},
            ],
        }
    ],
}

#証明ヘッダー
headers = {
    "Authorization": f"Bot {BOT_TOKEN}",
    "Content-Type": "application/json",
}

# POST リクエストを送信
resp = requests.post(url, headers=headers, data=json.dumps(command))
#レスポンスを確認
print(resp.status_code)
print(resp.text)
```

---

### 4.3 実行

```bash
python3 -m venv venv
source venv/bin/activate
pip install requests

python scripts/register_command.py
```

成功時の例：

* HTTP Status: `201`
* コマンド JSON が返る

---

## 5. 動作確認

Discord で `/` を入力し、`/ec2` が候補に出ることを確認する。

* `/ec2 action:start`
* `/ec2 action:stop`
* `/ec2 action:status`

期待結果：

* action の結果が Discord に返信される
* EC2 の状態が実際に変化する（AWS コンソール上でも確認できる）

---

👉 次章：`05_systemd_autostart_bot.md`

---
