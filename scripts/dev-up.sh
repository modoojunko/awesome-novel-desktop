#!/bin/bash
# dev-up.sh — 本地开发一键启动/停止（C端 + S端 全栈）
#
# 默认使用 Docker Compose；Docker 不可用时可用 --native 走本地直跑。
#
#   ./scripts/dev-up.sh [start]             Docker Compose 启动全部服务
#   ./scripts/dev-up.sh [start] --native    本地直跑（无需 Docker）
#   ./scripts/dev-up.sh stop [--native]     停止全部服务
#   ./scripts/dev-up.sh status [--native]   查看各服务状态
#   ./scripts/dev-up.sh restart [--native]  重启全部服务
#   ./scripts/dev-up.sh logs <名称> [--native]  跟踪某个服务日志
#
# Docker Compose 端口：C端 5174 / C端API 8000 / S端API 19000 / S端 5173
#   （可用 CLIENT_WEB_HOST_PORT 等环境变量覆盖，见 docker-compose.yml）
# 本地直跑端口：C端 5173 / C端API 8000 / S端API 19000 / S端 5175
#   （可用 C_FRONT_PORT / C_BACK_PORT / S_BACK_PORT / S_FRONT_PORT 覆盖）
#
# 运行数据（PID/日志）写在 .dev-runtime/（已 gitignore）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="$ROOT/.dev-runtime"
LOG_DIR="$RUNTIME_DIR/logs"
mkdir -p "$LOG_DIR"

C_FRONT_PORT="${C_FRONT_PORT:-5173}"
C_BACK_PORT="${C_BACK_PORT:-8000}"
S_BACK_PORT="${S_BACK_PORT:-19000}"
S_FRONT_PORT="${S_FRONT_PORT:-5175}"

# 解析参数：--native 表示本地直跑，否则用 Docker
MODE="docker"
ARGS=()
for arg in "$@"; do
  case "$arg" in
    --native) MODE="native" ;;
    *) ARGS+=("$arg") ;;
  esac
done

ACTION="${ARGS[0]:-start}"

port_busy() {
  lsof -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

compose_available() {
  docker info >/dev/null 2>&1
}

docker_required() {
  echo ""
  echo "Docker 不可用：Docker Desktop 引擎未启动（通常需要先在 Docker Desktop 窗口登录账号）。" >&2
  echo "完成登录后重试；或改用本地直跑：./scripts/dev-up.sh $ACTION --native" >&2
  exit 1
}

# ═══════════════════ Docker Compose 模式 ═══════════════════

compose_up() {
  compose_available || docker_required
  echo "── Docker Compose 启动全部服务 ──"
  (cd "$ROOT" && docker compose up -d --build)
  echo "等待服务就绪..."
  sleep 6
  compose_status
  echo ""
  echo "使用：C端创作应用  http://localhost:${CLIENT_WEB_HOST_PORT:-5174}"
  echo "      S端管理门户  http://localhost:${SERVER_WEB_HOST_PORT:-5173}"
  echo "日志：./scripts/dev-up.sh logs <服务名>（server-backend / server-frontend / client-backend / client-frontend）"
}

compose_down() {
  echo "── Docker Compose 停止全部服务 ──"
  (cd "$ROOT" && docker compose down)
}

compose_status() {
  compose_available || docker_required
  echo "── Docker Compose 服务状态 ──"
  (cd "$ROOT" && docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}")
}

compose_logs() {
  local name="$1"
  local service
  case "$name" in
    C端前端|client-frontend) service="client-frontend" ;;
    C端后端|client-backend)  service="client-backend" ;;
    S端前端|server-frontend) service="server-frontend" ;;
    S端后端|server-backend)  service="server-backend" ;;
    *) service="$name" ;;
  esac
  (cd "$ROOT" && docker compose logs -f "$service")
}

# ═══════════════════ 本地直跑模式（--native） ═══════════════════

