# VERSIONS.md - 分支版本管理 & 镜像追溯

> 记录各分支的版本状态、镜像版本关系，方便追溯和同步。

## 当前版本状态

| 分支 | 最新 commit | platform 版本 | k8s_client 状态 | 待同步 |
|------|------------|---------------|----------------|--------|
| **main** | `ab13810` refactor: remove custom image coupling | - | ✅ 已清理 effective_image 逻辑 | - |
| **cn** | `5771ecc` fix: only inject acpx/acp/gateway config when using custom image | - | ⚠️ 旧逻辑，待同步 main 改动 | cherry-pick main ab13810 + 加 .acpxrc.json |
| **cn-workshop** | `f1c4d30` fix: increase Node.js heap to 3072MB | v0.9.23-workshop | ⚠️ 旧逻辑，待同步 cn | 等 cn 更新后同步 |

## 镜像版本矩阵

### Agent 镜像

| 镜像 | Tag | 用途 | 分支 | 状态 |
|------|-----|------|------|------|
| `ghcr.io/openclaw/openclaw` | `latest` (2026.4.11) | main 默认 agent 镜像 | main | ✅ 使用中 |
| `public.ecr.aws/i4x4j7g8/openclaw-saas/openclaw-custom` | `2026.3.22` | cn 定制镜像 (kiro+acpx) | cn | ⚠️ 待更新为新 Dockerfile |
| `public.ecr.aws/i4x4j7g8/openclaw-saas/openclaw-custom` | `latest` | cn 定制镜像 alias | cn | ⚠️ 同上 |
| `public.ecr.aws/i4x4j7g8/openclaw-saas/openclaw` | `2026.3.13-1` | cn-workshop 预拉取 | cn-workshop | ⚠️ 待更新 |
| `public.ecr.aws/i4x4j7g8/openclaw-saas/openclaw-custom` | `2026.3.22` | cn-workshop 预拉取 | cn-workshop | ⚠️ 待更新 |

### Platform 镜像

| 镜像 | Tag | 分支 | 状态 |
|------|-----|------|------|
| `956045422469.dkr.ecr.us-west-2.amazonaws.com/openclaw-saas-platform` | `latest` | main | ✅ |
| `public.ecr.aws/i4x4j7g8/openclaw-saas/platform` | `v0.9.23-workshop` | cn-workshop | ⚠️ 待更新 |

### 基础设施镜像 (cn-workshop 预拉取)

| 镜像 (public.ecr.aws/i4x4j7g8/openclaw-saas/) | Tag | 上游来源 | 状态 |
|-------|-----|----------|------|
| `busybox` | `1.37.0` | docker.io/library/busybox | ✅ |
| `nginx` | `1.27-alpine` | docker.io/library/nginx | ✅ |
| `uv` | `0.6-bookworm-slim` | ghcr.io/astral-sh/uv | ✅ |
| `tailscale` | `2026.03.18` | ghcr.io/tailscale/tailscale | ✅ |
| `rclone` | `1.68` | docker.io/rclone/rclone | ✅ |
| `chromium` | `2026.03.17` | ghcr.io/browserless/chromium | ✅ |
| `openclaw-saas-dev-metrics-exporter` | `v0.1.0` | 自建 | ✅ |
| `billing-consumer` | `v0.1.0` | 自建 | ✅ |

---

## 变更日志

### 2026-04-12

**main 分支**
- `ab13810` — 重构 k8s_client.py：删除所有 `if effective_image:` 条件逻辑
  - ACP/acpx/gateway 配置无条件注入
  - 设 `readOnlyRootFilesystem: false`
  - 删除 init container、.acpxrc.json (kiro)、workspace.initialFiles
  - defaultAgent 从 kiro → claude
  - 删除 `import json`（不再需要）

**待做**
- [ ] main: 删除 `custom-image/` 目录
- [ ] main: 清空 Global Secret 中 `DEFAULT_AGENT_IMAGE`
- [ ] cn: cherry-pick main ab13810 + 适配（加 .acpxrc.json, 保留 custom image 引用）
- [ ] cn: 新 Dockerfile（预装 acpx + claude-agent-acp + codex-acp + kiro-cli, symlink → PVC）
- [ ] cn: build + push 新 custom image（tag: `2026.4.12`）
- [ ] cn-workshop: 同步 cn 改动 + 更新预拉取镜像版本
- [ ] cn-workshop: 更新 platform image tag

---

## 版本规则

- **Agent custom image tag**: 跟随日期 `YYYY.M.DD`（如 `2026.4.12`）
- **Platform image tag**: 语义化 `v{major}.{minor}.{patch}[-workshop]`
- **基础设施镜像 tag**: 跟随上游版本号
- **不使用 `latest` tag 推送到 public ECR**（参考 TOOLS.md 规则）
