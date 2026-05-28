"""example_todo 的本地内存工具。纯演示，不连任何外部存储。

删除整个 example_todo 目录即删掉本域所有痕迹（delete-clean）。
"""
from __future__ import annotations

from langchain_core.tools import tool

# 进程内内存：{user_id: [ {id,title,done}, ... ]}
_STORE: dict[int, list[dict]] = {}
_SEQ = [0]  # 自增 id


@tool
async def add_todo(user_id: int, title: str) -> dict:
    """新增一条待办。入参：user_id, title。"""
    _SEQ[0] += 1
    item = {"id": _SEQ[0], "title": title, "done": False}
    _STORE.setdefault(user_id, []).append(item)
    return {"ok": True, "id": item["id"], "title": title}


@tool
async def list_todos(user_id: int) -> dict:
    """列出某用户的全部待办。入参：user_id。"""
    return {"items": list(_STORE.get(user_id, []))}


@tool
async def complete_todo(user_id: int, todo_id: int) -> dict:
    """把某条待办标记完成。入参：user_id, todo_id。"""
    for item in _STORE.get(user_id, []):
        if item["id"] == todo_id:
            item["done"] = True
            return {"ok": True, "id": todo_id}
    return {"ok": False, "error": "not_found"}
