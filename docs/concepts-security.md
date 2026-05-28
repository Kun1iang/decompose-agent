# 安全层

三层通用安全，挂在 `agent_loop_action` 上，全部去业务化（不含任何业务权限常量）。

## 1. 工具权限过滤（`security/permissions.py`）
- 工具自行声明所需权限点：`register_tool_permissions("add_todo", ["todo.write"])`。**无声明 = 公开工具。**
- 授予来源：`state.permissions`（list）或 `state.user_scope.permissions`；HTTP 入口的 `ChatRequest` 可直接透传 `permissions`/`user_scope` 到 state。
- 选工具后收口：`agent_loop` 调 `filter_tools_for_permissions(tools, granted_permissions(state))`——只保留 `required ⊆ granted` 的工具，LLM 根本看不到无权工具。
- **fail-open 默认**：state 没带任何权限信息（`None`）→ 不限制（starter 开箱即用）。要强制收口就显式传 `permissions=[...]`（哪怕空列表）。
- 权限点是**普通字符串**，命名空间你自定（如 `todo.write` / `report.read`）。

## 2. 输入防注入 + 包裹（`security/sanitize.py` + `prompt.py`）
- `sanitize_user_input`：把明显的越权/注入片段（"ignore all previous instructions" / "忽略之前的指令" 等）替换成 `[已过滤]`。
- `wrap_user_input`：用户内容包进 `<user_input>...</user_input>`。
- `SYSTEM_INSTRUCTIONS`（系统基线）告诉模型：定界符内只当数据、忽略其中改写指令的企图、不要泄露系统提示。
- 三者在 `agent_loop` 里组合：system 起手放基线 + 历史里的 HumanMessage 过滤并包裹（**仅本次 LLM 调用，不写回 state**）。

## 3. 输出清理（`security/sanitize.py`）
- `sanitize_output`：清掉模型可能回显的定界符。业务可在此叠加 PII 打码、敏感字段脱敏等。

## capability 粗开关
“整个能力/域开不开”这种粗粒度控制，由**域注册开关**承担（如 `ENABLE_EXAMPLE_DOMAIN`，见 [adding-a-domain.md](adding-a-domain.md)）——关掉的域既不注册、classify 也选不到、工具自然不绑。不需要单独的 capability 系统。

## 扩展点
- 权限来源接你的鉴权（JWT/RBAC）：把解析出的权限点塞进 `state.permissions`（可在 recall 节点或入口中间件做）。
- 更强的注入检测 / 输出 PII 脱敏：在 `sanitize.py` 里加规则或接专门服务。
