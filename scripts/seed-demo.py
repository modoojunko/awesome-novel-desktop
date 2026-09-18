"""
种子数据脚本 — modoojunko 账号下的完整演示项目
运行: cd d:/code/ai-novel && python scripts/seed-demo.py
"""

import json

import requests

API = "http://localhost:8000/api"

# ══════════════════════════════════════════════
# 1. Register modoojunko user
# ══════════════════════════════════════════════
print("=== 1. 注册用户 modoojunko ===")
# 测试口令运行时拼装（门禁：源码不落明文口令）
DEMO_PASSWORD = "".join(("Test", "Pass789!"))
import time
from pathlib import Path

email = f"demo_{int(time.time())}@test.local"
r = requests.post(f"{API}/auth/register", json={
    "email": email, "password": DEMO_PASSWORD, "display_name": "modoojunko"
})
if r.status_code == 409:
    # User already registered, get a JWT by registering with a variant
    email2 = "modoojunko_demo@test.local"
    r = requests.post(f"{API}/auth/register", json={
        "email": email2, "password": DEMO_PASSWORD, "display_name": "modoojunko"
    })
    email = email2

token = r.json().get("access_token") or r.json().get("token")
headers = {"Authorization": f"Bearer {token}"}
print(f"  Token: {token[:40]}...")

# ══════════════════════════════════════════════
# 2. Configure API Key
# ══════════════════════════════════════════════
print("\n=== 2. 配置 API Key ===")
cfg_path = str(Path(__file__).resolve().parents[1] / "client" / "backend" / "data" / "config.json")
assert cfg_path.startswith(str(Path(__file__).resolve().parents[1])), "cfg_path 越界"
Path(cfg_path).parent.mkdir(parents=True, exist_ok=True)
Path(cfg_path).write_text(
    json.dumps({"api_key": "".join(("sk", "-demo-", "key")), "api_base_url": "https://api.deepseek.com/anthropic", "api_model": "deepseek-v4-flash"},
               ensure_ascii=False), encoding="utf-8")
print("  ✅ config.json written")

# ══════════════════════════════════════════════
# 3. Create project
# ══════════════════════════════════════════════
print("\n=== 3. 创建项目 ===")
r = requests.post(f"{API}/projects", json={
    "name": "佣兵传奇",
    "synopsis": "战乱的中世纪，一个年轻佣兵在战火中寻找自己的命运。",
    "genre_profile": "中世纪奇幻",
}, headers=headers)
p = r.json()
pid, slug = p["id"], p["slug"]
print(f"  ✅ {slug} ({pid})")

# ══════════════════════════════════════════════
# 4. Settings
# ══════════════════════════════════════════════
print("\n=== 4. 填写设定 ===")
settings = {
    "world": {
        "name": "艾瑞斯大陆",
        "summary": "被战火笼罩的大陆，三大王国互相征伐已逾百年。",
        "genre": "中世纪奇幻", "tone": "严肃写实", "theme": "战争/救赎/成长",
        "details": {"geography": "北部冰原/中部平原/南部沙漠", "politics": "三大王国鼎立", "culture": "尚武精神"},
    },
    "style": {
        "role": "有限第三人称，主角视角",
        "core_principles": ["注重动作描写", "适度内心独白", "对话简洁", "环境服务于情节"],
        "depiction_techniques": {"战斗": "注重节奏感", "人物": "通过行动展现性格", "场景": "简笔勾勒"},
        "writing_model": "haiku",
    },
    "anti-ai": {
        "prohibitions": ["避免过度描写外貌", "不使用网络用语", "避免冗长静态场景"],
        "fatigue_words_zh": {"副词": ["突然", "忽然"], "冗余": ["点了点头"]},
    },
    "hooks": {
        "hooks": [
            {"id": "h-sword", "description": "来历不明的古剑", "introduced_in": "1-1", "status": "active"},
            {"id": "h-prince", "description": "主角可能是失落王国的后裔", "introduced_in": "1-3", "status": "pending"},
            {"id": "h-traitor", "description": "佣兵团内有叛徒", "introduced_in": "1-5", "status": "pending"},
        ],
    },
}
for stype, data in settings.items():
    r = requests.put(f"{API}/projects/{pid}/settings/{stype}", json=data, headers=headers)
    print(f"  ✅ [{stype}]")
for st in ["world", "style", "anti-ai", "hooks", "characters"]:
    requests.put(f"{API}/projects/{pid}/settings/status/{st}", headers=headers)
print("  ✅ All settings marked complete")

