import json
import urllib.error
import urllib.request

payload = {"player_id": "player-001", "query": "桂花酒 安静 青铜钥匙", "limit": 5}
request = urllib.request.Request(
    "http://127.0.0.1:8080/memory/recall",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(request, timeout=10) as response:
        print(response.read().decode())
except urllib.error.HTTPError as exc:
    print(exc.code, exc.read().decode())
