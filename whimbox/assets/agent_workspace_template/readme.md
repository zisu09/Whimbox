# agent_workspace 说明

`agent_workspace` 是奇想盒的记忆宫殿。

用来保存奇想盒的原则、人格、用户画像、长期记忆、历史会话和可用技能。

## 目录结构

```text
agent_workspace/
├─ AGENTS.md
├─ SOUL.md
├─ USER.md
├─ TOOLS.md
├─ memory/
│  ├─ MEMORY.md
│  └─ HISTORY.md
├─ sessions/
└─ skills/
   ├─ memory/
   │  └─ SKILL.md
   └─ photo-score/
      └─ SKILL.md
```

## 文件说明

- `AGENTS.md`
  奇想盒的行为规则和工作准则。

- `SOUL.md`
  奇想盒的人格、价值观和沟通风格。

- `USER.md`
  用户画像，用户可以修改此文件，让奇想盒知道你的偏好、习惯和背景信息。

- `TOOLS.md`
  工具使用规则。适合记录具体工具的调用边界、前置条件和推荐流程。

- `memory/MEMORY.md`
  长期记忆。奇想盒自动记录的稳定、重要、需要长期保留的信息。

- `memory/HISTORY.md`
  历史事件。奇想盒自动按时间记录的对话摘要或阶段性事件。

- `sessions/`
  会话记录目录。用于保存近期的会话，重启后能够继续之前的对话。

- `skills/`
  技能目录。每个子目录表示一个独立 skill，通常包含一个 `SKILL.md` 作为说明和执行规则。

- `skills/memory/SKILL.md`
  记忆管理相关技能，当你让奇想盒记住一些东西时，会自动使用此技能。

- `skills/photo-score/SKILL.md`
  照片打分相关技能，可以让奇想盒对你上传的照片或当前游戏画面打分。

## 使用原则
- 你可以在这个目录中继续新增自己的 `skill`、修改奇想盒记忆。
- 如需清空奇想盒的记忆，可以直接删除该目录。下次启动会自动变成初始状态。

