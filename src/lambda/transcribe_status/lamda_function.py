def lambda_handler(event, context):
    # EventBridge から渡されたイベント内容を確認するための簡易ハンドラ

    print("Event received")
    print(event)

    job_name = event["detail"]["TranscriptionJobName"]
    status = event["detail"]["TranscriptionJobStatus"]

    print("Job Name:", job_name)
    print("Status:", status)

    return {
        "job_name": job_name,
        "status": status
    }
