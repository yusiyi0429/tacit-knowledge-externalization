# 隐性知识提取平台 — 内网部署

## 目录结构

```
deploy/
├── README.md                                  # 本文件（部署说明）
├── docker-compose.yml                         # 容器编排
├── tacit-knowledge-externalization-*.tar      # ARM64 离线镜像
├── tacit-knowledge-externalization-*.manifest.json  # 镜像清单
├── docker/
│   └── Dockerfile                             # 镜像构建文件（构建用）
├── config/
│   └── llm-config.yaml                        # LLM 配置（编辑内网地址）
├── scripts/
│   └── build-docker-arm64.sh                  # ARM64 构建脚本
└── .dockerignore                              # Docker 构建忽略规则
```

## 快速部署

### 1. 环境准备

- ARM64 服务器（鲲鹏 / 飞腾 / 树莓派等）
- Docker ≥ 24.0 + Docker Compose v2

### 2. 上传 `deploy/` 目录到服务器

将整个 `deploy/` 目录上传到内网服务器任意位置。

### 3. 加载镜像

```bash
cd deploy
docker load -i tacit-knowledge-externalization-arm64.tar
```

### 4. 创建持久化数据目录

```bash
mkdir -p workspace data/kb data/golden logs
```

### 5. 配置 LLM

编辑 `config/llm-config.yaml`，修改模型 API 地址为内网可达地址：

```yaml
# 例如：改为内网网关地址
api_base: http://内网网关IP:端口/v1
api_key: your-api-key
```

### 6. 启动服务

```bash
docker compose up -d
```

### 7. 验证

```bash
curl http://localhost:5000/api/health
# 期望响应：
# {"app_name":"tacit-knowledge-externalization","app_version":"3.0.0","status":"ok",...}
```

浏览器访问 `http://服务器IP:5000`

---

## 数据挂载说明

| 宿主机路径 | 容器内路径 | 内容 | 必须？ |
|-----------|-----------|------|--------|
| `./workspace` | `/app/workspace` | 流水线 JSON、Excel/SKILL 产出、上传附件 | ✅ 是 |
| `./data/kb` | `/app/data/kb` | 知识库 SQLite（生产知识资产） | ✅ 是 |
| `./data/golden` | `/app/data/golden` | 黄金数据库 SQLite（测试基准） | ✅ 是 |
| `./logs` | `/app/logs` | 应用日志 | ✅ 是 |
| `./config/llm-config.yaml` | `/app/config/llm-config.yaml:ro` | LLM 配置（只读） | ✅ 是 |

> **重要**：以上数据目录不挂载会导致容器重启后数据丢失。

---

## 从旧版本迁移数据

如果旧容器未挂卷、数据在容器内部：

```bash
# 从旧容器拷贝数据
docker cp 旧容器名:/app/workspace ./workspace
docker cp 旧容器名:/app/data/kb ./data/kb
docker cp 旧容器名:/app/data/golden ./data/golden
docker cp 旧容器名:/app/logs ./logs

# 停删旧容器
docker stop 旧容器名 && docker rm 旧容器名

# 加载新镜像并启动
docker load -i tacit-knowledge-externalization-arm64.tar
docker compose up -d
```

---

## 版本升级

1. 在开发环境构建新镜像 → 导出 tar → 复制到服务器
2. 停旧容器：`docker compose down`
3. 加载新镜像：`docker load -i 新镜像.tar`
4. 启动：`docker compose up -d`

数据目录保持不变，流水线进度和知识库不受影响。

---

## 常用命令

```bash
# 查看运行状态
docker compose ps

# 查看日志
docker compose logs -f

# 重启服务
docker compose restart

# 停止服务
docker compose down

# 查看版本信息
curl http://localhost:5000/api/version
```

---

## 构建镜像（开发环境）

在项目根目录执行：

```bash
# Linux/macOS
bash deploy/scripts/build-docker-arm64.sh
```

构建产物（tar + manifest）自动输出到 `deploy/` 目录。
