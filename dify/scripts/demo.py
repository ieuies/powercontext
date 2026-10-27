#!/usr/bin/env python3
"""端到端验证：模拟 Dify Chatflow 两次会话对记忆服务的调用。

用法（先启动 service/main.py）：
    python scripts/demo.py --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import urllib.request


def call(base_url: str, path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--player", default="player-001")
    args = parser.parse_args()

    session_a = "session-a"
    print("== 第一晚 ==")
    first = call(
        args.base_url,
        "/memory/remember",
        {
            "player_id": args.player,
            "session_id": session_a,
            "user_message": "老板，我叫阿澈，我喜欢桂花酒，讨厌吵闹的客人。",
            "assistant_reply": "阿澈啊，桂花酒给你留着，靠窗的位置安静。",
        },
    )
    print(json.dumps(first, ensure_ascii=False, indent=2))

    second = call(
        args.base_url,
        "/memory/remember",
        {
            "player_id": args.player,
            "session_id": session_a,
            "user_message": "我最近在找一个叫‘青铜钥匙’的东西。",
            "assistant_reply": "青铜钥匙？地窖里倒是有把旧的。",
        },
    )
    print(json.dumps(second, ensure_ascii=False, indent=2))

    print("\n== 第二晚（新会话）==")
    recalled = call(
        args.base_url,
        "/memory/recall",
        {"player_id": args.player, "query": "桂花酒 安静 青铜钥匙", "limit": 5},
    )
    print(json.dumps(recalled, ensure_ascii=False, indent=2))

    assert recalled["name"] == "阿澈", "老板应该记得玩家名字"
    contents = [item["content"] for item in recalled["memories"]]
    assert any("桂花酒" in item for item in contents), "老板应该记得偏好"
    assert any("青铜钥匙" in item for item in contents), "老板应该记得事件"
    print("\nOK: 跨会话记忆命中 name / preference / event")


if __name__ == "__main__":
    main()