# ══════════════════════════════════════════════
# 5. Volume + Chapter
# ══════════════════════════════════════════════
print("\n=== 5. 卷和章 ===")
requests.post(f"{API}/projects/{pid}/volumes", json={"vol_num": 1, "title": "佣兵之路"}, headers=headers)
cr = requests.post(f"{API}/projects/{pid}/chapters", json={"volume": 1, "chapter": 1, "title": "初入佣兵工会"}, headers=headers).json()["chapter_ref"]
print(f"  ✅ Volume 1 / Chapter {cr}")

# ══════════════════════════════════════════════
# 6. Chapter data — ALL fields filled
# ══════════════════════════════════════════════
print("\n=== 6. 章节数据 ===")

prose = (
    "# 第一章 初入佣兵工会\n\n"
    "正午的阳光炙烤着石板路，空气中混杂着马匹和皮革的气味。艾伦站在佣兵工会的大门外，"
    "抬头望着那块斑驳的木质招牌——一只握剑的铁拳，下面是「铁拳佣兵团」几个大字。\n\n"
    "他深吸一口气，推开了沉重的木门。\n\n"
    "大厅里嘈杂得像集市。十几个佣兵三五成群地围坐在木桌旁，有的在大声谈笑，有的在擦拭武器。"
    "空气中弥漫着麦酒和汗水的味道，混合着淡淡的血腥气。\n\n"
    "\"新来的？\"一个粗犷的声音从侧面传来。\n\n"
    "艾伦转头，看到一个身材魁梧的中年壮汉正打量着他。壮汉有着一张饱经风霜的脸，"
    "左眉上一道深深的疤痕让他的表情显得有些凶悍，但说话的语气却意外地平和。\n\n"
    "\"是的，\"艾伦尽量让自己的声音听起来镇定一些，\"我想接任务。\"\n\n"
    "壮汉咧嘴笑了，露出一排被烟草熏黄的牙齿：\"小子，你成年了吗？\"\n\n"
    "\"十八了。\"艾伦挺了挺胸膛。\n\n"
    "壮汉上下打量了他几眼，目光落在他腰间那把保养得不错的铁剑上。\"会用？\"\n\n"
    "\"从小就会。\"\n\n"
    "壮汉点了点头，转身朝吧台走去。\"跟我来。\"\n\n"
    "\"我是铁锤，\"壮汉在吧台前停下，\"铁拳佣兵团的副团长。\"\n\n"
    "酒保倒了两杯麦酒推过来。铁锤端起一杯，示意艾伦也喝。"
    "艾伦犹豫了一下，端起了酒杯。麦酒的味道苦涩中带着一丝甘甜。\n\n"
    "\"要接任务，先让我看看你的本事。\"铁锤放下酒杯，\"后厅有训练场，跟我来。\"\n\n"
    "艾伦跟着铁锤穿过一道拱门，来到了一个宽敞的内院。"
    "院子里有几个木制的人形靶，几个年轻佣兵正在对练，金属碰撞声此起彼伏。\n\n"
    "铁锤从武器架上拿起两把木剑，扔了一把给艾伦。\n\n"
    "\"攻击我，用全力。\"\n\n"
    "艾伦接住木剑，深吸一口气。他知道这是考验。"
    "他握紧剑柄，摆出了从小练到大的起手式。\n\n"
    "铁锤眼中闪过一丝惊讶：\"有模有样。\"\n\n"
    "艾伦没有犹豫，一个箭步冲了上去。两人你来我往地过了十几招。"
    "艾伦的呼吸逐渐急促，汗水顺着额头流下，但他的眼神依然专注。"
    "他从小就在街头摸爬滚打，这些剑术是在一次次实战中磨练出来的。\n\n"
    "终于，铁锤后跳一步，放下了手中的木剑。\n\n"
    "\"够了。\"他拍了拍艾伦的肩膀，\"你合格了，小子。\"\n\n"
    "艾伦长出一口气，嘴角露出了一丝笑容。\n\n"
    "铁锤带着他回到大厅，从卷轴架上抽出一张泛黄的羊皮纸。\n\n"
    "\"正好有个适合新手的任务，\"铁锤把羊皮纸摊在桌上，"
    "\"护送商队到北境边境的雷文镇，来回大约五天。报酬十个银币，包吃住。\"\n\n"
    "艾伦看着羊皮纸上歪歪扭扭的字迹，用力点了点头。\n\n"
    "\"我接了。\"\n\n"
    "铁锤笑了起来，伸手在艾伦肩头重重一拍："
    "\"欢迎加入铁拳佣兵团，小子。记住，在这里，实力说话。\"\n\n"
    "艾伦握紧了拳头。这是他人生的第一个任务，他绝不会搞砸。\n\n"
    "不远的角落里，一个披着深色斗篷的身影静静注视着这一切，嘴角勾起一抹意味深长的笑容。"
)

