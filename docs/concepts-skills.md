# Skills（Markdown 能力包）

给 agent 加能力的**无代码**方式：往顶层 `skills/` 丢一个 `SKILL.md`，运行时按相关性选中、把正文注入 agent 的 system prompt。业务同事不用碰 Python。

## 一个 skill 长什么样
`skills/<name>/SKILL.md`（也支持 `skills/<name>.md`）：

```markdown
---
name: concise-style
description: 用户希望回答更简洁/精炼时使用
keywords: [简洁, 精炼, 短一点, concise]
---

把回答压到最短：先给结论，去掉寒暄铺垫，能一句话说清就不写两句。
```

- **frontmatter**：`name`（标识）、`description`（干嘛用的）、`keywords`（用于相关性匹配的词）。
- **正文**：注入给模型的指令本身。

## 怎么被选中（相关性）
每轮按**用户消息**对每个 skill 算相关性：命中的 `keywords` 越多越靠前，取 top-3 注入。命中 0 的不注入——所以放再多 skill 也不会每轮都撑爆上下文。

> 默认是**关键词匹配**（确定、可测、零依赖）。要更聪明的**语义选择**（让 LLM 按 description 判），在 `skills/loader.py:select_skills` 接一个 LLM 选择器即可——这是扩展点。

## 加 / 删
- **加**：在 `skills/` 下建目录放 `SKILL.md`，写好 frontmatter + 正文。完事，不用动代码。
- **删**：`rm -rf skills/<name>/`。没有 `skills/` 目录时 = 无 skill，不影响任何东西。
- 示例：`skills/example_concise/`（通用"简洁风格"，照着抄/删）。

## skill vs domain（别混）
| | skill | domain（`tasks/<d>/`） |
|---|---|---|
| 形态 | Markdown 指令，无代码 | Python：DomainSpec/TaskSpec |
| 带工具？ | 否，纯 prompt 注入 | 是（read/write 工具） |
| 加的人 | 业务同事 | 开发 |
| 选中 | 按 keywords 相关性，注入 system | 按 classify 选域，绑工具 |

一句话：**要"让 agent 多懂一种说话/处理方式" → skill；要"让 agent 能调一类新工具做事" → domain。**

## 配置
- `SKILLS_DIR`（默认 `skills`）：skill 目录位置。
- 目录不存在 → 零 skill，agent 照常跑（零依赖默认）。
