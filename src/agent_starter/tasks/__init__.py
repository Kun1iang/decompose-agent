"""业务域 / 任务注册包。

加一个域：在本包下建 <domain>/ 目录（含 register()），并在 register_enabled_domains
里加一行调用。删一个域：删目录 + 删那一行。core 不 import 任何域符号。
"""


def register_enabled_domains(enable_example: bool | None = None) -> None:
    """按开关注册内置域。生产由 main.py 启动时调用一次。

    enable_example=None 时读 settings.enable_example_domain。
    """
    if enable_example is None:
        from agent_starter.settings import get_settings
        enable_example = get_settings().enable_example_domain

    # ↓↓↓ 删除 example_todo 域：删掉下面这一段 + 删 example_todo/ 目录 ↓↓↓
    if enable_example:
        from agent_starter.tasks import example_todo
        example_todo.register()
    # ↑↑↑ ↑↑↑

    # scaffold:domains