# Node 运行时：优先 PATH，缺失时回退到 Codex bundled runtime
ensure_node_runtime() {
  if command -v node >/dev/null 2>&1; then
    return 0
  fi
  BUNDLED_NODE="/Users/modoojunko/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin"
  if [[ -x "$BUNDLED_NODE/node" ]]; then
    export PATH="$BUNDLED_NODE:$PATH"
    echo "[env] 使用 bundled Node: $BUNDLED_NODE"
  else
    echo "错误：找不到 node，请先安装 Node.js 18+" >&2
    exit 1
  fi
}

ensure_pkg_mgr() {
  PKG_MGR="$(command -v pnpm || true)"
  if [[ -z "$PKG_MGR" ]]; then
    FALLBACK_PNPM="/Users/modoojunko/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback/pnpm"
    if [[ -x "$FALLBACK_PNPM" ]]; then
      PKG_MGR="$FALLBACK_PNPM"
    else
      PKG_MGR="$(command -v npm || true)"
    fi
  fi
  if [[ -z "$PKG_MGR" ]]; then
    echo "错误：找不到 pnpm/npm" >&2
    exit 1
  fi
}

ensure_python_deps() {
  local dir="$1"
  if [[ ! -x "$dir/.venv/bin/python" ]]; then
    echo "[deps] 创建 $dir/.venv ..."
    python3 -m venv "$dir/.venv"
  fi
  if ! "$dir/.venv/bin/python" -c "import fastapi" >/dev/null 2>&1; then
    echo "[deps] 安装 $dir 后端依赖（首次较慢）..."
    "$dir/.venv/bin/python" -m ensurepip --upgrade >/dev/null 2>&1 || true
    "$dir/.venv/bin/python" -m pip install -q -r "$dir/requirements.txt"
  fi
}

ensure_node_deps() {
  local dir="$1"
  if [[ ! -d "$dir/node_modules" ]]; then
    echo "[deps] 安装 $dir 前端依赖（首次较慢）..."
    (cd "$dir" && "$PKG_MGR" install)
  fi
}

ensure_all_deps() {
  ensure_node_runtime
  ensure_pkg_mgr
  ensure_python_deps "$ROOT/client/backend"
  ensure_python_deps "$ROOT/server"
  ensure_node_deps "$ROOT/client/frontend"
  ensure_node_deps "$ROOT/server/frontend"
}

native_start_one() {
  local name="$1" port="$2" logfile="$3"; shift 3
  local pidfile="$RUNTIME_DIR/$name.pid"

  if port_busy "$port"; then
    echo "[skip] $name 已在运行（端口 $port 被占用）"
    return 0
  fi

  nohup bash -c "$*" >"$LOG_DIR/$logfile" 2>&1 &
  echo $! > "$pidfile"
  echo "[start] $name (pid $!，端口 $port)"
}

native_start_all() {
  ensure_all_deps
  echo "── 本地直跑启动全部服务 ──"

  # 提示词模板源（c-prompt-source-flip）：sibling 提示词仓检出（PROMPTS_DIR 可覆盖）。
  # 主库不跟踪 .prompt，原生直跑不经 compose，须在此注入 PROMPT_PACK_DEV_DIR；
  # 缺检出时留空（loader 按未装包 503 语义，不阻断起栈）。
  PROMPTS_SRC="${PROMPTS_DIR:-$ROOT/../awesome-novel-prompts/prompts}"
  PROMPTS_ENV=""
  if [[ -d "$PROMPTS_SRC" ]]; then
    PROMPTS_ENV="PROMPT_PACK_DEV_DIR=$PROMPTS_SRC"
    echo "[env] 提示词模板源：$PROMPTS_SRC"
  else
    echo "[warn] 提示词模板源不在位（$PROMPTS_SRC）——AI 功能将按未装包提示"
  fi

  native_start_one "S端后端" "$S_BACK_PORT" "s-backend.log" \
    "cd '$ROOT/server' && mkdir -p data && DB_DIR=./data .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port $S_BACK_PORT"

  native_start_one "S端前端" "$S_FRONT_PORT" "s-frontend.log" \
    "cd '$ROOT/server/frontend' && ./node_modules/.bin/vite dev --port $S_FRONT_PORT"

  native_start_one "C端后端" "$C_BACK_PORT" "c-backend.log" \
    "cd '$ROOT/client/backend' && SERVER_API_BASE=http://127.0.0.1:$S_BACK_PORT/api DATA_ROOT=./data $PROMPTS_ENV .venv/bin/uvicorn main:app --host 127.0.0.1 --port $C_BACK_PORT"

  native_start_one "C端前端" "$C_FRONT_PORT" "c-frontend.log" \
    "cd '$ROOT/client/frontend' && ./node_modules/.bin/vite dev --port $C_FRONT_PORT"

  echo ""
  echo "等待服务就绪..."
  sleep 4
  native_status
  echo ""
  echo "使用：C端创作应用  http://localhost:$C_FRONT_PORT"
  echo "      S端管理门户  http://localhost:$S_FRONT_PORT"
  echo "日志：tail -f $LOG_DIR/<服务>.log 或 ./scripts/dev-up.sh logs <名称> --native"
}

