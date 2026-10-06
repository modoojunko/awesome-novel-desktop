#!/bin/bash
# Awesome Novel 端到端测试 — 从注册到生成提示词
# 启动后端后运行: bash scripts/e2e-test.sh
set -e

BASE="${1:-http://localhost:8000}"

echo "=== 1. 注册测试用户 ==="
REG=$(curl -sf -X POST "$BASE/api/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email":"test@ainovel.cn","password":"test123","display_name":"测试作者"}')
echo "$REG" | python3 -m json.tool
TOKEN=$(echo "$REG" | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
AUTH="Authorization: Bearer $TOKEN"

echo ""
echo "=== 2. 创建项目 ==="
PROJ=$(curl -sf -X POST "$BASE/api/projects" \
  -H "Content-Type: application/json" \
  -H "$AUTH" \
  -d '{"name":"钟声","synopsis":"三年前的一桩悬案，一个被调走的前刑警，一个失踪的证人。当陆征开始调查时，他发现所有的线索都指向他自己。","genre_profile":"suspense-crime"}')
echo "$PROJ" | python3 -m json.tool
PROJ_ID=$(echo "$PROJ" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
SLUG=$(echo "$PROJ" | python3 -c "import sys,json; print(json.load(sys.stdin)['slug'])")

echo ""
echo "=== 3. AI 起名建议（测试 AI 连通性） ==="
curl -sf -X POST "$BASE/api/ai/suggest-meta" \
  -H "Content-Type: application/json" \
  -H "$AUTH" \
  -d '{"premise":"一个退役刑警在调查三年前的悬案时，发现所有线索都指向他自己"}' \
  | python3 -m json.tool

echo ""
echo "=== 4. 创建卷 ==="
curl -sf -X POST "$BASE/api/projects/$PROJ_ID/volumes" \
  -H "Content-Type: application/json" \
  -H "$AUTH" \
  -d '{"vol_num":1,"title":"第一卷"}' | python3 -m json.tool

echo ""
echo "=== 5. 创建章节（含完整章纲） ==="
CHAPTER_DATA='{
  "volume":1,"chapter":1,"title":"第一声钟响",
  "status":"outline",
  "outline":{
    "summary":"陆征接到苏沫的委托，调查她姐姐苏棠的失踪案。警方判定为普通失踪，但苏沫坚持认为事有蹊跷。",
    "characters":["陆征","苏沫"]
  },
  "memo":{
    "payoff_plan":{"must_resolve":[],"must_hold":["灰短袖的身份"]},
    "required_changes":["陆征从观望转为正式介入调查"],
    "prohibitions":["不要过早揭示灰短袖的身份"]
  },
  "emotional_design":{
    "primary_mood":"好奇"
  },
  "plot_items":[
    "苏沫推门进办公室，把一沓照片放在陆征桌上。",
    "陆征翻看案卷，注意到照片背景里那个模糊的灰色人影。",
    "他独自去苏棠最后住的公寓，在床垫下摸到一张揉皱的物流单。",
    "回程路上后视镜里的灰色面包车亮了一下雾灯又关掉。"
  ],
  "challenge":"警方已按普通失踪结案，没人愿意重开",
  "plot_stage":"开局铺垫",
  "ladder_exit":"物流单上写着老马，面包车跟在后面",
  "micro_payoffs":[{"kind":"clue","description":"床垫下的物流单"}],
  "word_target":2500
}'
curl -sf -X PUT "$BASE/api/projects/$PROJ_ID/chapters/vol-1-ch-1" \
  -H "Content-Type: application/json" \
  -H "$AUTH" \
  -d "$CHAPTER_DATA" | python3 -m json.tool

echo ""
echo "=== 6. 确认章节（触发 gate 检查） ==="
curl -sf -X POST "$BASE/api/projects/$PROJ_ID/chapters/vol-1-ch-1/confirm" \
  -H "$AUTH" | python3 -m json.tool

echo ""
echo "=== 7. 生成提示词 ==="
curl -sf -X POST "$BASE/api/projects/$PROJ_ID/chapters/vol-1-ch-1/prompts/generate" \
  -H "$AUTH" | python3 -m json.tool

echo ""
echo "=== 8. 查看生成的提示词文件 ==="
curl -sf "$BASE/api/projects/$PROJ_ID/chapters/vol-1-ch-1/prompts" \
  -H "$AUTH" | python3 -m json.tool

echo ""
echo "=== 9. 查看第一个提示词内容（前 500 字符） ==="
curl -sf "$BASE/api/projects/$PROJ_ID/chapters/vol-1-ch-1/prompts/seg-1" \
  -H "$AUTH" | head -c 500

echo ""
echo ""
echo "=== 端到端测试完成 ==="
echo "项目: http://localhost:3000/project/$SLUG"
echo "写作: curl $BASE/api/projects/$PROJ_ID/chapters/vol-1-ch-1/write/stream/1 -H '$AUTH'"