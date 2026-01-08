import requests
import json

APPLICATION_ID = "xxxxx"
GUILD_ID = "xxxxx"
BOT_TOKEN = "xxxxx"

url = f"https://discord.com/api/v10/applications/{APPLICATION_ID}/guilds/{GUILD_ID}/commands"

command = {
    "name": "ec2",
    "description": "EC2 を操作します",
    "options": [
        {
            "name": "action",
            "description": "start / stop / status を指定",
            "type": 3,  # STRING
            "required": True,
            "choices": [
                {"name": "起動", "value": "start"},
                {"name": "停止", "value": "stop"},
                {"name": "状態確認", "value": "status"},
            ],
        }
    ],
}

headers = {
    "Authorization": f"Bot {BOT_TOKEN}",
    "Content-Type": "application/json",
}

resp = requests.post(url, headers=headers, data=json.dumps(command))
print(resp.status_code)
print(resp.text)