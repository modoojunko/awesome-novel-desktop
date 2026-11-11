import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate, useSearchParams } from "react-router-dom";
import { kbApi, type KbChainSeg, type KbEntry, type KbGenreCount, type KbInstanceFlatRow } from "@/lib/kbApi";
import {
  claimKbProbe,
  getLastKbProbe,
  openKbSyncModal,
  readKbDismissal,
  releaseKbProbe,
  setLastKbProbe,
} from "@/lib/kbProbe";
import KnowledgeTreePanel from "@/components/tools/KnowledgeTreePanel";
import { kbFieldDesc, kbFieldLabel, kbValueLabel } from "@/lib/kbFieldLabels";
import KbEntryRelations from "@/components/tools/KbEntryRelations";
import KbMaterialCard from "@/components/tools/KbMaterialCard";

const CONCEPTS = ["文风", "文笔", "世界设定", "角色设定", "手法", "情节"] as const;
const CONCEPT_DESC: Record<string, string> = {
  文风: "这本书的整体声音",
  文笔: "具体句子的写法",
  世界设定: "舞台、力量、势力、铁律",
  角色设定: "造好的角色，一人一条",
  手法: "写每一章时的场面打法",
  情节: "即将上线",
};

/** 深链合法值（?concept= 只认六概念；非法/缺省落「全部」）。 */
function conceptFromQuery(v: string | null): string {
  return v && (CONCEPTS as readonly string[]).includes(v) ? v : "全部";
}

/** 通用载荷平铺（概念无关，规格「条目详情抽屉：字段…」实现）：有值键按存储序出
 * (键, 展示串)；数组顿号连、对象/数组元素套对象走紧凑 JSON、空值跳过；标量值
 * 走 kbValueLabel（枚举值/布尔转中文）。 */
