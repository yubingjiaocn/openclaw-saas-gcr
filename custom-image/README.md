# OpenClaw Custom Image

基于 `ghcr.io/openclaw/openclaw:latest` 的自定义镜像，预装 Kiro CLI + Tavily Search skill。

## 运行时文件系统

Operator 设置 `readOnlyRootFilesystem=true`，`HOME=/home/openclaw`。

| 路径 | 来源 | 读写 | 用途 |
|------|------|------|------|
| `/home/openclaw/` | image layer | ❌ 只读 | HOME 目录（root 所有） |
| `/home/openclaw/.openclaw/` | PVC 挂载 | ✅ 可写 | OpenClaw 数据根目录 |
| `/home/openclaw/.openclaw/workspace/` | PVC | ✅ 可写 | 用户工作空间 |
| `/home/openclaw/.openclaw/skills/` | PVC | ✅ 可写 | 用户 skills（init container 拷入） |
| `/home/openclaw/.cache/` | PVC subPath | ✅ 可写 | npm/npx 缓存 |
| `/home/openclaw/.local/` | PVC subPath | ✅ 可写 | 用户本地数据 |
| `/home/openclaw/.kiro/` | image layer | ❌ 只读 | Kiro agent 配置（可读） |
| `/home/openclaw/.acpx` | symlink → `.openclaw/.acpx` | ✅ 可写 | acpx session 数据 |
| `/app/` | image layer | ❌ 只读 | OpenClaw 代码 + 内置 extensions |
| `/app/extensions/acpx/node_modules/` | image layer | ❌ 只读 | 预装的 acpx binary |
| `/opt/openclaw-custom/` | image layer | ❌ 只读 | PVC 内容暂存区（init container 源） |
| `/tmp/` | emptyDir | ✅ 可写 | 临时文件 |

> **注意**：`/home/node/` 是基础镜像的原始 HOME 目录，运行时无人使用，不要往这里写任何内容。

## Dockerfile 职责

Dockerfile **只负责** bake 到 image layer 的内容：

1. **系统工具** → `/usr/local/bin/kiro-cli`、`jq`
2. **acpx 预装** → `/app/extensions/acpx/node_modules/`（匹配 pinned version）
3. **Kiro 配置** → `/home/openclaw/.kiro/`（只读但可读）
4. **acpx symlink** → `/home/openclaw/.acpx` → `.openclaw/.acpx`
5. **PVC 内容暂存** → `/opt/openclaw-custom/skills/`、`KIRO-PLAYBOOK.md`

**不要**在 Dockerfile 中往 PVC 路径（`/home/openclaw/.openclaw/`）写文件，build time 写入的内容会被运行时的 PVC 挂载覆盖。

## Init Container 职责

`init-custom` 容器在每次 pod 启动时执行，使用 custom image 自身作为镜像：

```sh
mkdir -p /data/skills /data/.acpx/sessions
cp -r /opt/openclaw-custom/skills/* /data/skills/
cp /opt/openclaw-custom/KIRO-PLAYBOOK.md /data/workspace/KIRO-PLAYBOOK.md
chown -R 1000:1000 /data/skills /data/.acpx
```

Init container 的 `/data/` 挂载点对应运行时的 `/home/openclaw/.openclaw/`（同一块 PVC）。

## acpx 特殊处理

acpx 需要写 session 数据到 `~/.acpx/`，但 `/home/openclaw/` 是只读的。解决方案：

1. **Dockerfile**：创建 symlink `/home/openclaw/.acpx → /home/openclaw/.openclaw/.acpx`
2. **Init Container**：在 PVC 上创建 `.acpx/sessions/` 目录
3. **运行时**：acpx 写 `~/.acpx/sessions/` → 跟随 symlink → 写入 PVC ✅

## 预装的 acpx 版本

基础镜像的 `/app/extensions/acpx/src/config.ts` 定义了 `ACPX_PINNED_VERSION`。Dockerfile 中的 `npm install acpx@x.x.x` 必须匹配此版本。版本不匹配会触发运行时 re-install → 因 readOnlyRootFilesystem 失败 → ACP 不可用。

升级基础镜像时，检查新的 pinned version 并更新 Dockerfile。

## 构建

```bash
# arm64 (Graviton)
docker build --platform linux/arm64 \
  -t public.ecr.aws/i4x4j7g8/openclaw-saas/openclaw-custom:TAG \
  -t public.ecr.aws/i4x4j7g8/openclaw-saas/openclaw-custom:latest \
  .

# 推送
aws ecr-public get-login-password --region us-east-1 | docker login --username AWS --password-stdin public.ecr.aws/i4x4j7g8
docker push public.ecr.aws/i4x4j7g8/openclaw-saas/openclaw-custom:TAG
docker push public.ecr.aws/i4x4j7g8/openclaw-saas/openclaw-custom:latest
```

## 部署更新

镜像 `pullPolicy: Always`，删除 pod 即可拉取最新镜像：

```bash
kubectl delete pod -n tenant-<name> <agent>-0
```
