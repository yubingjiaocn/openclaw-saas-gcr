# BRANCHES.md - 分支差异对照表

> 每次开发新功能时，必须对照此表确认该功能在各分支上是否需要、实现方式是否有差异。

## 分支定位

| 分支 | 环境 | 用途 |
|------|------|------|
| **main** | Global (us-west-2) | 生产环境，原生 OpenClaw 镜像，npx 可用 |
| **cn** | China (cn-northwest-1) | CN 生产环境，custom image，npm/npx 被墙 |
| **cn-workshop** | China Workshop | CN 培训/演示环境，基于 cn 分支，额外包含部署脚本和预拉取镜像 |

## 核心差异对照

### 1. Agent 镜像

| 配置项 | main | cn | cn-workshop |
|--------|------|----|-------------|
| 默认镜像 | 原生 `ghcr.io/openclaw/openclaw` (operator 默认) | custom image (预装 binary) | 同 cn，镜像从 public ECR 拉取 |
| `DEFAULT_AGENT_IMAGE` env | 空（不设置） | `public.ecr.aws/.../openclaw-custom` | 同 cn |
| `DEFAULT_AGENT_IMAGE_TAG` env | 空 | 具体版本号 | 同 cn |
| `custom-image/` 目录 | ❌ 不存在 | ✅ 维护 Dockerfile | ✅ 同 cn |
| `readOnlyRootFilesystem` | `false` | `false` | `false` |

### 2. ACP / acpx

| 配置项 | main | cn | cn-workshop |
|--------|------|----|-------------|
| acpx 安装方式 | 运行时 npm install (自动) | Dockerfile 预装 | 同 cn |
| ACP agent 安装方式 | npx 按需下载 | Dockerfile 预装 (`npm install -g`) | 同 cn |
| `.acpxrc.json` | ❌ 不需要（走 npx 内置） | ✅ `workspace.initialFiles` 注入 | 同 cn |
| `.acpxrc.json` 内容 | N/A | 指向本地 binary 路径 | 同 cn |
| `acp.defaultAgent` | `claude` | `claude` | `claude` |
| `acp.allowedAgents` | claude, codex, gemini, pi, opencode | claude, codex, kiro, gemini, opencode | 同 cn |
| 冷启动开销 | ~7s (npm install + npx) | 0s (全部预装) | 同 cn |

### 3. Kiro

| 配置项 | main | cn | cn-workshop |
|--------|------|----|-------------|
| kiro-cli | ❌ 不安装 | ✅ Dockerfile 预装 | 同 cn |
| kiro config | 无 | 镜像层 `/opt/kiro-config/` | 同 cn |
| kiro-wrapper.sh | ❌ 不需要 | ❌ 不需要（改用 --config 参数） | 同 cn |
| init container | ❌ 不需要 | ❌ 不需要 | 同 cn |

### 4. k8s_client.py

| 逻辑 | main | cn | cn-workshop |
|------|------|----|-------------|
| ACP/acpx 配置 | 无条件注入 | 无条件注入 | 同 cn |
| gateway local mode | 无条件注入 | 无条件注入 | 同 cn |
| `if effective_image:` 分支 | ❌ 已删除 | ❌ 已删除 | 同 cn |
| `workspace.initialFiles` | 无 | `.acpxrc.json` | 同 cn |
| init container | 无 | 无 | 同 cn |
| `security.readOnlyRootFilesystem` | `false` | `false` | `false` |
| `NODE_OPTIONS` | `--max-old-space-size=1536` | `--max-old-space-size=1536` | `--max-old-space-size=3072` |

### 5. LLM Providers

| Provider | main | cn | cn-workshop |
|----------|------|----|-------------|
| `bedrock` (AWS AK/SK + Region) | ✅ | ✅ | ✅ |
| `bedrock-irsa` (Platform Managed, 无需 key) | ✅ **默认** | ❌ (无 IRSA) | ❌ |
| `bedrock-apikey` (IAM AK/SK, region optional) | ✅ | ✅ | ✅ |
| `openai` | ✅ | ✅ | ✅ |
| `anthropic` | ✅ | ✅ | ✅ |
| `openai-compatible` | ✅ | ✅ **默认** | ✅ **默认** |

> **bedrock-irsa** 仅适用于 Global (main)：EKS node role 通过 IRSA 自动获得 Bedrock 权限，
> 用户创建 agent 时无需提供任何 API key。CN 区不支持 IRSA + Bedrock，故不可用。

### 6. 平台配置 (config.py)

| 配置项 | main | cn | cn-workshop |
|--------|------|----|-------------|
| `AWS_REGION` | `us-west-2` | `cn-northwest-1` | `us-west-2` (workshop 用 global) |
| `AWS_PARTITION` | `aws` | `aws-cn` | `aws` |
| `AVAILABLE_CHANNELS` | 空 (全部) | `feishu` | 空 |
| `SQS_QUEUE_URL` | us-west-2 queue | cn-northwest-1 queue | us-west-2 queue |
| `ECR_REGISTRY` | us-west-2 ECR | cn-northwest-1 ECR | us-west-2 ECR |

### 7. cn-workshop 额外内容

cn-workshop 分支在 cn 基础上额外包含：

| 内容 | 说明 |
|------|------|
| `cloudformation/` | CloudFormation 模板（VPC、EKS、RDS） |
| `scripts/step2-k8s-components.sh` | K8s 组件部署脚本（含镜像预拉取） |
| `scripts/step3-platform-api.sh` | Platform API 部署脚本 |
| `scripts/destroy.sh` | 环境销毁脚本 |
| `scripts/e2e-test.py` | 端到端测试 |
| `yaml/` | 静态 K8s manifests (CRD, operator, storage) |
| `WORKSHOP.md` | Workshop 操作手册 |
| `platform/web-console/dist/` | 前端预编译产物 |

---

## 开发流程

1. **新功能先在 main 开发**
2. **对照此表确认 cn 分支是否需要** → 如需要，cherry-pick 或手动适配
3. **cn 测试通过后更新 cn-workshop** → 更新镜像版本、部署脚本
4. **更新 VERSIONS.md** 记录版本变更
