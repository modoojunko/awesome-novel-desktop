#!/bin/zsh
# 一次性全链（单调用内完成，端口 8317/5317/8318 专属本会话）
set -e
WT=/Users/modoojunko/Desktop/coding/ai-novel-wt-thinkproto
DATA=/tmp/proto-think-data
LOGS=/tmp/proto-think-fake

# 0. 清本套残留
for port in 8317 5317 8318; do
  pid=$(lsof -nP -tiTCP:$port -sTCP:LISTEN 2>/dev/null || true)
  [ -n "$pid" ] && kill -9 $pid 2>/dev/null || true
done
sleep 1

# 1. 重置库
rm -f $DATA/novel-dev.db*
cd $WT/client/backend
DATA_ROOT=$DATA PROMPT_PACK_DEV_DIR=/Users/modoojunko/Desktop/coding/awesome-novel-prompts/prompts \
  nohup venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8317 > $LOGS/backend.log 2>&1 &
BACKEND_PID=$!

# 2. 等建表完成
for i in $(seq 1 40); do
  sqlite3 $DATA/novel-dev.db "SELECT count(*) FROM users" >/dev/null 2>&1 && break
  sleep 1
done
sqlite3 $DATA/novel-dev.db "INSERT INTO users (id,email,password_hash,display_name,token_balance,total_tokens,plan,role,status,is_lifetime,api_key,api_base_url,api_model,token,pc_hash,pc_name,server_api,migrated) VALUES ('prototester','prototester@s.local','','prototester',0,0,'max','user','active',0,'','','','','','','',0); INSERT INTO api_configs (id,user_id,name,vendor,vendor_display_name,vendor_override,api_format,thinking_enabled,thinking_effort,api_key,base_url,models,status,created_at,updated_at) VALUES ('f0e1d2c3-0000-4000-8000-000000000001','prototester','MiniMax','openai-compat','OpenAI 兼容',NULL,'anthropic',0,'low','sk-fake-minimax','http://127.0.0.1:8318/anthropic','[\"MiniMax-M3.1-Flash\"]','active',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP);"
echo "db seeded (backend=$BACKEND_PID)"

# 3. 假模型 + 前端
nohup python3 $LOGS/fake_minimax.py > $LOGS/fake.log 2>&1 &
FAKE_PID=$!
cd $WT/client/frontend
VITE_API_PROXY=http://127.0.0.1:8317 nohup node_modules/.bin/vite --port 5317 --strictPort > $LOGS/vite.log 2>&1 &
VITE_PID=$!
for i in $(seq 1 30); do
  curl -s http://localhost:5317/ >/dev/null 2>&1 && break
  sleep 1
done
echo "all up: backend=$BACKEND_PID fake=$FAKE_PID vite=$VITE_PID"

# 4. 抓取（同一调用内，服务生命周期有保障）
node scripts/proto-think-seed-capture.cjs
echo "CAPTURE OK"
