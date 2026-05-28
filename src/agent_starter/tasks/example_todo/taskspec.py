from agent_starter.tasks.example_todo.prompt import DOMAIN_PROMPT
from agent_starter.tasks.example_todo.tools import add_todo
from agent_starter.tasks.registry import TaskSpec

SPEC = TaskSpec(
    task_type="create_todo",
    domain="todo",
    create_tool=add_todo,
    prompt_fragment=DOMAIN_PROMPT,
    success_message=lambda raw: f"✅ 已添加待办：{raw.get('title', '')}",
)
