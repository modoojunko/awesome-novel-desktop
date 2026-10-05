#!/bin/bash
# Run all test suites

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Awesome Novel — 全量测试"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── Backend API tests ─────────────────────────────────────────────────
echo "▸ 后端 API 测试 (pytest)..."
cd "$(dirname "$0")/../backend"
python -m pytest tests/ -v
BACKEND_EXIT=$?
echo ""

# ── Frontend E2E tests ────────────────────────────────────────────────
echo "▸ 前端 E2E 测试 (Playwright)..."
cd "$(dirname "$0")/../frontend"
npx playwright test
FRONTEND_EXIT=$?
echo ""

# ── Summary ───────────────────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  测试结果"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
[ $BACKEND_EXIT -eq 0 ] && echo "  ✓ 后端 API: 通过" || echo "  ✗ 后端 API: 失败"
[ $FRONTEND_EXIT -eq 0 ] && echo "  ✓ 前端 E2E: 通过" || echo "  ✗ 前端 E2E: 失败"
echo ""

if [ $BACKEND_EXIT -eq 0 ] && [ $FRONTEND_EXIT -eq 0 ]; then
    echo "  ✅ 全部测试通过！"
    exit 0
else
    echo "  ❌ 存在失败的测试"
    exit 1
fi
