import json, pathlib, re, sqlite3, difflib, time
import httpx
from cryptography.fernet import Fernet

ROOT = pathlib.Path('/Users/modoojunko/Desktop/coding/ai-novel')
DD = ROOT / '.docker-data/client'
OUT = pathlib.Path('/tmp/vp/exp/out'); OUT.mkdir(parents=True, exist_ok=True)
M = json.loads(pathlib.Path('/tmp/vp/exp/material.json').read_text())

# ── 密钥：只解密使用，不打印 ──
# key-crypto-selfcontained：钥匙已迁入库 app_meta.fernet_key 行；本脚本兼容
# 两种来源——优先读库行，旧数据目录（无钥匙行）回退 .fernet_key 文件遗留。
db = sqlite3.connect('file:' + str(DD / 'novel.db') + '?mode=ro', uri=True); db.row_factory = sqlite3.Row
row = db.execute("select api_key, base_url from api_configs where vendor='deepseek'").fetchone()
def _load_key():
    try:
        kr = db.execute("select value from app_meta where key='fernet_key'").fetchone()
        if kr:
            return kr[0].strip()
    except sqlite3.Error:
        pass
    return (DD / '.fernet_key').read_text().strip()
fk = _load_key()
tok = row['api_key']
KEY = Fernet(fk).decrypt(tok[4:].encode()).decode() if tok.startswith('enc:') else tok
BASE = row['base_url'].rstrip('/')          # https://api.deepseek.com/anthropic
MODEL = db.execute('select ai_model from novels').fetchone()[0]

