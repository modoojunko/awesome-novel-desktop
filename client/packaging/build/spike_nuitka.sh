#!/bin/zsh
# c-nuitka-full macOS spike：验证 pywebview 全栈能否过 Nuitka standalone。
# 用法：./spike_nuitka.sh   （日志 spike-build.log，产物 dist-nuitka/）
set -x
cd "$(dirname "$0")"

PY=/Users/modoojunko/Desktop/coding/ai-novel/client/backend/.venv/bin/python
BACKEND=../../backend
ROOT=../../..

# 与 build.spec hiddenimports 逐条同源（spike 阶段手抄；单源抽取是正式任务 1）
INCLUDES=(
  main config brand db ai_client aiosqlite sqlalchemy.ext.asyncio anthropic openai
  yaml httpx jose multipart
  auth_local auth_local.middleware auth_local.models auth_local.router auth_local.service
  settings chapters prompt write archive
  prompt_pack prompt_pack.container prompt_pack.localkey prompt_pack.sync
  api_configs genres workflow workflow.engine workflow.gates workflow.tier
  filesystem filesystem.storage filesystem.init settings.render
  story story.engine story.character_agent story.models
  novels models models.user models.project models.token_log models.chapter models.volume
  backup backup.router backup.export backup.format backup.importer
  job_runner manuscript manuscript.router manuscript.service manuscript.content manuscript.render
)
INC_FLAGS=()
for m in "${INCLUDES[@]}"; do INC_FLAGS+=(--include-module="$m"); done

EXCL=(tkinter matplotlib PIL pandas numpy notebook test unittest)
EXC_FLAGS=()
for m in "${EXCL[@]}"; do EXC_FLAGS+=(--nofollow-import-to="$m"); done

time env PYTHONPATH="$BACKEND" "$PY" -m nuitka \
  "${INC_FLAGS[@]}" \
  "${EXC_FLAGS[@]}" \
  --include-data-dir="$BACKEND/reference=reference" \
  --include-data-dir=../../frontend/dist=frontend \
  --include-data-file="$ROOT/brand/brand.json=brand.json" \
  --include-data-file="$ROOT/LICENSE=LICENSE" \
  --include-data-file="$ROOT/THIRD-PARTY-NOTICES.txt=THIRD-PARTY-NOTICES.txt" \
  --macos-create-app-bundle \
  --macos-app-name="AI Novel" \
  --macos-app-icon=icon.icns \
  --output-dir=dist-nuitka \
  --report=spike-report.xml \
  --assume-yes-for-downloads \
  pywebview_app.py
echo "SPIKE_EXIT=$?"
