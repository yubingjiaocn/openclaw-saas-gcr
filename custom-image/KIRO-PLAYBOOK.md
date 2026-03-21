# KIRO-PLAYBOOK.md — Kiro 调用手册

> 所有 Kiro 调用必须遵循此手册。核心原则：**每次调用都必须通过看门狗 subagent 执行，保证结果返回并通知用户。**

## 基础设施

| 命令 | 用途 |
|------|------|
| `acpx kiro sessions new --name <name>` | 创建命名 session |
| `acpx kiro -s <name> "<prompt>"` | 发送 prompt（同步阻塞，返回=完成） |
| `acpx kiro sessions close <name>` | 关闭 session 释放资源 |
| `acpx kiro sessions list` | 查看所有 session |

## 调用模式

- 单个任务 → **看门狗模式**
- 多个有依赖的任务 → **Pipeline 编排器模式**
- **没有"直接调用"模式。所有调用都走看门狗/编排器。**

## 看门狗模式（默认）

**适用**：所有单个 Kiro 任务，无论大小。

1. **主 session** 创建 Kiro session：`acpx kiro sessions new --name <name>`
2. **主 session** 启动看门狗：

```
sessions_spawn(
    mode="run",
    runTimeoutSeconds=7200,
    task="""你是一个 Kiro 任务看门狗。严格按步骤执行：

步骤 1：用 exec 工具执行以下命令（timeout=7200）：
acpx kiro -s {session_name} "{task_prompt}"

步骤 2：命令完成后，检查产出文件是否存在。

步骤 3：用 message 工具通知用户（通过当前配置的通讯渠道）。

步骤 4：返回执行结果摘要。"""
)
```

3. **主 session** 收到 completion event 后，关闭 session：`acpx kiro sessions close <name>`

## Pipeline 编排器模式

**适用**：2+ 个有依赖关系的顺序任务。编排器自己创建和关闭 session。

```
sessions_spawn(
    mode="run",
    runTimeoutSeconds=7200,
    task="""你是一个 Pipeline 编排器。
    1. exec: acpx kiro sessions new --name pipeline-<project>
    2. exec: acpx kiro -s pipeline-<project> "Task A"  ← 阻塞等完成
    3. 检查 Task A 产出
    4. exec: acpx kiro -s pipeline-<project> "Task B"  ← 阻塞等完成
    5. 检查 Task B 产出
    6. exec: acpx kiro sessions close pipeline-<project>
    7. 通知用户
    8. 返回摘要"""
)
```

## 硬性约束

- **一个 Kiro session 同时只能有一个看门狗**（多个会死锁）
- `runTimeoutSeconds=7200`，exec `timeout=7200`
- 看门狗模式：session 创建和关闭在**主 session** 做
- Pipeline 模式：session 创建和关闭在**编排器内**做

## Session 命名

| 场景 | 格式 | 示例 |
|------|------|------|
| 单组件 | `<project>-<component>` | `myapp-auth` |
| Pipeline | `pipeline-<project>` | `pipeline-myapp` |
| 临时 | `quick-test` / `debug-xxx` | `quick-test` |

## 故障排查

- **Kiro 卡住**：`acpx kiro sessions close <name>`，不行就 `pkill -f "kiro-cli"`
- **看门狗超时**：`subagents(action="kill", target="all")`
- **死锁**（多进程抢同一 session）：kill subagents → pkill kiro-cli → close session → 重建
