from agent_starter.tasks.domains import DomainSpec
from agent_starter.tasks.example_todo.tools import add_todo, complete_todo, list_todos

SPEC = DomainSpec(
    name="todo",
    label="待办（任务清单）",
    triggers=["待办", "todo", "任务", "提醒我", "清单"],
    read_tools=[list_todos],
    write_tools=[add_todo, complete_todo],
)
