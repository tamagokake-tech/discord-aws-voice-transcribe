## システム構成図

本システムは、Discord を起点として
EC2 上の Bot、AWS マネージドサービス（Transcribe / EventBridge / Lambda）を
役割分担させて構築している。

以下は、EC2 の起動制御から音声文字起こし・通知までの全体フローを示した構成図である。
![System Architecture](architecture_overview.png)
