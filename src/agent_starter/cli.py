"""命令行模式 —— 直接在终端里问问题，无需启动 HTTP 服务。"""
from __future__ import annotations

import asyncio
import argparse

from agent_starter.graph import build_graph
from agent_starter.settings import get_settings
from agent_starter.tasks import register_enabled_domains
from langchain_core.messages import HumanMessage


async def run_query(question: str, thread_id: str = "cli", user_id: int = 0) -> str:
    register_enabled_domains()
    graph = build_graph()

    inputs = {
        "messages": [HumanMessage(content=question)],
        "user_id": user_id,
        "jwt": "",
        "domain": "",
        "permissions": None,
        "user_scope": None,
        "workspace_id": get_settings().agent_workspace_id,
        "page_context": None,
    }
    config = {"configurable": {"thread_id": thread_id}}

    print("⏳ 拆解 + 检索 + 综合中...\n")
    out = await graph.ainvoke(inputs, config)
    last = out["messages"][-1]
    return getattr(last, "content", str(last))


def main():
    parser = argparse.ArgumentParser(
        prog="decompose",
        description="拆解-并行检索-综合 Agent —— 直接在命令行问分析问题",
    )
    parser.add_argument(
        "question",
        nargs="?",
        help="要分析的问题（不传则进入交互模式）",
    )
    parser.add_argument(
        "--thread-id", default="cli", help="会话 ID（默认 cli）"
    )
    parser.add_argument(
        "--user-id", type=int, default=0, help="用户 ID（默认 0）"
    )

    args = parser.parse_args()

    if args.question:
        reply = asyncio.run(run_query(args.question, args.thread_id, args.user_id))
        print(reply)
    else:
        # 交互模式
        print("拆解-并行检索-综合 Agent（输入 quit 退出）\n")
        thread_id = args.thread_id
        while True:
            try:
                q = input(">>> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nbye")
                break
            if q.lower() in ("quit", "exit", "q"):
                break
            if not q:
                continue
            reply = asyncio.run(run_query(q, thread_id, args.user_id))
            print(f"\n{reply}\n")


if __name__ == "__main__":
    main()
