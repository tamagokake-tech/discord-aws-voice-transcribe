# 02_transcribe_eventbridge_lambda.md

## 文字起こし完了イベント検知

（Amazon Transcribe → EventBridge → Lambda）

---

## 概要

本ドキュメントでは、**Amazon Transcribe の文字起こし完了イベント（COMPLETED）を EventBridge で検知し、Lambda を自動実行する構成**について説明する。

本章の目的は以下の確認に限定する。

* Transcribe ジョブの状態変化イベントを EventBridge が受信できること
* EventBridge から Lambda が自動実行されること

※
**文字起こし結果の加工・通知（Discord 連携など）は本章では扱わない**

---

## ゴール（到達状態）

* S3 上の音声ファイルを Amazon Transcribe で文字起こしできる
* Transcribe ジョブの完了イベント（COMPLETED）を EventBridge が検知する
* EventBridge により Lambda が自動実行される

---

## 全体構成（本章で扱う範囲）

```
Amazon S3（音声ファイル）
   ↓
Amazon Transcribe（文字起こし）
   ↓
EventBridge（ジョブ状態変化イベント）
   ↓
AWS Lambda（ログ出力）
```

※ EventBridge は **Transcribe のジョブ状態変化イベントのみ**を受信する

---

## 1. Amazon Transcribe の準備

※ 注意
新規 AWS アカウントでは、**Amazon Transcribe の利用が制限されている場合がある**。
事前にコンソールから実行可能であることを確認する。

---

### 1.1 音声ファイルの準備

Discord Bot から S3 に保存された音声ファイルを使用する。

例：

```
s3://user-transcribe-audio/discord-audio/sample.m4a
```

---

### 1.2 Transcribe ジョブ作成（手動）

AWS マネジメントコンソールより以下を設定する。

#### 基本設定

* ジョブ名：`lambda_test_transcribe_bot`
* 言語：日本語
* 音声形式：自動判定

#### 入力

* S3 URI

  ```
  s3://user-transcribe-audio/discord-audio/sample.m4a
  ```

#### 出力

* 出力先を指定

  ```
  s3://user-transcribe-audio/transcribe-output/
  ```

※ その他のオプション設定は行わない

---

### 1.3 動作確認

* ジョブ実行後、文字起こしが正常に完了すること
* `transcribe-output/` 配下に JSON ファイルが出力されること

---

## 2. Lambda 関数の作成（イベント受信確認用）

### 2.1 Lambda 作成

* サービス：AWS Lambda
* 関数名：`transcribe-complete-handler`
* ランタイム：Python 3.x
* リージョン：`us-west-2`

※
**EventBridge / Transcribe / Lambda は同一リージョンで構成すること**

---

### 2.2 IAM ロール（最小構成）

Lambda 実行ロールに以下を付与する。

* `AWSLambdaBasicExecutionRole`

※
本章では以下を行わないため、追加権限は不要。

* S3 へのアクセス
* Transcribe API の操作

---

### 2.3 Lambda コード（ログ確認用）
コメントなし配置場所:src/lambda/transcribe_status/lambda_function.py
※ 本章では理解しやすさのためコメント付きで掲載する。
GitHub 上のコードはコメントを最小限に整理して配置する。
```python
def lambda_handler(event, context):
    # Lambda が EventBridge などから呼び出されたときに最初に実行される関数
    # event   : EventBridge から渡されるイベントデータ（JSON）
    # context : 実行環境やリクエスト情報（今回は未使用）

    print("Event received")
    # Lambda が起動されたことをログに出力（動作確認用）

    print(event)
    # EventBridge から渡されたイベント全体をそのまま CloudWatch Logs に出力。どんなデータ構造が届いているかを確認するため

    job_name = event["detail"]["TranscriptionJobName"]
    # Event の detail 部分から、Transcribe のジョブ名（例: lambda_test_transcribe_bot）を取得

    status = event["detail"]["TranscriptionJobStatus"]
    # 同じく detail 部分から、Transcribe ジョブの状態（COMPLETED / FAILED / IN_PROGRESS）を取得

    print("Job Name:", job_name)
    # 取得したジョブ名をログに出力（確認用）

    print("Status:", status)
    # 取得したステータスをログに出力（確認用）

    return {
        "job_name": job_name,
        "status": status
    }

```

※ 本コードはログ確認目的のみ

---

## 3. EventBridge ルール作成

### 3.1 ルール作成

* EventBridge → ルール → 作成
* ルールタイプ：イベントパターン

---

### 3.2 イベントパターン設定

* サービス：AWS サービス
* サービス名：Amazon Transcribe
* イベントタイプ：Transcribe Job State Change

#### イベントパターン（確認用）

```json
{
  "source": ["aws.transcribe"],
  "detail-type": ["Transcribe Job State Change"]
}
```

---

### 3.3 ターゲット設定

* ターゲット：Lambda
* 関数：`transcribe-complete-handler`

---

### 3.4 権限設定

* EventBridge から Lambda を実行する権限は **自動付与される**
* 追加設定は不要

---

## 4. 動作確認

### 4.1 Transcribe 実行時の挙動

* ジョブ開始時：`IN_PROGRESS`
* 処理完了時：`COMPLETED`

---

### 4.2 EventBridge 発火内容（例）

```json
{
  "detail": {
    "TranscriptionJobName": "lambda_test_transcribe_bot",
    "TranscriptionJobStatus": "COMPLETED"
  }
}
```

---

### 4.3 Lambda 実行ログ確認

CloudWatch Logs に以下が出力される。

```
Event received
Job Name: lambda_test_transcribe_bot
Status: COMPLETED
```

---

## 5. 本構成で保証されること

* S3 に既存の JSON ファイルが存在していても影響しない
* EventBridge は **Transcribe ジョブの状態変化のみ**を検知する
* `COMPLETED` が発生した瞬間にのみ Lambda が実行される
* 過去のジョブやファイルを再処理することはない

---

👉 次章：`03_lambda_send_to_discord.md`

---