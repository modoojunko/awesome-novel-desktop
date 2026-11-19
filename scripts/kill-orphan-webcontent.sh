#!/usr/bin/env bash
# kill-orphan-webcontent.sh — 孤儿 WebKit WebContent 清扫（运维止血工具）
#
# 背景（2026-11-14 实锤，见记忆 c-shelf-slow-orphan-webkit-checkauth）：
#   桌面 App（pywebview/WebKit）卡死被强退后，旧实例的 WebContent XPC 泄漏——
#   宿主已死、挂在 launchd（ppid=1）下继续烧 100% CPU ×2.5 天 + 4.7GB 内存，
#   拖慢整机。App 重启不会回收它，须手动处置。
#
# 孤儿判据（三条同时满足才处置，宁漏勿误杀）：
#   1. ppid=1            宿主已退出（正常 WebContent 的父进程是宿主 App/Safari）
#   2. 无 TCP 句柄       不服务任何网络页面（lsof 全空亦命中）
#   3. CPU > 50%         正在烧机器（0% 的闲置孤儿无害，不动）
#
# 用法：
#   kill-orphan-webcontent.sh            # dry-run（默认）：只列处置集，不杀
#   kill-orphan-webcontent.sh --force    # 真杀（kill -TERM）
set -euo pipefail

MODE="${1:---dry-run}"
case "$MODE" in
  --dry-run) FORCE=0 ;;
  --force)   FORCE=1 ;;
  *) echo "用法: $0 [--dry-run|--force]" >&2; exit 2 ;;
esac

# comm 匹配 WebKit WebContent（macOS 自带 WebKit 栈，Safari/pywebview 共用）
PATTERN='com\.apple\.WebKit\.WebContent'
THRESHOLD=50.0

found=0
# ps -eo pid,ppid,%cpu,comm：按 ppid=1 + 进程名 + CPU 阈值预筛
while read -r pid cpu; do
  # 条件 2：无 TCP 句柄（lsof 对孤儿常返回空/报错，都不算有）
  if lsof -p "$pid" 2>/dev/null | grep -q "TCP"; then
    continue
  fi
  verb=$([ "$FORCE" = 1 ] && echo KILL || echo WOULD-KILL)
  printf '%s pid=%s cpu=%s%% (ppid=1, no TCP)\n' "$verb" "$pid" "$cpu"
  found=$((found + 1))
  if [ "$FORCE" = 1 ]; then
    kill -TERM "$pid"
  fi
done < <(ps -eo pid=,ppid=,%cpu=,comm= | awk -v pat="$PATTERN" -v th="$THRESHOLD" \
  '$2 == 1 && $4 ~ pat && $3 + 0 > th {print $1, $3}')

if [ "$found" -eq 0 ]; then
  echo "no orphan webcontent found (clean)"
fi
