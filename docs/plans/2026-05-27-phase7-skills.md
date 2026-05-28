# Phase 7：skills（Markdown 指令包，按相关性注入）

> 内联执行。

**Goal:** 给模板加一个统一的 `skills/` 目录，业务同事**不写代码**、丢一个 `SKILL.md`（frontmatter + 指令正文）就能加 agent 能力；运行时按相关性（keywords/description 匹配用户消息）选中若干，把正文注入 agent system prompt。

**Architecture:** 顶层 `skills/<name>/SKILL.md`（也支持 `skills/<name>.md`）。`skills/loader.py` 解析 frontmatter + 正文 → `Skill`；进程级 lazy 缓存；`select_skills(query, skills)` 关键词相关性选 top-k；`render_skills_section` 拼进 system。在 `agent._build_system` 注入（不加图节点，技能=prompt 增强）。无 `skills/` 目录 → 空 → 不注入（零依赖默认）。

**验证：** 全部零依赖可测（tmp_path 造 SKILL.md + set_skills 注入）。**LLM 语义选 skill** = 文档化扩展点（默认走 keywords 关键词匹配，确定可测）。

---

## Task 1：skills loader + settings

**Files:** `src/agent_starter/skills/__init__.py`(空), `skills/loader.py`; `settings.py`(加 `skills_dir`); Test `tests/test_skills.py`

- `Skill{name, description, body, keywords:list}`。
- `_parse_frontmatter(text)->(meta:dict, body)`：`---` 分隔，frontmatter 按 `key: value` 行解析；`keywords` 解析 `[a, b]` 或 `a, b`。
- `parse_skill(text, fallback_name)->Skill|None`（无正文返 None）。
- `load_skills(dir)->list[Skill]`：扫 `<dir>/*/SKILL.md` + `<dir>/*.md`；目录不存在→[]。fallback_name=目录名/文件 stem。
- `get_skills()`（lazy 读 `settings.skills_dir`，缓存，settings 取不到 fail-soft 用 "skills"）/ `set_skills(list)` / `reset_skills()`。
- `select_skills(query, skills, top_k=3)`：每个 skill 算分 = query 命中的 keyword 数（命中 0 时回退 name 是否出现在 query）；>0 的按分降序取 top-k。
- `render_skills_section(selected)->str`：`【可用技能（按相关性选中，请遵循）】` + 各 `## name\n body`。
- `settings.skills_dir: str = "skills"`。
- 测试：tmp_path 造 SKILL.md → load 出 name/desc/keywords/body；无目录→[]；select 关键词命中/不命中；render 含正文。

## Task 2：agent 注入 + 测试隔离

**Files:** `nodes/agent.py`(`_build_system` 注入)；`tests/conftest.py`(autouse `set_skills([])` 让单测不依赖磁盘)

- `_build_system`：基线 + base + **memory** 之后、域 prompt 之前，插 `render_skills_section(select_skills(last_user_text, get_skills()))`。
- conftest autouse 追加 `set_skills([])`（前）/`reset_skills()`（后）。
- 测试（test_skills.py 追加）：`set_skills([Skill(name=..,keywords=["简洁"],body="要简洁")])` + agent_loop（query 含"简洁"）→ system 含 "要简洁"；query 不含 → 不注入。

## Task 3：示例 skill

**Files:** `skills/example_concise/SKILL.md`

通用"简洁风格"skill（非业务），演示格式。顶层 `skills/`，业务同事照这个加；删 = rm 目录。

## Task 4：文档

- `docs/concepts-skills.md`：什么是 skill、SKILL.md 格式、怎么加/删、相关性选中机制（keywords 为主，LLM 语义选=扩展）、与 domain 的区别（skill=纯指令注入、无代码无工具；domain=工具+任务，要写代码）。
- README：结构树加 `skills/`（顶层）；状态表加“skills（Markdown 能力包）✅”；doc 索引加 concepts-skills。
- architecture：模块表加 `skills/loader.py` ✅ + 数据流 agent 那步补“注入选中 skill”。

## 验收
- AC-SK1 load/select/render（test_skills 单测）。
- AC-SK2 选中 skill 注入 agent system（agent 注入测试）。
- AC-SK3 无 skills/ 目录零依赖照跑（既有 57 测试 + 启动不破）。
- AC4 保持：`src/agent_starter/skills/` 无业务名（示例 skill 在顶层 skills/，不算 src core）。

## Self-Review
- 与 domain 区分清楚：skill=无代码 markdown 指令、相关性注入；domain=代码+工具+任务。
- 零依赖：无目录→空；autouse set_skills([]) 让既有测试不受磁盘示例 skill 影响。
- 类型一致：`Skill`、`load_skills(dir)`、`get/set/reset_skills`、`select_skills(query,skills,top_k=3)`、`render_skills_section(selected)`。
