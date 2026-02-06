#!/bin/bash

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  TestFlow - 停止服务脚本${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 停止服务函数
stop_service() {
    local name=$1
    local pid_file=$2

    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            echo -e "${YELLOW}正在停止 $name (PID: $pid) 及其子进程...${NC}"

            # 先杀死所有子进程（uvicorn --reload 的工作进程）
            pkill -P "$pid" 2>/dev/null

            # 再杀死主进程
            kill "$pid" 2>/dev/null

            # 等待进程结束
            local count=0
            while kill -0 "$pid" 2>/dev/null && [ $count -lt 10 ]; do
                sleep 0.5
                count=$((count + 1))
            done
            # 如果进程仍在运行，强制终止（包括子进程）
            if kill -0 "$pid" 2>/dev/null; then
                echo -e "${YELLOW}进程未响应，强制终止...${NC}"
                pkill -9 -P "$pid" 2>/dev/null
                kill -9 "$pid" 2>/dev/null
            fi
            echo -e "${GREEN}$name 已停止${NC}"
        else
            echo -e "${YELLOW}$name 进程不存在 (PID: $pid)${NC}"
        fi
        rm -f "$pid_file"
    else
        echo -e "${YELLOW}$name PID 文件不存在，跳过${NC}"
    fi
}

# 停止后端服务
echo -e "${BLUE}[1/2] 停止后端服务...${NC}"
stop_service "后端服务" "$SCRIPT_DIR/backend/backend.pid"

# 停止前端服务
echo -e "${BLUE}[2/2] 停止前端服务...${NC}"
stop_service "前端服务" "$SCRIPT_DIR/frontend/frontend.pid"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  所有服务已停止${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
