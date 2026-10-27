#!/usr/bin/env python3
"""静态校验 Dify DSL：结构、节点连通性和变量引用。

用法：
    python scripts/validate_dsl.py [app.yml]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REFERENCE = re.compile(r"\{\{#([^#{}]+)#\}\}")
ALLOWED_SYS = {"sys.query", "sys.conversation_id", "sys.user_id", "sys.files", "sys.dialogue_count"}


def references(value: object) -> set[str]:
    if isinstance(value, str):
        return set(REFERENCE.findall(value))
    if isinstance(value, dict):
        return {ref for item in value.values() for ref in references(item)}
    if isinstance(value, list):
        return {ref for item in value for ref in references(item)}
    return set()


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parents[1] / "app.yml")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    problems: list[str] = []

    app = document.get("app") or {}
    if app.get("mode") != "advanced-chat":
        problems.append("app.mode must be advanced-chat")

    graph = (document.get("workflow") or {}).get("graph") or {}
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    by_id = {node["id"]: node for node in nodes}
    if len(by_id) != len(nodes):
        problems.append("duplicate node ids")

    for edge in edges:
        for end in ("source", "target"):
            if edge.get(end) not in by_id:
                problems.append(f"edge {edge.get('id')} references unknown {end} {edge.get(end)!r}")

    reachable = {edge["target"] for edge in edges}
    for node_id in by_id:
        if node_id not in reachable and node_id != "start":
            problems.append(f"node {node_id!r} is not reachable from start")

    kinds = {node["data"]["type"] for node in nodes}
    for required in ("start", "http-request", "llm", "answer"):
        if required not in kinds:
            problems.append(f"missing node type {required!r}")

    start = next((node for node in nodes if node["data"]["type"] == "start"), None)
    start_vars = {item["variable"] for item in (start or {}).get("data", {}).get("variables", [])}
    if "player_id" not in start_vars:
        problems.append("start node must declare the player_id variable")

    for node in nodes:
        node_id = node["id"]
        data = node["data"]
        if data["type"] == "http-request":
            if data.get("method") != "post":
                problems.append(f"{node_id}: http method must be post")
            if not str(data.get("url", "")).startswith("http"):
                problems.append(f"{node_id}: http url must be absolute")
            if (data.get("body") or {}).get("type") != "json":
                problems.append(f"{node_id}: body must be json")
        for ref in references(data):
            if ref in ALLOWED_SYS:
                continue
            owner = ref.split(".")[0]
            if owner not in by_id:
                problems.append(f"{node_id}: reference {{{{#{ref}#}}}} points to unknown node {owner!r}")

    if problems:
        print("DSL problems:")
        for problem in problems:
            print(" -", problem)
        return 1
    print(f"OK: {len(nodes)} nodes, {len(edges)} edges, references resolved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