/** 实例字段值渲染：repr 列表顿号连（总结历史产物有单引号形态）；其余原样。 */
export function prettyFieldValue(raw: string): string {
  const t = (raw || "").trim();
  if (!t) return "";
  try {
    const j = JSON.parse(t);
    if (Array.isArray(j)) return j.map(String).join("、");
    if (typeof j === "string") return j;
    return t;
  } catch { /* 非 JSON 原样 */ }
  if (t.startsWith("[") && t.endsWith("]")) {
    try {
      const a = JSON.parse(t.replace(/'/g, '"'));
      if (Array.isArray(a)) return a.map(String).join("、");
    } catch { /* repr 解析失败原样 */ }
  }
  return t;
}

/** 实例 → 有值字段 (标签, 渲染值)；fields_json 畸形返空。
 *  渲染序：所属知识点的字段模板序（知识对象定义实例的格）在前，
 *  模板没有的键退概念字典兜底；两处都没有的按原序尾随。
 *  与实例正文同值的字段不重复显示（boss 2026-11-11 真机实锤：官方条目 payload
 *  历史上带「名字：怎么写」拼装份，详情页 实例/内容/怎么写 三字段同值——
 *  SDK 已停写拼装份，此处句末归一兜底挡存量包与残存形态）。
 *  角色卡逐字段原句证据（payload.field_quotes）：有则作为第三元挂在字段行上，
 *  不单独成行（字段名与档案八格同名）；字段无可核原句时如实不显示。 */
export function fieldsOf(row: KbInstanceFlatRow): [string, string, string?][] {
  if (row.row_kind !== "instance") return [];
  let fields: Record<string, unknown> = {};
  try { fields = JSON.parse(row.fields_json || "{}") ?? {}; } catch { fields = {}; }
  if (typeof fields !== "object" || Array.isArray(fields)) return [];
  const render = (v: unknown) => (typeof v === "string" ? prettyFieldValue(v) : Array.isArray(v) ? v.map(String).join("、") : String(v));
  const norm = (s: string) => s.trim().replace(/。+$/, "");
  const bodyNorm = norm(row.text || "");
  const out: [string, string, string?][] = [];
  const used = new Set<string>();
  // 逐字段原句证据（boss 2026-11-11）：{字段: 原句}；不是可渲染字段本身
  const fqRaw = (fields as Record<string, unknown>).field_quotes;
  const fieldQuotes: Record<string, string> = {};
  if (fqRaw && typeof fqRaw === "object" && !Array.isArray(fqRaw)) {
    for (const [k, v] of Object.entries(fqRaw as Record<string, unknown>)) {
      if (typeof v === "string" && v.trim()) fieldQuotes[k] = v.trim();
    }
  }
  const withQuote = (name: string, label: string, value: string): [string, string, string?] =>
    fieldQuotes[name] ? [label, value, fieldQuotes[name]] : [label, value];
  let schema: { name?: unknown; desc?: unknown }[] = [];
  try { schema = JSON.parse(row.knowledge_schema_json || "[]") ?? []; } catch { schema = []; }
  if (Array.isArray(schema)) {
    for (const s of schema) {
      const slotName = typeof s?.name === "string" ? s.name : "";
      if (!slotName || !(slotName in fields)) continue;
      const rendered = render(fields[slotName]);
      if (!rendered) continue;
      used.add(slotName);
      if (bodyNorm !== "" && norm(rendered) === bodyNorm) continue;
      out.push(withQuote(slotName, slotName, rendered));
    }
  }
  for (const [k, v] of Object.entries(fields)) {
    if (used.has(k)) continue;
    if (k === "field_quotes") continue;
    const rendered = render(v);
    if (!rendered) continue;
    if (bodyNorm !== "" && norm(rendered) === bodyNorm) continue;
    out.push(withQuote(k, kbFieldLabel(row.concept, k), rendered));
  }
  return out;
}

export function payloadRows(payload: Record<string, unknown>): [string, string][] {
  const rows: [string, string][] = [];
  for (const [k, v] of Object.entries(payload)) {
    if (v === null || v === undefined || v === "") continue;
    if (Array.isArray(v)) {
      if (v.length) {
        rows.push([k, v.map((x) => (typeof x === "object" && x !== null ? JSON.stringify(x) : String(x))).join("、")]);
      }
      continue;
    }
    if (typeof v === "object") {
      rows.push([k, JSON.stringify(v)]);
      continue;
    }
    rows.push([k, kbValueLabel(k, v)]);
  }
  return rows;
}

// 来源筛选（boss 2026-11-08：我们自己就是官方——官方内容即普通来源，无特权臂）：
// 全部＝我的实例＋官方合并；官方/拆书/手录＝按来源过滤。已隐藏臂退役（后端 hide 覆盖层保留，
// 同步不再复活已归档条目——分发机制不因界面统一而变）
const SOURCE_FILTERS = [
  { key: "全部", label: "全部来源" },
  { key: "官方", label: "官方" },
  { key: "拆书", label: "拆书" },
  { key: "手录", label: "手录" },
] as const;

export default function KnowledgeBasePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [genre, setGenre] = useState("全部题材");
  // ?concept= 深链（c-charlib-into-kb）：/tools/characters 重定向落位用；消费后即清，
  // URL 回到干净态（页签选择本身不进 URL，刷新回「全部」是预期）。
  const [concept, setConcept] = useState(() => conceptFromQuery(searchParams.get("concept")));
  // 视图支持 ?view=tree 直达（提炼任务详情「去知识树看变化」跳转；评审 2026-11-09）
  const [view, setView] = useState<"list" | "tree">(() => (searchParams.get("view") === "tree" ? "tree" : "list"));
  const [src, setSrc] = useState("全部");
  const [q, setQ] = useState("");
  const [entries, setEntries] = useState<KbEntry[]>([]);
  const [genreCounts, setGenreCounts] = useState<KbGenreCount[]>([]);
  // 实例行列表（c-kb-instance-list）：实例侧来源的数据源；官方精选/已隐藏两臂回知识行列表
  const [flatRows, setFlatRows] = useState<KbInstanceFlatRow[]>([]);
  const [flatLoading, setFlatLoading] = useState(false);
  const [sort, setSort] = useState<"recent" | "name">("recent");
  const [selected, setSelected] = useState<KbEntry | null>(null);
  // 实例详情（boss 2026-11-07 拍板：知识库看的是每条实例具体详情，归属知识点是它的属性）
  const [selectedInstance, setSelectedInstance] = useState<KbInstanceFlatRow | null>(null);
  // 原句证据默认折叠（c-deconstruct-compliance-guard）：按字段名展开，换实例复位
  const [quoteOpen, setQuoteOpen] = useState<Set<string>>(new Set());
  useEffect(() => {
    setQuoteOpen(new Set());
  }, [selectedInstance?.id]);
  const [showManual, setShowManual] = useState(false);
  const [manualText, setManualText] = useState("");
  const [manualGenre, setManualGenre] = useState("");
  const [manualError, setManualError] = useState("");
  const [manualNote, setManualNote] = useState("");
  const [manualConcept, setManualConcept] = useState("手法");
  const [instRows, setInstRows] = useState<{ id: string; text: string; fields: Record<string, string>; source_novel: string; quote: string }[]>([]);
  const [showMoreGenres, setShowMoreGenres] = useState(false);
  const [opBusy, setOpBusy] = useState(false);
  const [opNote, setOpNote] = useState("");
  // 知识提炼（原型定稿 2026-11-08）：单按钮 → 确认弹窗 → 任务进任务清单后台执行
  const [showRefineConfirm, setShowRefineConfirm] = useState(false);
  const [refineBusy, setRefineBusy] = useState(false);
  // 「全部题材」页签下提炼需要先选题材（后端按题材建任务；评审 P2：空串必 422）
  const [refineGenre, setRefineGenre] = useState("");
  const [toast, setToast] = useState<{ text: string; link?: { label: string; to: string } } | null>(null);
  const navigate = useNavigate();
  // 实例臂点行取数失败的列表区提示（独立于 opNote——那是回退臂抽屉操作文案，不得跨臂滞留）
  const [openError, setOpenError] = useState("");
  // 官方知识探测结果（c-kb-baseline-update-ux）：页头入口显示版本号；
  // null＝本页尚未探测过（入口仍可点，弹窗内自查）
  const [kbProbe, setKbProbe] = useState(getLastKbProbe());

  // 官方知识更新探测（c-kb-baseline-update-ux）：进页静默探测一次（照书架
  // 提示词探测先例，claim 去重）；有新版且未被「暂不更新」锚压制→自动弹
  // 更新窗；其余（无更新/探测失败）全静默。
  useEffect(() => {
    if (!claimKbProbe()) return;
    void (async () => {
      try {
        const p = await kbApi.baselineProbe();
        setLastKbProbe(p);
        setKbProbe(p);
        if (p.update_available && readKbDismissal().updateVersion !== String(p.latest)) {
          openKbSyncModal({ mode: "update", from: p.installed, to: p.latest });
        }
      } catch {
        /* 探测失败＝无更新静默 */
      } finally {
        releaseKbProbe();
      }
    })();
  }, []);

  // 官方条目常取（boss 2026-11-08：无特权臂——官方与自有实例合并单列表）；
  // 原始 KbEntry 留存供抽屉「关联知识」本地查找与映射
  const loadOfficial = useCallback(async () => {
    try {
      const sp = new URLSearchParams();
      sp.set("src", "官方精选");
      if (genre !== "全部题材") sp.set("genre", genre);
      if (concept !== "全部") sp.set("concept", concept);
      if (q) sp.set("q", q);
      sp.set("limit", "200");
      const r = await kbApi.entries(Object.fromEntries(sp));
      setEntries(r.entries);
    } catch { setEntries([]); }
  }, [genre, concept, q]);



  const loadFlat = useCallback(async () => {
    setFlatLoading(true);
    setOpenError(""); // 重取即清——旧失败提示不跨筛选滞留
    try {
      const sp = new URLSearchParams();
      // 「跨题材通用」档（genre=''）不发参数——由前端按行过滤（现 /entries 链路该档是
      // no-op，不照抄）；genre/concept/q 过滤语义与 list_entries 同口径
      if (genre !== "全部题材" && genre !== "") sp.set("genre", genre);
      if (concept !== "全部") sp.set("concept", concept);
      if (q) sp.set("q", q);
      const r = await kbApi.instancesFlat(Object.fromEntries(sp));
      setFlatRows(r.rows);
    } catch {
      setFlatRows([]);
    } finally { setFlatLoading(false); }
  }, [genre, concept, q]);

  // 实例臂客户端过滤与排序（数据全量在内存）：来源（拆书/手录）按行 src_kind、
  // 「跨题材通用」档只留 genre==='' 行；名称排序按所属知识名、素材行恒排末位
  // 回退臂（官方精选/已隐藏）条目同映射为实例行（官方条目也是实例——boss 模型
  // 口径 2026-11-07：知识库所有维度都是实例行；分层只是查看方式）
  // 官方条目 → 统一实例行（官方即普通来源——无特权臂、无特殊抽屉段）
  const mapOfficialRows = useCallback((list: KbEntry[]): KbInstanceFlatRow[] => list.map((e) => ({
    row_kind: "instance" as const,
    id: e.id,
    knowledge_id: e.id,
    knowledge_title: e.title || e.instruction.slice(0, 20),
    chain: [] as KbChainSeg[],
    genre: e.genre,
    concept: e.concept,
    text: e.instruction,
    quote: "",
    source_novel: e.src_novel_name || "",
    source_chapter: "",
    src_kind: "官方" as const,
    created_at: e.created_at || "",
    fields_json: "{}",
    name: e.title || "",
    official: true,
  })), []);
  const officialRows = useMemo(() => mapOfficialRows(entries), [entries, mapOfficialRows]);

  // 单列表合并：全部来源＝我的实例＋官方；官方/拆书/手录＝按来源过滤
  const visibleRows = useMemo(() => {
    let rows: KbInstanceFlatRow[];
    if (src === "官方") rows = officialRows;
    else if (src === "拆书") rows = flatRows.filter((r) => r.src_kind === "拆书");
    else if (src === "手录") rows = flatRows.filter((r) => r.src_kind === "手录");
    else rows = [...flatRows, ...officialRows];
    if (genre === "") rows = rows.filter((r) => r.genre === "");
    if (sort === "name") {
      rows = [...rows].sort((a, b) => {
        if (!a.knowledge_title) return 1;
        if (!b.knowledge_title) return -1;
        return a.knowledge_title.localeCompare(b.knowledge_title, "zh");
      });
    }
    return rows;
  }, [officialRows, flatRows, src, genre, sort]);

  // 计数行分类分布（与 N 同口径：含待归属素材行）
  const conceptBreakdown = useMemo(() => {
    const m = new Map<string, number>();
    visibleRows.forEach((r) => m.set(r.concept, (m.get(r.concept) ?? 0) + 1));
    return [...m.entries()];
  }, [visibleRows]);

  // 点行/点链取数（c-kb-instance-list D5）：行 id 不一概是 kb_entries id——
  // 实例行用 knowledge_id、素材行与链上级用行/链 id；统一走 entry() 兜底路径
  const openKnowledgeById = useCallback(async (id: string) => {
    try {
      const d = await kbApi.entry(id);
      setSelected(d);
      setSelectedInstance(null);
      setOpNote("");
      setOpenError("");
    } catch {
      // 抽屉没开成——提示须落在列表区才可见（opNote 在抽屉内的渲染面此时不可达）
      setOpenError("这条知识暂时打不开，稍后再试");
    }
  }, []);

  // 删素材/手录/基线操作后的当前臂刷新
  const reloadCurrent = useCallback(async () => {
    await Promise.all([loadFlat(), loadOfficial()]);
    kbApi.genres().then(setGenreCounts).catch(() => {});
  }, [loadFlat, loadOfficial]);

  useEffect(() => {
    kbApi.genres().then(setGenreCounts).catch(() => {});
  }, []);

  useEffect(() => {
    if (!searchParams.get("concept")) return;
    setSearchParams({}, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 只在挂载后消费一次深链参数
  }, []);

  useEffect(() => {
    void loadFlat();
    void loadOfficial();
  }, [genre, concept, src, q, loadFlat, loadOfficial]);

  const visibleGenres = useMemo(() => {
    const filled = genreCounts.filter((g) => g.count > 0);
    if (showMoreGenres) return filled;
    return filled.slice(0, 5);
  }, [genreCounts, showMoreGenres]);

  const moreCount = genreCounts.filter((g) => g.count > 0).length - visibleGenres.length;
  const showFoldToggle = moreCount > 0 || showMoreGenres;

  useEffect(() => {
    if (!selected) { setInstRows([]); return; }
    let alive = true;
    kbApi.listInstances(selected.id)
      .then((r) => {
        if (!alive) return;
        setInstRows(r.instances.map((x) => ({
          id: x.id,
          text: x.text,
          fields: (() => { try { return JSON.parse(x.fields_json || "{}") as Record<string, string>; } catch /* v8 ignore next — 畸形 fields_json UI 不可达（后端恒合法 JSON） */ { return {}; } })(),
          source_novel: x.source_novel,
          quote: x.quote || "",
        })));
      })
      .catch(() => { if (alive) setInstRows([]); });
    return () => { alive = false; };
  }, [selected]);

  const startRefineTask = async () => {
    if (refineBusy) return;
    const g = genre === "全部题材" ? refineGenre : genre;
    if (!g) return;
    setRefineBusy(true);
    try {
      await kbApi.refineTasks.create(g);
      setShowRefineConfirm(false);
      setToast({ text: "知识提炼任务已开始", link: { label: "查看任务", to: "/tools" } });
      /* v8 ignore next -- 定时消 toast 臂（jsdom 计时器时序，链接点击臂已测） */
      window.setTimeout(() => setToast(null), 5200);
      await reloadCurrent();
    } catch (e) {
      setShowRefineConfirm(false);
      setOpenError(e instanceof Error ? e.message : "任务创建失败，稍后再试");
    } finally {
      setRefineBusy(false);
    }
  };

  const handleDeleteMaterial = async () => {
    /* v8 ignore start -- 双保险早退：删除钮只挂在素材抽屉上（真机连点防护），UI 面走不到该早退 */
    if (!selected || selected.origin !== "material" || opBusy) return;
    /* v8 ignore stop */
    setOpBusy(true);
    setOpNote("");
    try {
      await kbApi.deleteEntry(selected.id);
      setSelected(null);
      await reloadCurrent();
    } catch (e: unknown) {
      setOpNote((e as { message?: string }).message || "删除失败");
    } finally {
      setOpBusy(false);
    }
  };

  const handleManual = async () => {
    setManualError("");
    /* v8 ignore start -- 手录表单校验三臂：空文本/空题材由表单交互覆盖（真机段） */
    if (!manualText.trim()) { setManualError("先写一条"); return; }
    if (!manualGenre) { setManualError("选一个题材"); return; }
    /* v8 ignore stop */
    try {
      await kbApi.createEntry({
        genre: manualGenre,
        concept: manualConcept,
        instruction: manualText,
      });
      setManualText("");
      setManualNote("素材已收录，总结后成为知识点");
      await reloadCurrent();
    } catch (e: unknown) {
      // ApiError：422 的 message = 后端第一条闸门错误（api.ts 不变量：4xx message 恒非空）
      const err = e as { message?: string };
      setManualError(err.message || "保存失败");
    }
  };

  return (
    // 版式对齐写作工具系各页（c-kb-header-align）：共用 .main 居中容器＋.page-head
    // 标题行（h1 30px/副标题 .sub/右侧动作），不再用整幅通栏大标题
    <main className="main" data-od-id="kb-home">
      <div className="page-head">
        <div>
          <h1>知识库</h1>
          <p className="sub">存的是拆书拆出的好写法和自己踩过的经验，写新书时能用上。</p>
        </div>
        <div className="flex flex-none items-center gap-2">
          <button
            data-testid="kb-baseline-entry"
            onClick={() => openKbSyncModal({ mode: "manual" })}
            className="rounded-md border border-[var(--border)] px-3 py-1.5 text-[12px] text-[var(--muted)] hover:text-[var(--fg)]"
          >
            官方知识{kbProbe?.installed ? ` v${kbProbe.installed}` : ""}
          </button>
          <button
            data-testid="kb-refine-btn"
            disabled={refineBusy}
            onClick={() => setShowRefineConfirm(true)}
            className="rounded-md border border-[var(--accent)] px-3 py-1.5 text-[12px] text-[var(--accent)] hover:bg-[var(--accent-soft)] disabled:opacity-50"
          >
            知识提炼
          </button>
          <div className="flex items-center gap-1 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-0.5">
            {(["list", "tree"] as const).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={`rounded-md px-3 py-1.5 text-[12px] ${view === v ? "bg-[var(--accent-soft)] font-medium text-[var(--accent)]" : "text-[var(--muted)] hover:text-[var(--fg)]"}`}
              >
                {v === "list" ? "列表" : "树"}
              </button>
            ))}
          </div>
        </div>
      </div>

        {showRefineConfirm && createPortal(
          <div className="fixed inset-0 z-50 flex items-center justify-center p-6">
            <div className="absolute inset-0 bg-black/50" onClick={() => setShowRefineConfirm(false)} />
            <div data-testid="kb-refine-modal" className="relative w-[520px] max-w-full max-h-[86vh] overflow-y-auto rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6 shadow-2xl">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-mono text-[10px] tracking-[0.12em] text-[var(--faint)]">
                    {genre === "全部题材" ? "全部题材 · 知识库" : `${genre} · 知识库`}
                  </p>
                  <h2 className="mt-1 font-[var(--font-display)] text-xl font-semibold text-[var(--fg)]">知识提炼</h2>
                  <p className="mt-1 text-[12.5px] text-[var(--muted)]">接下来 AI 会做两件事，确认后开始。</p>
                </div>
                <button onClick={() => setShowRefineConfirm(false)} className="text-[var(--faint)] hover:text-[var(--fg)]">✕</button>
              </div>
              {genre === "全部题材" && (
                <div className="mt-3 flex items-center gap-2" data-testid="kb-refine-genre-pick">
                  <span className="text-[12px] text-[var(--muted)]">提炼题材</span>
                  <select
                    value={refineGenre}
                    onChange={(e) => setRefineGenre(e.target.value)}
                    className="h-8 rounded-md border border-[var(--border)] bg-[var(--surface)] px-2 text-[12.5px] text-[var(--fg)]"
                  >
                    <option value="">选一个题材…</option>
                    {genreCounts.filter((x) => x.count > 0).map((x) => (
                      <option key={x.name} value={x.name}>{x.name}</option>
                    ))}
                  </select>
                </div>
              )}
              <div className="mt-4 rounded-xl border border-[var(--border)] p-4">
                <div className="flex gap-3">
                  <span className="grid h-6 w-6 flex-none place-items-center rounded-full bg-[var(--accent-soft)] text-[12px] font-semibold text-[var(--accent)]">1</span>
                  <div>
                    <h3 className="text-[13.5px] font-semibold text-[var(--fg)]">归类进树</h3>
                    <p className="mt-0.5 text-[12.5px] leading-relaxed text-[var(--muted)]">
                      「其他」暂存的原始材料逐条归类：对得上知识点的挂进去、按知识点的格子填好；树上没有的，AI 会<b className="text-[var(--fg)]">提案新知识点自动挂树</b>（这一轮最多长 3 个）。
                    </p>
                  </div>
                </div>
                <div className="mt-3 flex gap-3">
                  <span className="grid h-6 w-6 flex-none place-items-center rounded-full bg-[var(--accent-soft)] text-[12px] font-semibold text-[var(--accent)]">2</span>
                  <div>
                    <h3 className="text-[13.5px] font-semibold text-[var(--fg)]">梳理关系</h3>
                    <p className="mt-0.5 text-[12.5px] leading-relaxed text-[var(--muted)]">
                      在已归位的知识之间找关系：<b className="text-[var(--fg)]">细化</b>（这条笔法是那条的具体做法）、<b className="text-[var(--fg)]">矛盾</b>（两条规矩打架）、<b className="text-[var(--fg)]">依赖</b>（用这个手法得先懂那个设定）。
                    </p>
                  </div>
                </div>
              </div>
              <p className="mt-3 rounded-lg bg-[var(--fg-soft)] px-3 py-2 text-[11.5px] leading-relaxed text-[var(--muted)]">
                任务进「任务清单」后台执行，随时来看进度；AI 做完之前不动你现有的知识，留守材料留在「其他」。
              </p>
              <div className="mt-5 flex items-center justify-end gap-3">
                <span className="mr-auto text-[11.5px] text-[var(--faint)]">预计 1–2 分钟</span>
                <button className="rounded-md border border-[var(--border)] px-3 py-1.5 text-[12px] text-[var(--muted)] hover:text-[var(--fg)]" onClick={() => setShowRefineConfirm(false)}>暂不</button>
                <button
                  data-testid="kb-refine-start"
                  disabled={refineBusy || (genre === "全部题材" && !refineGenre)}
                  onClick={() => void startRefineTask()}
                  className="rounded-md bg-[var(--accent)] px-4 py-1.5 text-[12px] font-medium text-[var(--on-accent)] hover:bg-[var(--accent-strong)] disabled:opacity-50"
                >
                  {refineBusy ? "任务创建中…" : "开始提炼"}
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}
        {toast && createPortal(
          <div data-testid="kb-toast" className="fixed left-1/2 top-14 z-[70] flex -translate-x-1/2 items-center gap-3 rounded-lg bg-[var(--fg)] px-4 py-2.5 text-[12.5px] text-[var(--surface)] shadow-2xl">
            <span>{toast.text}</span>
            {toast.link && (
              <button
                className="underline underline-offset-2"
                style={{ color: "var(--accent-soft)" }}
                onClick={() => { const to = toast.link?.to; setToast(null); if (to) navigate(to); }}
              >{toast.link.label}</button>
            )}
          </div>,
          document.body,
        )}
        <div className="flex gap-6" style={{ display: view === "list" ? undefined : "none" }}>
          {/* 左栏 */}
          <aside className="w-52 flex-none pt-4">
            <p className="mb-2 font-mono text-[9.5px] tracking-[0.14em] text-[var(--muted)]">题材</p>
            <nav className="space-y-0.5">
              <button
                onClick={() => setGenre("全部题材")}
                className={`flex w-full items-center justify-between rounded-md px-3 py-1.5 text-[13px] ${genre === "全部题材" ? "bg-[var(--accent-soft)] font-medium text-[var(--accent)]" : "text-[var(--muted)] hover:text-[var(--fg)]"}`}
              >
                <span>全部</span><span className="font-mono text-[10px] opacity-70">{visibleRows.length}</span>
              </button>
              {visibleGenres.map((g) => (
                <button
                  key={g.key ?? g.name}
                  onClick={() => setGenre(g.key ?? g.name)}
                  className={`flex w-full items-center justify-between rounded-md px-3 py-1.5 text-[13px] ${genre === (g.key ?? g.name) ? "bg-[var(--accent-soft)] font-medium text-[var(--accent)]" : "text-[var(--muted)] hover:text-[var(--fg)]"}`}
                >
                  <span>{g.name}</span><span className="font-mono text-[10px] opacity-70">{g.count}</span>
                </button>
              ))}
              {showFoldToggle && (
                <button
                  onClick={() => setShowMoreGenres(!showMoreGenres)}
                  className="w-full rounded-md px-3 py-1.5 text-left text-[11px] text-[var(--faint)] hover:text-[var(--muted)]"
                >
                  {showMoreGenres ? "收起" : `更多题材 (${moreCount})`}
                </button>
              )}
              {!showMoreGenres && genreCounts.filter((g) => g.count === 0).slice(0, 2).map((g) => (
                <button
                  key={g.key ?? g.name}
                  onClick={() => setGenre(g.key ?? g.name)}
                  className="flex w-full items-center justify-between rounded-md px-3 py-1.5 text-[13px] text-[var(--faint)] hover:text-[var(--muted)]"
                >
                  <span>{g.name}</span><span className="font-mono text-[10px]">0</span>
                </button>
              ))}
              {showMoreGenres && genreCounts.filter((g) => g.count === 0).map((g) => (
                <button
                  key={g.key ?? g.name}
                  onClick={() => setGenre(g.key ?? g.name)}
                  className="flex w-full items-center justify-between rounded-md px-3 py-1.5 text-[13px] text-[var(--faint)] hover:text-[var(--muted)]"
                >
                  <span>{g.name}</span><span className="font-mono text-[10px]">0</span>
                </button>
              ))}
            </nav>
            <p className="mt-4 text-[10.5px] leading-relaxed text-[var(--faint)]">
              拆书时按题材归档；一本书只用一个题材的库。
            </p>
          </aside>

          {/* 主内容 */}
          <div className="min-w-0 flex-1 pt-4">
            {/* 概念页签 */}
            <div className="mb-4 flex flex-wrap gap-1.5">
              <button
                onClick={() => setConcept("全部")}
                className={`rounded-md px-3 py-1.5 text-[13px] ${concept === "全部" ? "bg-[var(--accent-soft)] font-medium text-[var(--accent)]" : "text-[var(--muted)] hover:text-[var(--fg)]"}`}
              >全部</button>
              {CONCEPTS.map((c) => (
                <button
                  key={c}
                  onClick={() => setConcept(c)}
                  title={CONCEPT_DESC[c]}
                  className={`rounded-md px-3 py-1.5 text-[13px] ${concept === c ? "bg-[var(--accent-soft)] font-medium text-[var(--accent)]" : "text-[var(--muted)] hover:text-[var(--fg)]"} ${c === "情节" ? "cursor-not-allowed opacity-40" : ""}`}
                  disabled={c === "情节"}
                >
                  {c}
                  {c === "情节" && <span className="ml-1 text-[9px] text-[var(--faint)]">即将上线</span>}
                </button>
              ))}
            </div>

            {/* 库分组卡已按原型退役（boss 2026-11-07）：知识库页不再展示选择器库——
                 库本体与绑定链路仍在（选择器/建书消费），仅本页展示面移除 */}

            {/* 来源筛选：官方即普通来源（boss 2026-11-08 无特权拍板） */}
            <div className="mb-3 flex flex-wrap gap-1.5">
              {SOURCE_FILTERS.map((s) => (
                <button
                  key={s.key}
                  data-testid={`kb-src-${s.key}`}
                  onClick={() => setSrc(s.key)}
                  className={`rounded-md border px-3 py-1 text-[12px] ${src === s.key ? "border-[var(--accent)] bg-[var(--accent-soft)] font-medium text-[var(--accent)]" : "border-[var(--border)] text-[var(--muted)] hover:text-[var(--fg)]"}`}
                >
                  {s.label}
                </button>
              ))}
            </div>

            {/* 搜索 */}
            <div className="mb-4">
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="搜名字、内容、来源书名"
                className="w-full max-w-xs rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-[13px] text-[var(--fg)] placeholder:text-[var(--faint)] focus:border-[var(--accent)] focus:outline-none"
              />
            </div>

            {/* 列表主体：统一实例行（全臂同构——官方条目也是实例） */}
            <>
            {/* 计数行＋排序：N 与分类分布同口径（含待归属素材行） */}
            {!selected && openError && (
              <p data-testid="kb-open-error" className="mb-2 text-[12px] text-[var(--muted)]">{openError}</p>
            )}
            <div className="mb-2 flex items-center justify-between gap-3">
              <span className="text-sm text-[var(--muted)]" data-testid="kb-count-line">
                共 <b className="font-medium text-[var(--fg)]">{visibleRows.length}</b> 条实例
                {conceptBreakdown.map(([c, n]) => (
                  <span key={c} className="ml-2 text-[12px] text-[var(--faint)]">· {c} {n}</span>
                ))}
              </span>
              <select
                aria-label="排序"
                value={sort}
                onChange={(e) => setSort(e.target.value as "recent" | "name")}
                className="h-7 rounded-md border border-[var(--border)] bg-[var(--surface)] px-2 text-[12px] text-[var(--fg)]"
              >
                <option value="recent">最近收录</option>
                <option value="name">名称</option>
              </select>
            </div>
            <div>
              {visibleRows.map((r) => {
                const openRow = () => {
                  if (r.row_kind === "material" || (r as { official?: boolean }).official) {
                    void openKnowledgeById(r.id); // 素材态/官方条目 → 详情抽屉（隐藏/副本动作在那边）
                    return;
                  }
                  setSelectedInstance(r);  // 实例详情＝主角；归属知识点是详情里的属性行
                };
                return (
                <div
                  key={`${r.row_kind}-${r.id}`}
                  data-testid={r.row_kind === "material" ? "kb-material-row" : "kb-inst-row"}
                  role="button"
                  tabIndex={0}
                  onClick={openRow}
                  onKeyDown={(ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); openRow(); } }}
                  className="cursor-pointer border-b border-[var(--border)] px-1 py-3.5 hover:bg-[var(--fg-soft)]"
                >
                  {/* 归属链：题材段非链接文字，知识各级 accent 可点下钻 */}
                  <div className="mb-1 flex flex-wrap items-center text-[11px]">
                    <span className="text-[var(--muted)]">{r.genre || "跨题材通用"}</span>
                    {r.chain.map((seg) => (
                      <span key={seg.id} className="flex items-center">
                        <span className="mx-1.5 text-[var(--faint)]">→</span>
                        <button
                          data-testid="kb-chain-seg"
                          onClick={(ev) => { ev.stopPropagation(); void openKnowledgeById(seg.id); }}
                          className="text-[var(--accent)] underline underline-offset-2 hover:text-[var(--accent-strong)]"
                        >{seg.title}</button>
                      </span>
                    ))}
                  </div>
                  <div className="mb-1 flex flex-wrap gap-1.5">
                    <span className="rounded-full bg-[var(--accent-soft)] px-2 py-px text-[10.5px] text-[var(--accent)]">{r.concept}</span>
                    {r.row_kind === "material" && (
                      <span data-testid="kb-row-material-badge" className="rounded-full border border-[var(--border)] px-2 py-px text-[10.5px] text-[var(--muted)]">待归属素材</span>
                    )}
                  </div>
                  <p className="text-[14px] leading-relaxed text-[var(--fg)]">
                    {r.row_kind === "instance" && r.name && (
                      <span className="font-semibold">{r.name}：</span>
                    )}
                    {r.text}
                    {r.quote && <span className="text-[var(--muted)]">——{r.quote}</span>}
                  </p>
                  {/* 出处行按值渲染：空片段不渲染、整行无值不渲染出处行 */}
                  {(r.source_novel || r.source_chapter) && (
                    <p className="mt-1 text-[11px] text-[var(--faint)]">
                      源自：{r.source_novel}{r.source_novel && r.source_chapter ? " · " : ""}{r.source_chapter}
                    </p>
                  )}
                  <p className="mt-1 text-right text-[11px] text-[var(--muted)]">
                    {r.created_at ? r.created_at.slice(0, 10) : ""} 收录 <span className="ml-1 text-[var(--faint)]">{r.src_kind}</span>
                  </p>
                </div>
                );
              })}
              {/* 实例臂空态：零内容题材＝记一条；筛选无命中＝清空筛选出口 */}
              {!visibleRows.length && !flatLoading && (genre === "全部题材" && concept === "全部" && !q.trim() && src === "全部" ? (
                <div className="rounded-lg border border-dashed border-[var(--border)] p-6 text-center">
                  <p className="text-[13px] text-[var(--muted)]">还没有条目——先拆书或手录，写法到位后这里会长出来。</p>
                  <button
                    onClick={() => setShowManual(true)}
                    className="mt-3 rounded-lg bg-[var(--accent)] px-4 py-2 text-[13px] font-medium text-[var(--on-accent)] hover:bg-[var(--accent-strong)]"
                  >记一条</button>
                </div>
              ) : (
                <div data-testid="kb-flat-empty" className="rounded-lg border border-dashed border-[var(--border)] p-6 text-center">
                  <p className="text-[13px] text-[var(--muted)]">当前筛选下没有写法。</p>
                  <button
                    data-testid="kb-clear-filters"
                    onClick={() => { setQ(""); setConcept("全部"); setSrc("全部"); setGenre("全部题材"); }}
                    className="mt-3 rounded-lg border border-[var(--accent)] px-4 py-2 text-[13px] text-[var(--accent)] hover:bg-[var(--accent-soft)]"
                  >清空筛选</button>
                </div>
              ))}
            </div>
            </>
          </div>
        </div>

      {/* 树视图（boss 2026-11-08：界面要能看到知识树——层级知识点＋实例挂点下） */}
      {view === "tree" && (
        <KnowledgeTreePanel
          genre={genre !== "全部题材" ? genre : ""}
          onSelectInstance={(row) => setSelectedInstance(row)}
        />
      )}

      {/* 手录表单 */}
      {showManual && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-lg rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6 shadow-xl">
            <h2 className="mb-4 text-lg font-semibold">记一条</h2>
            <div className="mb-3">
              <label className="mb-1 block text-[12px] text-[var(--muted)]">题材 *</label>
              <select
                aria-label="题材"
                value={manualGenre}
                onChange={(e) => setManualGenre(e.target.value)}
                className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-[13px]"
              >
                <option value="">选一个</option>
                {genreCounts.map((g) => (
                  <option key={g.key ?? g.name} value={g.key ?? g.name}>{g.name}</option>
                ))}
              </select>
            </div>
            <div className="mb-3">
              <label className="mb-1 block text-[12px] text-[var(--muted)]">类别（总结归组用）*</label>
              <select
                aria-label="类别"
                value={manualConcept}
                onChange={(e) => setManualConcept(e.target.value)}
                className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-[13px]"
              >
                {["手法", "文风", "文笔", "世界设定", "角色设定"].map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
            <div className="mb-3">
              <label className="mb-1 block text-[12px] text-[var(--muted)]">写什么（以句号结尾）*</label>
              <textarea
                value={manualText}
                onChange={(e) => setManualText(e.target.value)}
                placeholder="你想记什么写法？贴上来"
                rows={3}
                maxLength={240}
                className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-[13px] resize-none"
              />
              <p className="mt-1 text-right text-[10px] text-[var(--faint)]">{manualText.length}/240</p>
            </div>
            {manualError && <p className="mb-3 text-[12px] text-red-500">{manualError}</p>}
            {manualNote && (
              <p className="mb-3 text-[12px] text-[var(--accent)]">{manualNote}</p>
            )}
            <div className="flex justify-end gap-2">
              <button onClick={() => { setShowManual(false); setManualNote(""); }} className="rounded-lg border border-[var(--border)] px-4 py-2 text-[13px]">取消</button>
              <button onClick={handleManual} className="rounded-lg bg-[var(--accent)] px-4 py-2 text-[13px] font-medium text-[var(--on-accent)] hover:bg-[var(--accent-strong)]">保存</button>
            </div>
          </div>
        </div>
      )}

      {/* 实例详情弹窗（boss 2026-11-08：抽屉滚动后锚位漂移，改居中弹窗；portal 挂
          body——路由转场 transform 劫持 fixed 的 containing block） */}
      {selectedInstance && createPortal(
        <div className="fixed inset-0 z-50 flex items-center justify-center p-6">
          <div className="absolute inset-0 bg-black/50" onClick={() => setSelectedInstance(null)} />
          <div data-testid="kb-inst-modal" className="relative w-[560px] max-w-full max-h-[82vh] overflow-y-auto rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 shadow-2xl">
            <div className="mb-3 flex items-center justify-between">
              <span className="font-mono text-[9.5px] tracking-[0.1em] text-[var(--faint)]">
                {selectedInstance.concept} · {selectedInstance.genre || "跨题材通用"}
              </span>
              <button data-testid="kb-inst-drawer-close" onClick={() => setSelectedInstance(null)} className="text-[var(--faint)] hover:text-[var(--fg)]">✕</button>
            </div>
            {/* 归属属性行：知识点可点跳知识抽屉（定义/全量实例在那边） */}
            <div className="mb-3 text-[12px] text-[var(--muted)]">
              归属：{" "}
              <button
                onClick={() => { void openKnowledgeById(selectedInstance.knowledge_id); }}
                className="text-[var(--accent)] underline underline-offset-2 hover:text-[var(--accent-strong)]"
              >{selectedInstance.knowledge_title || /* v8 ignore next — 实例行 knowledge_title 后端恒非空 */ "未归属"}</button>
              {selectedInstance.chain.slice(0, -1).map((seg) => (
                <span key={seg.id}>
                  {" ← "}
                  <button
                    data-testid="kb-drawer-chain-seg"
                    onClick={(ev) => { ev.stopPropagation(); void openKnowledgeById(seg.id); }}
                    className="text-[var(--accent)] underline underline-offset-2 hover:text-[var(--accent-strong)]"
                  >{seg.title}</button>
                </span>
              ))}
            </div>
            {selectedInstance.row_kind === "instance" && selectedInstance.name && (
              <h2 className="text-[17px] font-semibold text-[var(--fg)]">{selectedInstance.name}</h2>
            )}
            <h2 className="text-[15px] font-medium leading-relaxed text-[var(--fg)]">
              {selectedInstance.text}
              {selectedInstance.quote && (
                <span className="text-[var(--muted)]">——{selectedInstance.quote}</span>
              )}
            </h2>
            {fieldsOf(selectedInstance).length > 0 && (
              <div className="mt-4">
                <p className="text-[10.5px] font-mono tracking-[0.12em] text-[var(--muted)]">写法细节</p>
                <dl className="mt-1 space-y-1.5">
                  {fieldsOf(selectedInstance).map(([label, value, quote]) => (
                    <div key={label}>
                      <dt className="text-[10.5px] font-mono tracking-[0.12em] text-[var(--muted)]">{label}</dt>
                      <dd className="whitespace-pre-wrap text-[12.5px] leading-relaxed text-[var(--fg)]">{value}</dd>
                      {quote && (
                        <dd className="mt-1">
                          <button
                            type="button"
                            className="text-[10.5px] text-[var(--muted)] underline-offset-2 hover:underline"
                            onClick={() =>
                              setQuoteOpen((prev) => {
                                const next = new Set(prev);
                                if (next.has(label)) next.delete(label);
                                else next.add(label);
                                return next;
                              })
                            }
                          >
                            {quoteOpen.has(label) ? "收起" : "看原句"}
                          </button>
                          {quoteOpen.has(label) && (
                            <p className="mt-1 whitespace-pre-wrap border-l-2 border-[var(--border)] pl-2 text-[11.5px] leading-relaxed text-[var(--muted)]">
                              原句：{quote}
                            </p>
                          )}
                        </dd>
                      )}
                    </div>
                  ))}
                </dl>
              </div>
            )}
            {(selectedInstance.source_novel || selectedInstance.source_chapter) && (
              <div className="mt-4">
                <p className="text-[10.5px] font-mono tracking-[0.12em] text-[var(--muted)]">出处</p>
                <p className="mt-1 text-[12px] text-[var(--muted)]">
                  源自：{selectedInstance.source_novel}{selectedInstance.source_novel && selectedInstance.source_chapter ? " · " : ""}{selectedInstance.source_chapter}
                </p>
              </div>
            )}
            <p className="mt-4 text-right text-[11px] text-[var(--muted)]">
              {selectedInstance.created_at ? selectedInstance.created_at.slice(0, 10) : ""} 收录{" "}
              <span className="ml-1 text-[var(--faint)]">{selectedInstance.src_kind}</span>
            </p>
          </div>
        </div>,
        document.body,
      )}

      {/* 知识详情弹窗（2026-11-08 与实例详情同改：居中弹窗＋portal 挂 body） */}
      {selected && createPortal(
        <div className="fixed inset-0 z-50 flex items-center justify-center p-6">
          <div className="absolute inset-0 bg-black/50" onClick={() => setSelected(null)} />
          <div data-testid="kb-know-modal" className="relative w-[560px] max-w-full max-h-[82vh] overflow-y-auto rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 shadow-2xl">
            <div className="mb-4 flex items-center justify-between">
              <span className="font-mono text-[9.5px] tracking-[0.1em] text-[var(--faint)]">
                {selected.id.slice(0, 8)} · {selected.concept} · {selected.genre}
              </span>
              <button onClick={() => setSelected(null)} className="text-[var(--faint)] hover:text-[var(--fg)]">✕</button>
            </div>
            <h2 className="text-xl font-semibold text-[var(--fg)]">{selected.title || selected.instruction.slice(0, 30)}</h2>
            {/* 分类：类别 + 题材 */}
            <div className="mt-2 text-[11px] text-[var(--muted)]">
              分类：类别 / {selected.concept} · 题材 / {selected.genre}
            </div>
            {instRows.length > 0 && (
              <div className="mt-4">
                <p className="text-[10.5px] font-mono tracking-[0.12em] text-[var(--muted)]">实例群</p>
                <ul className="mt-1 space-y-1">
                  {instRows.map((r) => (
                    <li key={r.id} className="rounded-md border border-[var(--border)] px-2.5 py-1.5 text-[12px]">
                      <p className="leading-relaxed">{r.text}</p>
                      {r.quote && (
                        <p className="mt-0.5 border-l-2 border-[var(--accent)] pl-2 text-[11.5px] text-[var(--muted)]">{r.quote}</p>
                      )}
                      {Object.entries(r.fields).filter(([, v]) => v).map(([k, v]) => (
                        <p key={k} className="mt-0.5 text-[11px] text-[var(--muted)]">
                          <span className="text-[var(--faint)]">{kbFieldLabel(selected.concept, k)}：</span>{prettyFieldValue(v)}
                        </p>
                      ))}
                      {r.source_novel && (
                        <p className="mt-0.5 text-[10.5px] text-[var(--faint)]">源自小说：{r.source_novel}</p>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {selected.origin === "material" && (
              <KbMaterialCard
                busy={opBusy}
                note={opNote}
                onDelete={() => void handleDeleteMaterial()}
              />
            )}
            {/* 知识定义 */}
            <div className="mt-4">
              <p className="text-[10.5px] font-mono tracking-[0.12em] text-[var(--muted)]">知识定义</p>
              {selected.definition ? (
                <p className="mt-1 text-[13px] leading-relaxed">{selected.definition}</p>
              ) : (
                <p className="mt-1 text-[11px] text-[var(--faint)]">知识定义待补——可在「修改」中补写一般性定义</p>
              )}
            </div>
            {/* 适用场景 */}
            {selected.when_text && (
              <div className="mt-3">
                <p className="text-[11px] text-[var(--muted)]">适用：{selected.when_text}</p>
              </div>
            )}
            {/* 字段 schema（c-kb-summarize）：知识点的字段元数据 */}
            {(() => {
              let schemaRows: { name: string; desc: string }[] = [];
              try { schemaRows = JSON.parse(selected.schema_json || "[]"); } catch /* v8 ignore next — 畸形 schema_json UI 不可达（后端恒合法 JSON） */ { schemaRows = []; }
              if (!Array.isArray(schemaRows) || schemaRows.length === 0) return null;
              return (
                <div className="mt-4">
                  <p className="text-[10.5px] font-mono tracking-[0.12em] text-[var(--muted)]">字段 schema</p>
                  <div className="mt-1 space-y-0.5">
                    {schemaRows.map((s) => {
                      // 字段名走中文字典；总结侧 desc 恒空（留待后端补作家语言）——
                      // 空说明不渲染悬空「·」（真机 2026-11-07 实锤）
                      const label = kbFieldLabel(selected.concept, s.name);
                      // desc 空时回退字段说明单源（kbFieldDesc）——总结侧不写 desc，
                      // 作家语言由前端字典统一供（c-kb-field-labels 同源机制）
                      const desc = (s.desc || kbFieldDesc(s.name)).trim();
                      return (
                        <p key={s.name} className="text-[12px]">
                          <span className="font-medium text-[var(--fg)]">{label}</span>
                          {desc && <span className="text-[var(--muted)]"> · {desc}</span>}
                        </p>
                      );
                    })}
                  </div>
                </div>
              );
            })()}
            {/* 实例：instruction 作为第 1 条实例 */}
            {selected.instruction && (
              <div className="mt-4">
                <p className="text-[10.5px] font-mono tracking-[0.12em] text-[var(--muted)]">实例</p>
                <div className="mt-2 border-l-2 border-[var(--accent)] pl-3">
                  <p className="text-[13px] leading-relaxed">{selected.instruction}</p>
                </div>
              </div>
            )}
            {payloadRows(selected.payload).length > 0 && (
              <div className="mt-4">
                <p className="text-[10.5px] font-mono tracking-[0.12em] text-[var(--muted)]">字段</p>
                <dl className="mt-1 space-y-1.5">
                  {payloadRows(selected.payload).map(([k, v]) => (
                    <div key={k}>
                      <dt className="text-[10.5px] font-mono tracking-[0.12em] text-[var(--muted)]">{kbFieldLabel(selected.concept, k)}</dt>
                      <dd className="whitespace-pre-wrap text-[12.5px] leading-relaxed text-[var(--fg)]">{v}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            )}
            {selected.example && (
              <div className="mt-4 border-l-2 border-[var(--accent)] pl-3">
                <p className="text-[10.5px] font-mono tracking-[0.12em] text-[var(--muted)]">正例</p>
                <p className="mt-1 text-[13px]">{selected.example}</p>
              </div>
            )}
            {selected.negative_example && (
              <div className="mt-4">
                <p className="text-[10.5px] font-mono tracking-[0.12em] text-[var(--muted)]">反例</p>
                <p className="mt-1 text-[13px]">{selected.negative_example}</p>
              </div>
            )}
            {opNote && (
              <p className="mt-2 text-[11.5px] text-[var(--muted)]">{opNote}</p>
            )}
            <KbEntryRelations
              entryId={selected.id}
              onOpenKnowledge={(id) => {
                const local = entries.find((x) => x.id === id);
                if (local) {
                  setSelected(local);
                  return;
                }
                // 对端不在当前筛选列表（跨题材/类别）：拉详情兜底；不可达给一句提示
                void kbApi
                  .entry(id)
                  .then((d) => setSelected(d))
                  .catch(() => setOpNote("这条关联的知识暂时打不开，稍后再试"));
              }}
            />
            {selected.evidence && (
              <div className="mt-4">
                <p className="text-[10.5px] font-mono tracking-[0.12em] text-[var(--muted)]">证据</p>
                <p className="mt-1 text-[12px] text-[var(--muted)]">{selected.evidence}</p>
              </div>
            )}
            {selected.src_novel_name && (
              <div className="mt-4">
                <p className="text-[10.5px] font-mono tracking-[0.12em] text-[var(--muted)]">源自小说</p>
                <p className="mt-1 text-[12px] text-[var(--muted)]">{selected.src_novel_name}</p>
              </div>
            )}

                  </div>
        </div>,
        document.body,
      )}
    </main>
  );
}