E = M['ending']
def call(prompt, temperature, max_tokens):
    # 照应用 ai_client.py 的口径：判定/短答复类调用默认关闭思考，被端点拒绝则去掉重试
    t0 = time.time()
    body = {'model': MODEL, 'max_tokens': max_tokens, 'temperature': temperature,
            'thinking': {'type': 'disabled'},
            'messages': [{'role': 'user', 'content': prompt}]}
    r = httpx.post(BASE + '/v1/messages',
        headers={'x-api-key': KEY, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'},
        json=body, timeout=180)
    if r.status_code >= 400 and 'thinking' in r.text.lower():
        body.pop('thinking', None)
        r = httpx.post(BASE + '/v1/messages',
            headers={'x-api-key': KEY, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'},
            json=body, timeout=180)
    r.raise_for_status()
    j = r.json()
    txt = ''
    for blk in j.get('content', []):
        if blk.get('type') == 'text' and blk.get('text'):
            txt += blk['text']
    return txt, j.get('usage', {}), round(time.time() - t0, 1)

def parse_json(txt):
    t = txt.strip()
    t = re.sub(r'^```(?:json)?|```$', '', t, flags=re.M).strip()
    i, k = t.find('{'), t.rfind('}')
    if i >= 0 and k > i: t = t[i:k+1]
    try: return json.loads(t), None
    except Exception as e: return None, str(e)

# ── 三份提示词 ──
P_OPTIONS = f"""你是长篇小说的结构顾问。已知这本书的整体设定与上一卷的结尾，给这一卷 3 套可行走法，供作者选择。

【全书主线】{M['fullstory']}
【结局（作者写的）】最后一幕：{E['scene']}｜主角变成：{E['hero']}｜读者感觉：{E['tone']}
【世界观摘要】{M['world_brief']}
【核心人物】{M['cast_brief']}
【上一卷的结尾】（这是第一卷，还没有上一卷；从主线开头的处境起步）
【作者这一卷的想法】（空——作者还没有想法）
【题材与节奏】{M['genre']}；单卷约 40 章

硬规则：
1. 三套都必须忠于上面的主线、世界观、核心人物与结局：都要接得上【上一卷的结尾】，都要让故事朝【结局】推近。
2. 差异只允许落在三处：中间的走向、冲突（谁在拦、对抗什么）、侧重点（代价／关系／认知／节奏…）。
3. 不得新增设定里没有的人物、势力、事件、地点；需要时用已有元素组合。
4. 三套必须在结构上真的不同——不是同一套的三种措辞。只想得出两套就给两套，并在 note 里说明为什么。
5. 作者写了想法时，每套都要说明「怎么执行这句话」。

每套四个字段：spine（一句话走向，≤40 字）｜conflict（一句话冲突，≤40 字）｜ending（这一卷收在哪里，必须能当下一卷的进场，≤40 字）｜focus（这一套相对另外两套的侧重，≤20 字）。

只输出 JSON，不要其他文字：
{{"plans":[{{"spine":"…","conflict":"…","ending":"…","focus":"…"}}],"note":"…"}}"""

AUTHOR_LINE = '林野为查身世，跟豢养派的旧贵族做交易拿情报，代价是替他们清掉一个叛徒'
P_EXPAND = f"""你是长篇小说的结构顾问。把作者对这一卷的一句话，铺成这一卷的卷纲。

【全书主线】{M['fullstory']}
【结局（作者写的）】最后一幕：{E['scene']}｜主角变成：{E['hero']}
【世界观摘要】{M['world_brief']}
【核心人物】{M['cast_brief']}
【上一卷的结尾】（第一卷，从主线开头的处境起步）
【作者这一卷的一句话】{AUTHOR_LINE}
【题材与节奏】{M['genre']}；单卷约 40 章
【伏笔台账（active）】
{M['hook_brief']}

硬规则（输出前逐条自查）：
1. 不凭空添人添事：只用上面出现过的人物、势力、事件、地点。
2. 接上上一卷的结尾，不跳空。
3. 核心矛盾是主线在这一阶段的子集，不另开一条线。
4. 卷末要给读者一个交代，并让局面朝结局更近一步（状态／关系／信息至少一类发生不可逆变化）。
5. 不跟设定打架：人物性格、世界规矩、已经埋下的伏笔。
6. 伏笔不重复埋、不提前揭；埋下的写清打算哪一卷收（引用台账编号，或写明「新埋」）。
7. 只铺结构，不改作者那句话——你与它有不一致的地方写进 checks，不要偷偷改。

字段上限：summary ≤80 字｜conflict ≤60｜goal ≤60｜ending ≤60｜plants ≤2 条｜reveals ≤2 条｜chapter_target 数字｜name ≤6 字（可从内容里长，允许留空）。
checks：0–3 条，只写你拿不准、或与作者那句话有张力的地方，每条 ≤40 字。

只输出 JSON，不要其他文字：
{{"name":"…","summary":"…","conflict":"…","goal":"…","ending":"…","plants":["…"],"reveals":["…"],"chapter_target":40,"checks":["…"]}}"""

P_CHECK_T = """你是校对结构的人，不是改写的人。只给判断与定位，不写改写文本。

【本卷卷纲】{vol}
【全书主线】{full}
【结局（作者写的）】{scene}
【世界观铁律】{rules}
【核心人物】{cast}
【伏笔台账（active）】
{hooks}
【已写内容（如有）】（还没写）

按三组逐条给结论，每条必须带证据（点名字段或台账条目）：
对主线：进场是否接得上上一卷的收尾｜这一卷要解决的事是否是主线走到这一步该解决的事｜卷末是否收束并朝结局推近
对设定：人物有没有空转或违背性格｜有没有违反世界铁律｜伏笔有没有重复埋、提前揭、漏收
对已写内容：实际写出来的和卷纲有没有出入（没有章节时输出一条 status=none 的占位）

status 只用三个值：ok／warn／none。每条 ≤45 字。不要给出改写后的句子，不要评价文笔。

只输出 JSON，不要其他文字：
{{"groups":[{{"name":"对主线","items":[{{"status":"warn","text":"…"}}]}}]}}"""

CJK = re.compile(r'[\u4e00-\u9fff]{2,4}')
def new_tokens(text, material):
    cnt = {}
    for t in CJK.findall(text):
        if t not in material:
            cnt[t] = cnt.get(t, 0) + 1
    return [t for t, c in sorted(cnt.items(), key=lambda x: -x[1]) if c >= 2][:8]

def report(name, runs):
    print(f'\n===== {name} =====')
    for i, (txt, usage, sec) in enumerate(runs, 1):
        obj, err = parse_json(txt)
        (OUT / f'{name}-{i}.txt').write_text(txt)
        print(f'--- run{i} | {sec}s | in {usage.get("input_tokens")} out {usage.get("output_tokens")} | JSON {"OK" if obj else "FAIL:" + str(err)[:40]}')
        if not obj:
            print('    原文前 200 字:', txt[:200].replace('\n', ' '))
            continue
        if name == 'options':
            ps = obj.get('plans', [])
            spines = [p.get('spine', '') for p in ps]
            sims = [round(difflib.SequenceMatcher(None, a, b).ratio(), 2)
                    for a, b in zip(spines, spines[1:])] if len(spines) > 1 else []
            print(f'    套数={len(ps)} | focus={[p.get("focus","")[:12] for p in ps]} | focus去重={len({p.get("focus","") for p in ps})}')
            print(f'    spine 两两相似度={sims} | 每套 ending 非空={all(p.get("ending") for p in ps)}')
            print('    疑似新造名词:', new_tokens(txt, MATERIAL_TEXT) or '无')
            for p in ps: print(f'      · {p.get("spine","")} ｜ {p.get("focus","")}')
        elif name == 'expand':
            lim = {'summary': 80, 'conflict': 60, 'goal': 60, 'ending': 60}
            print('    字段长度:', {k: len(str(obj.get(k, ''))) for k in lim}, '| 上限', lim)
            print(f'    plants={len(obj.get("plants", []))} reveals={len(obj.get("reveals", []))} chapter_target={obj.get("chapter_target")} name={obj.get("name")}')
            print('    checks:', obj.get('checks'))
            print('    是否改掉作者那句（关键要素命中）:',
                  '交易' in str(obj) and '叛徒' in str(obj), '| 卷入交易:', '豢养' in str(obj) or '旧贵族' in str(obj))
            print('    疑似新造名词:', new_tokens(txt, MATERIAL_TEXT) or '无')
        else:
            groups = obj.get('groups', [])
            print('    组数:', len(groups), [g.get('name') for g in groups])
            st = [it.get('status') for g in groups for it in g.get('items', [])]
            print('    status 分布:', {s: st.count(s) for s in set(st)}, '| 总条数', len(st))
            long_items = [it['text'] for g in groups for it in g.get('items', []) if len(it.get('text', '')) > 45]
            print('    超 45 字的条目:', len(long_items), long_items[:2])
            ghost = re.findall(r'(改为|建议写|可以写成|应该写成)', txt)
            print('    代笔迹象:', ghost or '无')

MATERIAL_TEXT = M['fullstory'] + M['world_brief'] + M['cast_brief'] + M['hook_brief'] + E['scene'] + E['hero'] + M['synopsis'] + AUTHOR_LINE

runs_opt = [call(P_OPTIONS, 0.7, 2000) for _ in range(2)]
report('options', runs_opt)

runs_exp = [call(P_EXPAND, 0.4, 2000) for _ in range(2)]
report('expand', runs_exp)

vol = parse_json(runs_exp[0][0])[0]
vol_txt = json.dumps({k: v for k, v in vol.items() if k != 'checks'}, ensure_ascii=False) if vol else '(解析失败)'
P_CHECK = P_CHECK_T.format(vol=vol_txt, full=M['fullstory'][:600], scene=E['scene'],
                           rules=M['world_brief'][-300:], cast=M['cast_brief'], hooks=M['hook_brief'])
runs_chk = [call(P_CHECK, 0.2, 2000) for _ in range(2)]
report('check', runs_chk)
print('\n原始输出已存 /tmp/vp/exp/out/')