native_stop_all() {
  echo "── 停止本地直跑服务 ──"
  local stopped=0
  for pidfile in "$RUNTIME_DIR"/*.pid; do
    [[ -f "$pidfile" ]] || continue
    local name pid
    name="$(basename "$pidfile" .pid)"
    pid="$(cat "$pidfile")"
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      echo "[stop] $name (pid $pid)"
      stopped=1
    fi
    rm -f "$pidfile"
  done
  [[ "$stopped" -eq 0 ]] && echo "没有由本脚本管理的运行中服务（手动启动的服务请自行停止）。"
}

native_status() {
  echo "── 本地直跑服务状态 ──"
  local rows=(
    "C端前端|$C_FRONT_PORT|http://localhost:$C_FRONT_PORT/"
    "C端后端|$C_BACK_PORT|http://127.0.0.1:$C_BACK_PORT/api/health"
    "S端后端|$S_BACK_PORT|http://127.0.0.1:$S_BACK_PORT/api/auth-page"
    "S端前端|$S_FRONT_PORT|http://localhost:$S_FRONT_PORT/"
  )
  local row
  for row in "${rows[@]}"; do
    local name port url
    name="${row%%|*}"; port="$(echo "$row" | cut -d'|' -f2)"; url="${row##*|}"
    if port_busy "$port"; then
      local code
      code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "$url" || echo ERR)"
      printf "  %-10s 端口 %-5s 运行中 (HTTP %s)\n" "$name" "$port" "$code"
    else
      printf "  %-10s 端口 %-5s 未运行\n" "$name" "$port"
    fi
  done
}

native_logs() {
  local name="$1"
  local logfile="$LOG_DIR/$name.log"
  if [[ ! -f "$logfile" ]]; then
    echo "没有找到 $name 的日志（$logfile）" >&2
    exit 1
  fi
  tail -f "$logfile"
}

native_restart() {
  native_stop_all
  sleep 1
  native_start_all
}

# ═══════════════════ 入口 ═══════════════════

if [[ "$MODE" == "docker" ]]; then
  case "$ACTION" in
    start)   compose_up ;;
    stop)    compose_down ;;
    status)  compose_status ;;
    restart) compose_down; compose_up ;;
    logs)    compose_logs "${ARGS[1]:?用法: ./scripts/dev-up.sh logs <服务名>}" ;;
    *)       echo "用法: $0 [start|stop|status|restart|logs <名称>] [--native]" >&2; exit 1 ;;
  esac
else
  case "$ACTION" in
    start)   native_start_all ;;
    stop)    native_stop_all ;;
    status)  native_status ;;
    restart) native_restart ;;
    logs)    native_logs "${ARGS[1]:?用法: ./scripts/dev-up.sh logs <服务名称> --native}" ;;
    *)       echo "用法: $0 [start|stop|status|restart|logs <名称>] --native" >&2; exit 1 ;;
  esac
fi
