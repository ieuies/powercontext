#!/usr/bin/env python3
"""酒馆老板的记性 —— 记忆服务（seekdb 后端）。

只依赖标准库 + pymysql，供 Dify Chatflow 的 HTTP Request 节点调用：

    GET  /health
    POST /memory/recall     {"player_id", "query", "limit"}
    POST /memory/remember   {"player_id", "session_id", "user_message", "assistant_reply"}

环境变量：TAVERN_DB_HOST / TAVERN_DB_PORT / TAVERN_DB_USER / TAVERN_DB_PASSWORD /
          TAVERN_DB_NAME / TAVERN_PORT
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pymysql

DB_CONFIG = {
    "host": os.environ.get("TAVERN_DB_HOST", "127.0.0.1"),
    "port": int(os.environ.get("TAVERN_DB_PORT", "2881")),
    "user": os.environ.get("TAVERN_DB_USER", "root"),
    "password": os.environ.get("TAVERN_DB_PASSWORD", ""),
    "database": os.environ.get("TAVERN_DB_NAME", "tavern"),
    "charset": "utf8mb4",
    "autocommit": True,
}

NAME_PATTERNS = (
    re.compile(r"我叫([\u4e00-\u9fa5A-Za-z0-9_]{1,12})"),
    re.compile(r"叫我([\u4e00-\u9fa5A-Za-z0-9_]{1,12})"),
    re.compile(r"我的名字(?:是|叫)([\u4e00-\u9fa5A-Za-z0-9_]{1,12})"),
)
PREFERENCE_PATTERN = re.compile(r"(喜欢|讨厌|爱吃|不爱吃|不吃|受不了|最怕|怕)([^，。！？,.!?\n]{1,24})")
MAX_MEMORY_TEXT = 200


def connect() -> pymysql.connections.Connection:
    return pymysql.connect(**DB_CONFIG)


def extract_memories(message: str) -> list[tuple[str, str]]:
    """从一句话里抽取可长期复用的记忆：姓名、偏好、以及本轮原话。"""

    found: list[tuple[str, str]] = []
    for pattern in NAME_PATTERNS:
        match = pattern.search(message)
        if match:
            found.append(("name", match.group(1)))
            break
    for match in PREFERENCE_PATTERN.finditer(message):
        found.append(("preference", f"{match.group(1)}{match.group(2)}".strip()))
    if not found:
        text = message.strip()
        if text:
            found.append(("event", text[:MAX_MEMORY_TEXT]))
    return list(dict.fromkeys(found))


def ensure_player(cursor, player_id: str) -> None:
    cursor.execute("INSERT IGNORE INTO players (player_id) VALUES (%s)", (player_id,))


def _jsonable(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value.isoformat(sep=" ") if isinstance(value, (datetime, date)) else value
        for key, value in row.items()
    }


def recall(player_id: str, query: str, limit: int) -> dict[str, Any]:
    limit = max(1, min(int(limit or 5), 20))
    with connect() as conn, conn.cursor(pymysql.cursors.DictCursor) as cursor:
        ensure_player(cursor, player_id)
        cursor.execute("SELECT name FROM players WHERE player_id = %s", (player_id,))
        row = cursor.fetchone()
        name = row["name"] if row else None

        memories: list[dict[str, Any]] = []
        terms = " ".join(re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]+", query or ""))
        if terms:
            cursor.execute(
                "SELECT kind, content, created_at FROM memories "
                "WHERE player_id = %s AND MATCH(content) AGAINST(%s) "
                "ORDER BY created_at DESC LIMIT %s",
                (player_id, terms, limit),
            )
            memories = list(cursor.fetchall())

        if not memories:
            cursor.execute(
                "SELECT kind, content, created_at FROM memories "
                "WHERE player_id = %s ORDER BY created_at DESC LIMIT %s",
                (player_id, limit),
            )
            memories = list(cursor.fetchall())

        cursor.execute(
            "SELECT user_message, assistant_reply, created_at FROM turns "
            "WHERE player_id = %s ORDER BY id DESC LIMIT 3",
            (player_id,),
        )
        recent = list(cursor.fetchall())

    if name and not any(item["kind"] == "name" for item in memories):
        memories.insert(0, {"kind": "name", "content": name, "created_at": None})
    return {
        "player_id": player_id,
        "name": name,
        "memories": [_jsonable(item) for item in memories],
        "recent": [_jsonable(item) for item in recent],
    }


def remember(player_id: str, session_id: str, user_message: str, assistant_reply: str) -> dict[str, Any]:
    facts = extract_memories(user_message)
    stored: list[dict[str, str]] = []
    with connect() as conn, conn.cursor() as cursor:
        ensure_player(cursor, player_id)
        for kind, content in facts:
            cursor.execute(
                "INSERT INTO memories (player_id, kind, content, session_id) VALUES (%s, %s, %s, %s)",
                (player_id, kind, content, session_id),
            )
            stored.append({"kind": kind, "content": content})
        if any(kind == "name" for kind, _ in facts):
            new_name = next(content for kind, content in facts if kind == "name")
            cursor.execute(
                "UPDATE players SET name = %s, updated_at = CURRENT_TIMESTAMP WHERE player_id = %s",
                (new_name, player_id),
            )
        cursor.execute(
            "INSERT INTO turns (player_id, session_id, user_message, assistant_reply) VALUES (%s, %s, %s, %s)",
            (player_id, session_id, user_message, assistant_reply),
        )
    return {"player_id": player_id, "stored": stored}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # 保持输出干净
        pass

    def _send(self, payload: dict[str, Any], code: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        if self.path == "/health":
            self._send({"status": "ok"})
        else:
            self._send({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send({"error": "invalid json"}, 400)
            return
        try:
            if self.path == "/memory/recall":
                self._send(recall(payload["player_id"], payload.get("query", ""), payload.get("limit", 5)))
            elif self.path == "/memory/remember":
                self._send(
                    remember(
                        payload["player_id"],
                        payload["session_id"],
                        payload.get("user_message", ""),
                        payload.get("assistant_reply", ""),
                    )
                )
            else:
                self._send({"error": "not found"}, 404)
        except KeyError as exc:
            self._send({"error": f"missing field {exc.args[0]}"}, 400)
        except Exception as exc:  # noqa: BLE001 - 便于评审排查
            self._send({"error": f"{type(exc).__name__}: {exc}"}, 500)


def main() -> None:
    port = int(os.environ.get("TAVERN_PORT", "8000"))
    print(f"tavern memory service on 0.0.0.0:{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