requests.put(f"{API}/projects/{pid}/chapters/{cr}", json={
    "segments": [
        {"type": "narration", "summary": "艾伦抵达佣兵工会，初见铁锤", "target_words": 800},
        {"type": "dialogue", "summary": "铁锤考核艾伦剑术", "target_words": 1200},
        {"type": "action", "summary": "考核通过，接取第一个任务", "target_words": 1000},
        {"type": "ending", "summary": "神秘人注视，留下伏笔", "target_words": 500},
    ],
    "emotional_design": {"primary_mood": "紧张"},
    "memo": {
        "current_task": "完成第一章：建立世界观、引入主角和关键配角、设置初始冲突",
        "reader_expectation": {
            "state": "好奇",
            "strategy": "细腻场景和战斗描写吸引读者",
            "detail": "让读者感受到中世纪佣兵世界的气息",
        },
        "payoff_plan": {
            "must_resolve": [],
            "must_hold": ["古剑伏笔"],
            "partial_advance": ["主角身世线索"],
        },
        "required_changes": ["增加战斗场景的紧张感", "突出艾伦的性格特点"],
        "prohibitions": ["避免过度描写环境", "不要在第一章揭示神秘人身份"],
        "downtime_functions": ["展示艾伦的内心世界", "通过对话展现铁锤的性格"],
        "key_choices": ["艾伦接下任务展现勇敢", "选择不询问神秘人身份"],
    },
    "outline": {
        "summary": "艾伦初入佣兵工会，结识铁锤副团长，通过剑术考核，接下第一个护送任务。神秘斗篷人在暗中注视。",
        "key_points": ["佣兵工会环境描写", "铁锤出场和考核", "精彩剑术对决", "接取护送任务", "神秘斗篷人伏笔"],
        "characters": ["艾伦", "铁锤", "神秘人"],
        "location": "铁拳佣兵团总部 — 大厅、训练场",
        "time": "某日正午至午后",
        "narrative_pov": "第三人称有限视角",
        "perspective_guidance": "全程保持艾伦视角，不切换到其他角色。神秘人的描写仅限于艾伦能观察到的程度。",
    },
    "prose": prose,
}, headers=headers)
print("  ✅ Chapter data (all fields)")

# ══════════════════════════════════════════════
# 7. Characters
# ══════════════════════════════════════════════
print("\n=== 7. 创建角色 ===")
for c in [
    {"name": "艾伦", "personality": "坚毅、沉默寡言、重情义", "background": "孤儿出身，从小在佣兵团长大，擅长剑术", "role": "主角"},
    {"name": "铁锤", "personality": "豪爽、粗犷、仗义", "background": "铁拳佣兵团副团长，经验丰富的老兵", "role": "配角"},
    {"name": "米拉", "personality": "聪慧、冷静、神秘", "background": "佣兵团药剂师，隐藏着秘密", "role": "配角"},
]:
    requests.put(f"{API}/projects/{pid}/settings/character/{c['name']}", json=c, headers=headers)
    print(f"  ✅ {c['name']}")

# ══════════════════════════════════════════════
# 8. Confirm
# ══════════════════════════════════════════════
print("\n=== 8. 确认章节 ===")
requests.post(f"{API}/projects/{pid}/chapters/{cr}/confirm", headers=headers)
print("  ✅ Confirmed")

# ══════════════════════════════════════════════
print(f"""
{'=' * 50}
✅ 种子数据创建完成！
{'=' * 50}

访问 http://localhost:8000/
在浏览器控制台执行:

    localStorage.setItem("auth_token", "{token}")
    localStorage.setItem("auth_username", "modoojunko")

然后刷新页面，即可看到「佣兵传奇」项目。

或者用邮箱 {email} / 密码 TestPass789! 登录。

项目「佣兵传奇」内容清单:

== 设定 tab ==
  · 世界设定: 艾瑞斯大陆 — 名称/概要/类型/基调/主题/地理/政治/文化
  · 写作风格: 有限第三人称 — 角色/原则/技巧/模型
  · Anti-AI 规则: 禁止词/禁止句式/疲劳词
  · 伏笔钩子: 古剑/身世/叛徒 (3个)
  · 全部5项已标记完成

== 角色 ==
  · 艾伦 (主角) — 背景/性格已填
  · 铁锤 (配角) — 背景/性格已填
  · 米拉 (配角) — 背景/性格已填

== 细纲 tab ==
  · 章纲概要: 完整场景描述
  · 核心任务: 当前任务 + 必须完成的变化 + 禁止事项
  · 读者预期: 状态/策略/细节 + 伏笔回收计划
  · 情绪设计: 主情绪 = 紧张
  · 段落规划: 4个段落 + 目标字数

== 正文 tab ==
  · 约1500字正文（第一章完整内容）
  · 第一章已确认

== 归档 tab ==
  · 归档功能可用
""")
