# Docker 部署指南

## 快速开始

### 前置要求
- Docker 20.10+
- Docker Compose 2.0+

### 一键启动

```bash
# 1. 配置环境变量
cp backend/.env.example backend/.env
# 编辑 backend/.env，填入你的 AI API Key

# 2. 构建并启动
docker-compose up -d --build

# 3. 查看日志
docker-compose logs -f

# 4. 访问应用
# 前端: http://localhost:3000
# 后端: http://localhost:9000/docs
```

### 停止服务

```bash
docker-compose down
```

## 常用命令

### 查看运行状态
```bash
docker-compose ps
```

### 查看日志
```bash
# 所有服务
docker-compose logs -f

# 仅后端
docker-compose logs -f backend

# 仅前端
docker-compose logs -f frontend
```

### 重启服务
```bash
# 重启所有
docker-compose restart

# 重启后端
docker-compose restart backend
```

### 进入容器
```bash
# 进入后端容器
docker-compose exec backend bash

# 进入前端容器
docker-compose exec frontend sh
```

## 数据管理

### 数据持久化

以下数据会持久化到宿主机：
- `backend/autotestcase.db` - SQLite 数据库
- `backend/uploads/` - 用户上传的文件
- `backend/logs/` - 应用日志

### 数据备份

```bash
# 备份数据库和上传文件
tar -czf testflow-backup-$(date +%Y%m%d).tar.gz \
  backend/autotestcase.db \
  backend/uploads/

# 恢复备份
tar -xzf testflow-backup-20231201.tar.gz
```

### 清理数据

```bash
# 停止并删除容器（保留数据）
docker-compose down

# 删除所有数据（危险操作！）
docker-compose down -v
rm -rf backend/autotestcase.db backend/uploads/* backend/logs/*
```

## 更新应用

```bash
# 1. 拉取最新代码
git pull

# 2. 重新构建并启动
docker-compose up -d --build

# 3. 查看日志确认启动成功
docker-compose logs -f
```

## 故障排查

### 后端无法启动

```bash
# 查看后端日志
docker-compose logs backend

# 常见问题：
# 1. 端口被占用 - 修改 docker-compose.yml 中的端口映射
# 2. 依赖安装失败 - 检查网络连接
# 3. 数据库文件权限 - chmod 666 backend/autotestcase.db
```

### 前端无法访问

```bash
# 查看前端日志
docker-compose logs frontend

# 检查 Nginx 配置
docker-compose exec frontend cat /etc/nginx/conf.d/default.conf

# 测试后端连接
docker-compose exec frontend wget -O- http://backend:9000/docs
```

### 容器间无法通信

```bash
# 检查网络
docker network ls
docker network inspect testflow_testflow-network

# 重建网络
docker-compose down
docker-compose up -d
```

## 性能优化

### 镜像大小优化

当前镜像大小：
- 后端: ~500MB
- 前端: ~25MB

### 构建缓存

```bash
# 清理构建缓存
docker builder prune

# 完全重新构建
docker-compose build --no-cache
```

## 生产环境建议

1. **使用环境变量管理敏感信息**
   ```bash
   # 不要将 .env 文件提交到 Git
   # 在服务器上单独配置
   ```

2. **配置反向代理**
   ```nginx
   # 使用 Nginx/Caddy 作为入口
   # 配置 HTTPS
   # 配置域名
   ```

3. **定期备份数据**
   ```bash
   # 设置 cron 任务
   0 2 * * * /path/to/backup.sh
   ```

4. **监控日志**
   ```bash
   # 使用 ELK/Loki 等日志系统
   # 配置告警
   ```

5. **资源限制**
   ```yaml
   # 在 docker-compose.yml 中添加
   deploy:
     resources:
       limits:
         cpus: '2'
         memory: 2G
   ```

## 端口说明

| 服务 | 容器端口 | 宿主机端口 | 说明 |
|------|---------|-----------|------|
| frontend | 80 | 3000 | 前端 Web 界面 |
| backend | 9000 | 9000 | 后端 API 服务 |

## 环境变量

### 后端环境变量 (backend/.env)

```bash
# AI API 配置（必填）
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1

# 数据库配置
DATABASE_URL=sqlite:///./autotestcase.db

# JWT 密钥（生产环境必须修改）
SECRET_KEY=your-super-secret-key-change-in-production

# 其他配置见 backend/.env.example
```

## 常见问题

**Q: 如何修改端口？**
A: 编辑 `docker-compose.yml` 中的 `ports` 配置

**Q: 如何使用自己的域名？**
A: 配置外部 Nginx 反向代理到 `localhost:3000`

**Q: 数据库可以换成 PostgreSQL 吗？**
A: 可以，修改 `backend/app/config.py` 和 `docker-compose.yml`

**Q: 如何查看 API 文档？**
A: 访问 http://localhost:9000/docs

## 技术支持

遇到问题请提交 Issue: https://github.com/Ggbond626/testflow/issues
