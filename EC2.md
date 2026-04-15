# EC2 部署环境搭建指南

从 CloudFormation 创建的 EC2 跳板机完成 OpenClaw SaaS 全部部署流程。

> 以下命令假设 EC2 使用 **Amazon Linux 2023 (x86_64)**，以 `ec2-user` 身份登录。
> EC2 通过 CloudFormation 模板自动绑定 IAM Role，已具备 EKS Admin + ECR + S3 等权限。

---

## 0. 前置条件

- EC2 由 CloudFormation 模板创建（自带 IAM Role + EKS Access Entry）
- 实例类型 `t3.medium` 以上（Docker 构建需要内存）
- 安全组已放通 443 出站

---

## 1. 系统基础工具

```bash
sudo yum install -y git tar gzip vim jq unzip make gcc gcc-c++
```

---

## 2. AWS CLI v2

Amazon Linux 2023 通常已预装。验证或更新：

```bash
aws --version

# 如需更新
curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
unzip -qo /tmp/awscliv2.zip -d /tmp
sudo /tmp/aws/install --update
rm -rf /tmp/aws /tmp/awscliv2.zip
```

验证 IAM 身份（应显示 EC2 Role）：

```bash
aws sts get-caller-identity
```

> **注意：** 后续命令使用默认 profile。如果 `~/.aws/config` 中配置的是 `[profile cn]` 而非 `[default]`，需要 `export AWS_PROFILE=cn`。

---

## 3. Docker + Buildx

```bash
sudo yum install -y docker
sudo systemctl enable docker && sudo systemctl start docker
sudo usermod -aG docker ec2-user

# 重新登录使 docker 组生效
exit
# 重新 SSH/SSM 登录后验证
docker info
```

安装 buildx（跨架构构建 arm64 镜像）：

```bash
BUILDX_VERSION=v0.21.2
mkdir -p ~/.docker/cli-plugins
curl -fsSL "https://github.com/docker/buildx/releases/download/${BUILDX_VERSION}/buildx-${BUILDX_VERSION}.linux-amd64" \
  -o ~/.docker/cli-plugins/docker-buildx
chmod +x ~/.docker/cli-plugins/docker-buildx
docker buildx version

# 创建多架构 builder
docker buildx create --name multiarch --use
docker buildx inspect --bootstrap

# 注册 QEMU（x86 EC2 构建 arm64 镜像需要）
docker run --privileged --rm tonistiigi/binfmt --install arm64
```

> **⚠️ sudo 与 docker 凭证隔离：** 加入 docker 组后，所有 docker 命令都**不要**加 `sudo`。`sudo docker push` 会使用 root 的凭证存储，导致 push 失败。

---

## 4. Node.js 22.x

Vite 7 需要 Node.js 20.19+ 或 22.12+：

```bash
curl -fsSL https://rpm.nodesource.com/setup_22.x | sudo bash -
sudo yum install -y nodejs
node --version   # 应 >= 22.12
```

---

## 5. Python 3.11 + CDK

```bash
# Amazon Linux 2023 自带 Python 3.9，安装 3.11
sudo yum install -y python3.11 python3.11-pip python3.11-devel

# 设为默认（可选）
sudo alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1
python3 --version

# 安装 CDK CLI
sudo npm install -g aws-cdk
cdk --version
```

---

## 6. kubectl

```bash
curl -fsSL "https://dl.k8s.io/release/$(curl -sL https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
  -o /tmp/kubectl
sudo install -o root -g root -m 0755 /tmp/kubectl /usr/local/bin/kubectl
rm -f /tmp/kubectl
kubectl version --client
```

> **中国区网络不通？** 使用镜像源：
> ```bash
> curl -fsSL https://dqz9mdd9dvd79.cloudfront.net/tools/kubectl -o /tmp/kubectl
> sudo install -o root -g root -m 0755 /tmp/kubectl /usr/local/bin/kubectl
> ```

---

## 7. Helm

```bash
curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
helm version --short
```

> **中国区网络不通？** 使用镜像源：
> ```bash
> curl -fsSL https://dqz9mdd9dvd79.cloudfront.net/tools/helm.tar.gz -o /tmp/helm.tar.gz
> tar xzf /tmp/helm.tar.gz -C /tmp
> sudo mv /tmp/linux-amd64/helm /usr/local/bin/helm
> rm -rf /tmp/helm.tar.gz /tmp/linux-amd64
> ```

---

## 8. 验证所有工具

```bash
echo "=== Tool Versions ==="
aws --version
docker --version
docker buildx version
node --version
python3 --version
cdk --version
kubectl version --client
helm version --short
echo "=== AWS Identity ==="
aws sts get-caller-identity
```

---

## 9. 验证 EKS 访问

CloudFormation 模板已通过 `EC2AccessEntry` 自动授予 EC2 Role 集群管理员权限，无需额外配置：

```bash
export AWS_DEFAULT_REGION=cn-northwest-1

aws eks update-kubeconfig --name openclaw-prod --region cn-northwest-1
kubectl get nodes
```

如果报 `Unauthorized`，检查 CloudFormation Stack 是否部署成功：

```bash
aws cloudformation describe-stacks --stack-name openclaw-prod \
  --query 'Stacks[0].StackStatus' --output text
# 应为 CREATE_COMPLETE
```

---

## 后续步骤

环境准备完成后，回到 [README.md](README.md) 继续执行：

- **CloudFormation 部署**：从 [步骤 4 - 镜像准备](#4-镜像准备) 开始
- **CDK 部署**：从 [方式二 - 步骤 2](#2-部署基础设施) 开始

---

## 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `docker buildx build` 失败 arm64 | 缺少 QEMU | `docker run --privileged --rm tonistiigi/binfmt --install arm64` |
| `docker buildx` 报 `unknown flag: --platform` | 系统包不含 buildx 插件 | 手动安装 buildx 插件（见步骤 3） |
| `docker push` 层显示 `Unavailable` | `sudo docker push` 凭证隔离 | 统一不用 sudo（加入 docker 组后） |
| `docker login` 指向 Docker Hub | `${ECR}` 环境变量为空 | 确认 `AWS_ACCOUNT_ID` 和 `AWS_DEFAULT_REGION` 已设置 |
| `npm install` 报 Node.js 版本太低 | Vite 7 需要 Node.js ≥ 22.12 | 安装 Node.js 22.x（见步骤 4） |
| `npm install -g` 报 `EACCES` | 全局安装需要 root | 加 `sudo` |
| `python3 -m venv` 报 `ensurepip` | 缺少 venv 包 | `sudo yum install python3.11-devel` |
| `The config profile (cn) could not be found` | 无对应 AWS profile | `export AWS_PROFILE=default` |
| ECR push 报 `no basic auth credentials` | ECR 登录过期 (12h) | 重新 `aws ecr get-login-password` |
| CDK deploy 到错误 region | 环境变量未设置 | 确认 `AWS_DEFAULT_REGION=cn-northwest-1` |
