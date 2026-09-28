// 伏笔设定面板（foreshadow-settings-v2）：伏笔台账＋伏笔卡（原型
// prototypes/foreshadow-settings.html 转正版）。
//   台账三分组（活跃=warn／已收束=ok／废弃=muted，空组不渲染）＋描述搜索＋添加置顶；
//   伏笔卡 .hk-kv 档案表（描述/引入/计划收束/类型/优先级/状态三态/收束记录软引导）；
//   章节三格＝卷章选择器（按卷 optgroup，存 chapter id，悬挂显示「章节已删」）。
// 持久化＝字段级防抖 PATCH＋串行队列（沿 CharacterManager；无 rev，失败即停不热循环）；
//   save()=flush 在途队列（gap3）；「存草稿」对伏笔隐藏（SettingsView 显隐条件）。
// 删除＝DELETE＋服务端 ops token 撤销（原 id 原样恢复）；回执面板内自管
//   （最近一条、8 秒自清窗口），不经 SettingsView 的 onReceiptChange 通道。
// 确认门禁＝≥1 条描述非空（任意状态）：前端提示性预检（按钮恒可点），后端 400 兜底；
//   确认后内容指纹变化→面板徽标「内容有变 · 待重新确认」（charStale 先例，快照落 localStorage）。
// AI 行（批2/批3，c-settings-ai-confirm-modal 起统一弹窗出卡）：
//   h1 起草＝3 候选进弹窗勾选卡（勾选→「采纳所选」走批1 乐观行队列，采纳后聚焦
//   引入章节选择器，回执精确撤销只回滚本次采纳）；
//   h2 拟收束方案＝弹窗结构化卡，已有收束记录时确认键明示「覆盖并收束」（警示级）；
//   采纳=PATCH {status:'resolved', resolved_chapter_id, payoff_note}＋flush＋回执精确撤销；
//   h3 体检＝弹窗报告卡，行可点跳转（关卡 skipRestore＋选中＋聚焦 goto 字段＋滚动可见）；
//   h4 查一致性＝选中 hook × 简介/题材/世界，弹窗报告卡行可点聚焦描述字段；
//   h2/h4 无选中置灰＋hint（SettingsView 批1 机制保留）；重开同一行展示缓存不发请求（D9）。
import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  hooksApi,
  type HookAuditCheck,
  type HookCandidate,
  type HooksCheckResult,
  type HookEntry,
  type HookPatchBody,
  type HookUndo,
  type VolumeTreeEntry,
} from "@/lib/hooksApi";
import {
  DESCRIPTION_MAX,
  HOOK_STATUSES,
  HOOK_TYPES,
  PAYOFF_NOTE_MAX,
  priorityLabel,
  typeLabel,
} from "@/lib/hooksModel";
import { aiBlockReason } from "@/lib/ai";
import { toast } from "@/lib/toast";
import { nodeLabel } from "@/lib/nodeTitle";
import { Ico, P } from "@/components/icons";
import AiCardModal from "./AiCardModal";
import type { SettingSaveHandle } from "./FormField";
import type { AiState } from "@/types/api-config";

interface Props {
  projectId: string;
  /** 设定键（settingsKey="hooks"）；真表化后仅作 SettingsView 注册表兼容保留 */
  settingKey: string;
  /** 脏状态回调（有未落库修改时 true）——接 SettingsView 的面板切换/离开守卫 */
  onDirtyChange?: (dirty: boolean) => void;
  /** 保存四态上报（面板脚 save-state 槽位由 SettingsView 渲染） */
  onSaveStateChange?: (s: HookSaveState) => void;
  /** 面板徽标五态＋空表预检上报（panel-head 徽标与 panel-foot note/warnline 槽位） */
  onPanelState?: (s: { cls: string; label: string; ok: boolean; empty: boolean }) => void;
  /** 选中条目变化上报（右栏 h2/h4 置灰与作用域行的数据源） */
  onCtxChange?: (ctx: { id: string; code: string; desc: string } | null) => void;
  /** 本书 AI 就绪态（D13）：空态「让 AI 起草」旁路同一门控 */
  aiState?: AiState;
  onBlocked?: (reason: AiState) => void;
  /** 该项是否已确认（confirmedStatus.hooks）——徽标「已确认」系与内容有变降级的判据 */
  confirmed?: boolean;
}

export interface HooksPanelHandle extends SettingSaveHandle {
  /** 确认成功后快照内容指纹（内容有变降级的基线；SettingsView confirm 流调用） */
  markConfirmed?: () => void;
  /** 确认预检：≥1 条 trim 非空描述（任意状态） */
  canConfirm?: () => boolean;
  runAi?: (key: string) => Promise<void>;
}

export type HookSaveState = "saved" | "saving" | "dirty" | "failed";

type HookStatusValue = (typeof HOOK_STATUSES)[number];

/** 右栏 AI 行动作（h1 起草 / h2 拟收束 / h3 体检 / h4 查一致性）。 */
type HooksAiAction = "h1" | "h2" | "h3" | "h4";

/** 起草候选（最近一版；「换一个」替换，勾选态随卡自持）。 */
interface DraftSinkEntry {
  candidates: HookCandidate[];
  checked: boolean[];
}

interface AuditSinkEntry {
  checks: HookAuditCheck[];
  degraded: boolean;
  degradedReasons: string[];
  verdict: string;
}

/** 拟收束方案结果（批3）：作用域钉在生成时的那条伏笔上（换选中即作废）。 */
interface PayoffSinkEntry {
  hookId: string;
  code: string;
  resolvedChapterRef: string;
  payoffNote: string;
}

/** 查一致性结果（批3）：三上下文行（简介/题材/世界 × 伏笔）。 */
interface CheckSinkEntry {
  hookId: string;
  checks: HooksCheckResult["checks"];
  degraded: boolean;
  degradedReasons: string[];
  verdict: string;
}

/** 采纳回执（面板内自管，8 秒自清）：精确撤销——
 *  draft＝只删本次采纳的那批 id；payoff＝把三字段改回采纳前值。 */
type AiReceipt =
  | { kind: "draft"; text: string; ids: string[] }
  | {
      kind: "payoff";
      text: string;
      hookId: string;
      before: {
        status: HookEntry["status"];
        resolved_chapter_id: string | null;
        payoff_note: string;
      };
    };

const GROUP_LABEL: Record<HookStatusValue, string> = {
  active: "活跃",
  resolved: "已收束",
  abandoned: "废弃",
};

/** 新增行默认值（与原型一致：活跃/悬念/中优先级/各章位留空）。 */
function emptyHook(projectId: string, tempId: string): HookEntry {
  return {
    id: tempId,
    novel_id: projectId,
    seq: 0,
    code: "#H-????",
    description: "",
    type: "mystery",
    priority: 2,
    status: "active",
    introduced_chapter_id: null,
    planned_chapter_id: null,
    resolved_chapter_id: null,
    mentioned_chapter_id: null,
    payoff_note: "",
    created_at: null,
    updated_at: null,
  };
}

/** 内容指纹：确认基线（内容有变→徽标降级）。只含落库内容，不含时间戳。 */
function fingerprint(items: HookEntry[]): string {
  return [...items]
    .sort((a, b) => a.seq - b.seq)
    .map((h) =>
      [
        h.seq,
        h.description,
        h.type,
        h.priority,
        h.status,
        h.introduced_chapter_id ?? "",
        h.planned_chapter_id ?? "",
        h.resolved_chapter_id ?? "",
        h.payoff_note,
      ].join("\u0001"),
    )
    .join("\u0002");
}

const HooksSettingForm = forwardRef<HooksPanelHandle, Props>(function HooksSettingForm(
  { projectId, onDirtyChange, onSaveStateChange, onPanelState, onCtxChange, aiState, onBlocked, confirmed = false },
  ref,
) {
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState<HookEntry[]>([]);
  const [vols, setVols] = useState<VolumeTreeEntry[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [query, setQuery] = useState("");
  const [saveState, setSaveState] = useState<HookSaveState>("saved");
  /** 删除回执（面板内自管）：最近一条 + 撤销凭证；8 秒自清窗口 */
  const [receipt, setReceipt] = useState<{ text: string; undo: HookUndo } | null>(null);
  const [dirty, setDirty] = useState(false);

  const itemsRef = useRef<HookEntry[]>([]);
  itemsRef.current = items;
  const selectedIdRef = useRef("");
  selectedIdRef.current = selectedId;
  const saveStateRef = useRef<HookSaveState>("saved");
  saveStateRef.current = saveState;
  /** 确认内容指纹基线（localStorage 持久，reload 后徽标口径一致） */
  const snapRef = useRef<string | null>(null);
  const [snapVersion, setSnapVersion] = useState(0);

  const queueRef = useRef<{ hookId: string; field: string; value: unknown }[]>([]);
  const runningRef = useRef(false);
  const timerRef = useRef<number | null>(null);
  /** 在途建行（乐观 temp 行 → POST 真 id 替换）；PATCH 队列在 flush 时先等它 */
  const creatingRef = useRef<Promise<unknown> | null>(null);
  const receiptTimerRef = useRef<number | null>(null);
  const descInputRef = useRef<HTMLTextAreaElement>(null);
  const outSelectRef = useRef<HTMLSelectElement>(null);
  /** AI 行跳转落点：引入章节（采纳后聚焦）/ 计划收束（未定期·超期）/ 怎么收的（无留痕） */
  const inSelectRef = useRef<HTMLSelectElement>(null);
  const planSelectRef = useRef<HTMLSelectElement>(null);
  const howInputRef = useRef<HTMLTextAreaElement>(null);

  const applySaveState = useCallback(
    (s: HookSaveState) => {
      setSaveState(s);
      onSaveStateChange?.(s);
    },
    [onSaveStateChange],
  );

  const markDirty = useCallback(() => {
    setDirty(true);
    onDirtyChange?.(true);
  }, [onDirtyChange]);

  const clearDirty = useCallback(() => {
    setDirty(false);
    onDirtyChange?.(false);
  }, [onDirtyChange]);

  const reloadList = useCallback(async (): Promise<HookEntry[]> => {
    const data = await hooksApi.list(projectId);
    setItems(data.items);
    return data.items;
  }, [projectId]);

  // ── 初始加载：台账 + 卷章树（选择器数据源） ──────────────────────────
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        try {
          snapRef.current = window.localStorage.getItem(`foreshadow.snap.${projectId}`);
        } catch {
          snapRef.current = null;
        }
        const [data, volsRes] = await Promise.all([
          hooksApi.list(projectId),
          hooksApi.volumes(projectId).catch(() => [] as VolumeTreeEntry[]),
        ]);
        if (!alive) return;
        setItems(data.items);
        setVols(volsRes);
        if (data.items.length) {
          selectedIdRef.current = data.items[0].id;
          setSelectedId(data.items[0].id);
        }
      } catch {
        if (alive) toast.error("伏笔加载失败，请刷新重试");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  // ── 自动保存：串行队列 flush（字段级 PATCH；无 rev——失败即丢弃该项，不热循环） ──
  const flushQueue = useCallback(async () => {
    if (runningRef.current || queueRef.current.length === 0) return;
    runningRef.current = true;
    applySaveState("saving");
    try {
      while (queueRef.current.length > 0) {
        if (creatingRef.current) await creatingRef.current.catch(() => {});
        const next = queueRef.current.shift()!;
        try {
          await hooksApi.patch(projectId, next.hookId, { [next.field]: next.value });
        } catch {
          applySaveState("failed");
          toast.error("自动保存失败——请检查网络后重试");
        }
      }
      if (saveStateRef.current !== "failed") {
        applySaveState("saved");
        clearDirty();
      }
    } finally {
      runningRef.current = false;
      if (queueRef.current.length > 0) void flushQueue();
    }
  }, [projectId, applySaveState, clearDirty]);

  const enqueue = useCallback(
    (hookId: string, field: string, value: unknown) => {
      queueRef.current = queueRef.current.filter(
        (op) => !(op.hookId === hookId && op.field === field),
      );
      queueRef.current.push({ hookId, field, value });
      markDirty();
      applySaveState("dirty");
      if (timerRef.current) window.clearTimeout(timerRef.current);
      timerRef.current = window.setTimeout(() => void flushQueue(), 600);
    },
    [flushQueue, markDirty, applySaveState],
  );

  const setField = useCallback(
    (field: keyof HookEntry, value: unknown) => {
      const hookId = selectedIdRef.current;
      if (!hookId) return;
      setItems((prev) => prev.map((h) => (h.id === hookId ? { ...h, [field]: value } : h)));
      enqueue(hookId, field, value);
    },
    [enqueue],
  );

  // ── 建行（乐观 temp 行 → 串行 POST 真 id 替换）────────────────────────
  // 「添加伏笔」与 AI 采纳共用：批1 的「POST 回踩清本地输入」竞态修复语义原样保留——
  // temp 行上用户已抢编辑的值用队列现值合并，不被 POST 响应整行回踩。
  const createRows = useCallback(
    (bodies: HookPatchBody[]): Promise<string[]> => {
      const temps = bodies.map(
        (body) =>
          ({ tempId: `temp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`, body }),
      );
      setItems((prev) => [
        ...prev,
        ...temps.map(
          (t) => ({ ...emptyHook(projectId, t.tempId), ...t.body }) as HookEntry,
        ),
      ]);
      selectedIdRef.current = temps[0].tempId;
      setSelectedId(temps[0].tempId);
      setQuery("");
      markDirty();
      applySaveState("dirty");
      const run = (async () => {
        try {
          await creatingRef.current?.catch(() => {});
          const ids: string[] = [];
          for (const t of temps) {
            const created = await hooksApi.create(projectId, t.body);
            ids.push(created.id);
            const merged: HookEntry = { ...created };
            for (const op of queueRef.current) {
              if (op.hookId === t.tempId)
                (merged as unknown as Record<string, unknown>)[op.field] = op.value;
            }
            setItems((prev) => prev.map((h) => (h.id === t.tempId ? merged : h)));
            queueRef.current.forEach((op) => {
              if (op.hookId === t.tempId) op.hookId = created.id;
            });
          }
          if (selectedIdRef.current === temps[0].tempId) {
            selectedIdRef.current = ids[0];
            setSelectedId(ids[0]);
          }
          if (queueRef.current.length === 0) {
            applySaveState("saved");
            clearDirty();
          }
          return ids;
        } catch (e) {
          // 失败：回滚 temp 行、选中回正、保存态置失败（调用方决定 toast 文案）
          setItems((prev) => prev.filter((h) => !temps.some((t) => t.tempId === h.id)));
          if (temps.some((t) => t.tempId === selectedIdRef.current)) {
            const rest = itemsRef.current.filter(
              (h) => !temps.some((t) => t.tempId === h.id),
            );
            selectedIdRef.current = rest[0]?.id ?? "";
            setSelectedId(rest[0]?.id ?? "");
          }
          applySaveState("failed");
          throw e;
        }
      })();
      creatingRef.current = run;
      void run.then(
        () => {
          if (creatingRef.current === run) creatingRef.current = null;
        },
        () => {
          if (creatingRef.current === run) creatingRef.current = null;
        },
      );
      return run;
    },
    [projectId, markDirty, applySaveState, clearDirty],
  );

  const addHook = useCallback(() => {
    createRows([{}]).catch(() => {
      toast.error("添加失败，请重试");
    });
    window.setTimeout(() => descInputRef.current?.focus(), 0);
  }, [createRows]);

  // ── 删除：即落库 DELETE＋ops token；回执 8 秒自清；撤销按原 id 原样恢复 ──
  const doDelete = useCallback(async () => {
    if (timerRef.current) window.clearTimeout(timerRef.current);
    await flushQueue();
    if (creatingRef.current) await creatingRef.current.catch(() => {});
    const target = itemsRef.current.find((h) => h.id === selectedIdRef.current);
    if (!target || target.id.startsWith("temp-")) return;
    try {
      const res = await hooksApi.remove(projectId, target.id);
      queueRef.current = queueRef.current.filter((op) => op.hookId !== target.id);
      const data = await hooksApi.list(projectId);
      setItems(data.items);
      const rest = data.items;
      selectedIdRef.current = rest[0]?.id ?? "";
      setSelectedId(rest[0]?.id ?? "");
      setReceipt({ text: `${res.receipt} · 8 秒内可点撤销`, undo: res.undo });
      if (receiptTimerRef.current) window.clearTimeout(receiptTimerRef.current);
      receiptTimerRef.current = window.setTimeout(() => setReceipt(null), 8000);
    } catch (e) {
      toast.error((e as Error).message || "删除失败");
    }
  }, [projectId, flushQueue]);

  const doUndo = useCallback(async () => {
    const rec = receipt;
    if (!rec) return;
    try {
      const restored = await hooksApi.restore(projectId, rec.undo);
      setReceipt(null);
      if (receiptTimerRef.current) window.clearTimeout(receiptTimerRef.current);
      await reloadList();
      selectedIdRef.current = restored.id;
      setSelectedId(restored.id);
      toast.success("已撤销，按原编号原样找回");
    } catch (e) {
      // token 过期/被顶掉（409）：窗口已关，重试不可用——收起回执并明示
      setReceipt(null);
      toast.error((e as Error).message || "撤销窗口已过，无法恢复");
    }
  }, [receipt, projectId, reloadList]);

  // ── 状态三态切换：切换即挪组、选中跟随；resolved→active 保留收束记录（PATCH 只动 status） ──
  const switchStatus = useCallback(
    (to: HookStatusValue) => {
      const cur = itemsRef.current.find((h) => h.id === selectedIdRef.current);
      if (!cur || cur.status === to) return;
      setField("status", to);
      if (to === "resolved") {
        toast.info("已移入「已收束」——选收束章节、补一句怎么收的");
        window.setTimeout(() => outSelectRef.current?.focus(), 0);
      } else if (to === "abandoned") {
        toast.info("已移入「废弃」——不再收束，移回活跃可重新埋");
      } else {
        toast.info("已移回「活跃」——记得补计划收束章");
      }
    },
    [setField],
  );

  // ── AI 行：h1 起草 / h2 拟收束 / h3 体检 / h4 查一致性 ─────────────────
  // c-settings-ai-confirm-modal：结果统一进弹窗出卡（内嵌结果区退役）；每行缓存
  // 最近一版，重开同一行直接展示缓存不再发请求，「换一个／重新检查」才重跑（D9）。
  const [draftSinks, setDraftSinks] = useState<DraftSinkEntry | null>(null);
  const [auditSinks, setAuditSinks] = useState<AuditSinkEntry | null>(null);
  /** h2/h4 只留最近一次结果（重跑即替换；换选中条目即作废——作用域钉在生成时那条） */
  const [payoffSink, setPayoffSink] = useState<PayoffSinkEntry | null>(null);
  const [checkSink, setCheckSink] = useState<CheckSinkEntry | null>(null);
  const [cardAction, setCardAction] = useState<HooksAiAction | null>(null);
  const [cardOpen, setCardOpen] = useState(false);
  const [cardCached, setCardCached] = useState(false);
  const [cardError, setCardError] = useState("");
  const [versions, setVersions] = useState<Partial<Record<HooksAiAction, number>>>({});
  const [aiRunning, setAiRunning] = useState<HooksAiAction | null>(null);
  /** 面板级在途锁（ref 同步判定）：无论调用方点几次，同时在飞的只有一个请求。 */
  const aiBusyRef = useRef(false);
  /** 采纳回执（面板内自管，8 秒自清）：精确撤销＝只回滚这次采纳 */
  const [aiReceipt, setAiReceipt] = useState<AiReceipt | null>(null);
  const aiReceiptTimerRef = useRef<number | null>(null);
  /** 报告行跳转关卡时置 true：跳过 Modal 关闭后的焦点还原（防抢走 jumpToHook 聚焦，D6） */
  const cardSkipRestoreRef = useRef(false);

  /** ref（vol-N-ch-M）→ 卷章树里的章 id；未建章/树里查不到返回 null（留空待补） */
  const refToChapterId = useCallback(
    (ref: string): string | null => {
      for (const v of vols) {
        const ch = v.chapters.find((c) => c.ref === ref);
        if (ch) return ch.id;
      }
      return null;
    },
    [vols],
  );

  const runRequest = useCallback(
    async (key: HooksAiAction) => {
      aiBusyRef.current = true;
      setAiRunning(key);
      setCardError("");
      // h2/h4 前置：无选中不空跑也不开卡（沿原守卫文案）
      if (key === "h2" || key === "h4") {
        if (creatingRef.current) await creatingRef.current.catch(() => {});
        const cur = itemsRef.current.find((h) => h.id === selectedIdRef.current);
        if (!cur || cur.id.startsWith("temp-")) {
          toast.info(
            key === "h2" ? "先选一条伏笔——收束方案对选中条目生效" : "先选一条伏笔——查一致性对选中条目生效",
          );
          aiBusyRef.current = false;
          return;
        }
      }
      setCardAction(key);
      setCardOpen(true);
      try {
        if (key === "h1") {
          const r = await hooksApi.draftAi(projectId);
          const candidates = r.candidates ?? [];
          setDraftSinks({ candidates, checked: candidates.map(() => true) });
        } else if (key === "h2") {
          // 作用域＝当前选中 hook：body 传当前编辑值（intro 先例——不读库旧文）
          const cur = itemsRef.current.find((h) => h.id === selectedIdRef.current);
          if (!cur || cur.id.startsWith("temp-")) {
            toast.info("先选一条伏笔——收束方案对选中条目生效");
            return;
          }
          const r = await hooksApi.payoffAi(projectId, {
            hook_id: cur.id,
            description: cur.description,
            type: cur.type,
            priority: cur.priority,
            code: cur.code,
            planned_chapter_id: cur.planned_chapter_id,
          });
          setPayoffSink({
            hookId: cur.id,
            code: cur.code,
            resolvedChapterRef: r.resolved_chapter_ref,
            payoffNote: r.payoff_note,
          });
        } else if (key === "h3") {
          const r = await hooksApi.auditAi(projectId);
          setAuditSinks({
            checks: r.checks ?? [],
            degraded: !!r.degraded,
            degradedReasons: r.degraded_reasons ?? [],
            verdict: r.verdict ?? "",
          });
        } else {
          const cur = itemsRef.current.find((h) => h.id === selectedIdRef.current);
          if (!cur || cur.id.startsWith("temp-")) {
            toast.info("先选一条伏笔——查一致性对选中条目生效");
            return;
          }
          const r = await hooksApi.checkAi(projectId, {
            hook_id: cur.id,
            description: cur.description,
            type: cur.type,
            priority: cur.priority,
            code: cur.code,
          });
          setCheckSink({
            hookId: cur.id,
            checks: r.checks ?? [],
            degraded: !!r.degraded,
            degradedReasons: r.degraded_reasons ?? [],
            verdict: r.verdict ?? "",
          });
        }
        setCardCached(false);
        setVersions((prev) => ({ ...prev, [key]: (prev[key] ?? 0) + 1 }));
      } catch (e) {
        const reason = aiBlockReason(e);
        // 403 member_required 已由 request() 广播全局升级引导，这里只兜底文案
        if (reason === "member_required") toast.info("AI 是会员功能，升级 PRO 后解锁");
        else if (reason === "no_key") toast.info((e as Error).message || "先去「模型配置」添加 API Key");
        else if (reason === "missing_model" || reason === "invalid")
          toast.info("先在本书选择模型");
        else toast.error((e as Error).message || "生成失败，请重试");
        setCardOpen(false);
      } finally {
        aiBusyRef.current = false;
        setAiRunning(null);
      }
    },
    [projectId],
  );

  const runAi = useCallback(
    async (key: string) => {
      if (aiBusyRef.current) return; // 已有在途请求：忽略重复触发
      if (key !== "h1" && key !== "h2" && key !== "h3" && key !== "h4") return;
      const hasCache =
        (key === "h1" && !!draftSinks) ||
        (key === "h2" && !!payoffSink) ||
        (key === "h3" && !!auditSinks) ||
        (key === "h4" && !!checkSink);
      if (hasCache) {
        // 重开＝展示缓存，不重复生成（D9）
        setCardCached(true);
        setCardError("");
        setCardAction(key);
        setCardOpen(true);
        return;
      }
      await runRequest(key);
    },
    [draftSinks, payoffSink, auditSinks, checkSink, runRequest],
  );

  /** 采纳所选候选：走批1 乐观行队列建行（保留「POST 回踩清本地输入」竞态修复语义） */
  const adoptCandidates = useCallback(
    async (entry: DraftSinkEntry) => {
      const chosen = entry.candidates.filter((_, i) => entry.checked[i] ?? true);
      if (chosen.length === 0) {
        toast.info("先勾选至少一条候选");
        return;
      }
      let ids: string[];
      try {
        ids = await createRows(
          chosen.map((c) => ({
            description: c.description,
            type: c.type,
            priority: c.priority,
          })),
        );
      } catch {
        toast.error("采纳失败，请重试");
        return;
      }
      // 采纳后聚焦引入章节选择器——「选一下引入章节就算埋好了」
      window.setTimeout(() => inSelectRef.current?.focus(), 0);
      // 回执精确撤销：只回滚本次采纳的这批 id，不影响用户此前的其他编辑
      setAiReceipt({
        kind: "draft",
        text: `已采纳「起草伏笔」：${ids.length} 条加入活跃组，章位待补 · 8 秒内可点撤销`,
        ids,
      });
      if (aiReceiptTimerRef.current) window.clearTimeout(aiReceiptTimerRef.current);
      aiReceiptTimerRef.current = window.setTimeout(() => setAiReceipt(null), 8000);
      setCardOpen(false); // 确认写回＝弹窗自动关
      toast.success(`已加入 ${ids.length} 条——选一下引入章节就算埋好了`);
    },
    [createRows],
  );

  /** 采纳拟收束方案（批3）：先 flush 在途编辑（用户等待期改的字段先落库，避免
   *  采纳后被队列旧值回踩），再 PATCH {status, resolved_chapter_id, payoff_note}；
   *  已有收束记录时按钮已明示「覆盖并收束」，撤销兜底（三字段改回采纳前值）。 */
  const adoptPayoff = useCallback(
    async (entry: PayoffSinkEntry) => {
      const prev = itemsRef.current.find((h) => h.id === entry.hookId);
      if (!prev || prev.id.startsWith("temp-")) {
        toast.error("这条伏笔不在台账里，无法采纳");
        return;
      }
      const before = {
        status: prev.status,
        resolved_chapter_id: prev.resolved_chapter_id,
        payoff_note: prev.payoff_note,
      };
      if (timerRef.current) window.clearTimeout(timerRef.current);
      await flushQueue();
      const chapterId = refToChapterId(entry.resolvedChapterRef);
      try {
        await hooksApi.patch(projectId, entry.hookId, {
          status: "resolved",
          resolved_chapter_id: chapterId,
          payoff_note: entry.payoffNote,
        });
      } catch {
        toast.error("采纳失败，请重试");
        return;
      }
      await reloadList();
      selectedIdRef.current = entry.hookId;
      setSelectedId(entry.hookId);
      setPayoffSink(null);
      setAiReceipt({
        kind: "payoff",
        text: `已采纳「拟收束方案」：${entry.code} 移入已收束${
          chapterId ? "" : "（建议章未建，收束章节留空待补）"
        } · 8 秒内可点撤销`,
        hookId: entry.hookId,
        before,
      });
      if (aiReceiptTimerRef.current) window.clearTimeout(aiReceiptTimerRef.current);
      aiReceiptTimerRef.current = window.setTimeout(() => setAiReceipt(null), 8000);
      setCardOpen(false); // 确认写回＝弹窗自动关
      toast.success("已收束——收束记录已写入");
    },
    [projectId, flushQueue, refToChapterId, reloadList],
  );

  /** 精确撤销本次采纳：draft＝逐条 DELETE（行已被用户手动删的跳过）；
   *  payoff＝三字段改回采纳前值（不影响其他行与其他编辑）。 */
  const undoAdopt = useCallback(async () => {
    const rec = aiReceipt;
    if (!rec) return;
    if (rec.kind === "payoff") {
      try {
        await hooksApi.patch(projectId, rec.hookId, {
          status: rec.before.status,
          resolved_chapter_id: rec.before.resolved_chapter_id,
          payoff_note: rec.before.payoff_note,
        });
      } catch {
        toast.error("撤销失败——这条伏笔可能已被删除，请手动核对");
        return;
      }
      if (aiReceiptTimerRef.current) window.clearTimeout(aiReceiptTimerRef.current);
      setAiReceipt(null);
      const rest = await reloadList();
      if (!rest.some((h) => h.id === selectedIdRef.current)) {
        selectedIdRef.current = rest[0]?.id ?? "";
        setSelectedId(rest[0]?.id ?? "");
      }
      toast.success("已撤销，恢复采纳前内容");
      return;
    }
    let failed = 0;
    for (const id of rec.ids) {
      try {
        await hooksApi.remove(projectId, id);
      } catch {
        failed += 1;
      }
    }
    if (aiReceiptTimerRef.current) window.clearTimeout(aiReceiptTimerRef.current);
    setAiReceipt(null);
    const rest = await reloadList();
    if (!rest.some((h) => h.id === selectedIdRef.current)) {
      selectedIdRef.current = rest[0]?.id ?? "";
      setSelectedId(rest[0]?.id ?? "");
    }
    toast.success(
      failed ? `已撤销（${rec.ids.length - failed}/${rec.ids.length} 条，其余请手动核对）` : "已撤销，只回滚这次采纳",
    );
  }, [aiReceipt, projectId, reloadList]);

  /** 换选中条目即作废拟收束方案结果（作用域钉在生成时的那条；沿原型 selectHook） */
  useEffect(() => {
    setPayoffSink((prev) => (prev && prev.hookId !== selectedId ? null : prev));
  }, [selectedId]);

  /** 体检行跳转：先 flush 在途保存，再选中该伏笔＋聚焦 goto 字段＋滚动可见 */
  const jumpToHook = useCallback(
    (hookId: string, gotoField: string | null) => {
      if (timerRef.current) window.clearTimeout(timerRef.current);
      void flushQueue().then(() => {
        selectedIdRef.current = hookId;
        setSelectedId(hookId);
        if (!gotoField) return;
        // 等选中行的字段渲染后再聚焦（收束记录区只在已收束态展开）
        window.setTimeout(() => {
          const el = gotoField === "payoff" ? howInputRef.current : planSelectRef.current;
          el?.scrollIntoView({ block: "center", behavior: "smooth" });
          el?.focus();
        }, 60);
      });
    },
    [flushQueue],
  );

  // ── 句柄：save()=flush（gap3 确认前落库）；确认快照；AI 分发 ─────────────
  useImperativeHandle(ref, () => ({
    save: async () => {
      if (timerRef.current) window.clearTimeout(timerRef.current);
      await flushQueue();
      if (creatingRef.current) await creatingRef.current.catch(() => {});
      return queueRef.current.length === 0 && saveStateRef.current !== "failed";
    },
    markDirty,
    clearAi: () => {
      // 确认动作会清 AI 结果卡（沿简介/角色先例：确认＝基线前移，旧建议作废）
      setDraftSinks(null);
      setAuditSinks(null);
      setPayoffSink(null);
      setCheckSink(null);
      setCardAction(null);
      setCardOpen(false);
    },
    markConfirmed: () => {
      const fp = fingerprint(itemsRef.current);
      snapRef.current = fp;
      try {
        window.localStorage.setItem(`foreshadow.snap.${projectId}`, fp);
      } catch {
        /* 隐私模式等存储失败：徽标降级退化为会话内不跨刷新 */
      }
      setSnapVersion((v) => v + 1);
    },
    canConfirm: () => itemsRef.current.some((h) => h.description.trim().length > 0),
    runAi,
  }));

  // ── 章节引用显示：树内查 label；悬挂 id 显示「章节已删」；空显示占位 ──────
  const chLabel = useCallback(
    (id: string | null): string => {
      if (!id) return "";
      for (const v of vols) {
        const ch = v.chapters.find((c) => c.id === id);
        if (ch)
          return `第 ${String(ch.chapter).padStart(2, "0")} 章${ch.title ? ` · ${ch.title}` : ""}`;
      }
      return "章节已删";
    },
    [vols],
  );

  const selected = items.find((h) => h.id === selectedId) ?? null;

  // ── 上报：面板徽标五态＋空表预检；选中条目 ctx ────────────────────────
  const pendingCount = items.filter((h) => h.status === "active").length;
  const fp = useMemo(() => fingerprint(items), [items]);
  const stale = confirmed && snapRef.current !== null && snapRef.current !== fp;
  const hasContent = items.some((h) => h.description.trim().length > 0);

  const lastPanelState = useRef("");
  useEffect(() => {
    let next: { cls: string; label: string; ok: boolean; empty: boolean };
    if (stale) next = { cls: "warn", label: "内容有变 · 待重新确认", ok: false, empty: !hasContent };
    else if (items.length === 0)
      next = { cls: "empty", label: "还没有伏笔", ok: false, empty: true };
    else if (confirmed)
      next = { cls: "ok", label: `已确认 · ${pendingCount} 条待收束`, ok: true, empty: !hasContent };
    else if (pendingCount > 0)
      next = { cls: "warn", label: `${pendingCount} 条待收束`, ok: false, empty: !hasContent };
    else next = { cls: "ok", label: "全部收束", ok: true, empty: !hasContent };
    // 挂载/每次派生值变化都上报（父层不重置本状态，避免「先清后报」时序抹掉）；
    // 同值重入由父层 setState 浅比较吸收（deps 不含父层状态，无回环）
    const key = JSON.stringify(next) + stale + snapVersion;
    if (key !== lastPanelState.current) {
      lastPanelState.current = key;
      onPanelState?.(next);
    }
  }, [items, pendingCount, confirmed, stale, hasContent, snapVersion, onPanelState, fp]);

  const lastCtx = useRef("");
  useEffect(() => {
    const key = selected ? `${selected.id}|${selected.code}|${selected.description}` : "";
    if (key === lastCtx.current) return;
    lastCtx.current = key;
    onCtxChange?.(
      selected
        ? { id: selected.id, code: selected.code, desc: selected.description }
        : null,
    );
  }, [selected, onCtxChange]);

  // 挂载即上报保存态初始值（面板脚 save-state 槽位随挂载对齐，不等第一次编辑）
  useEffect(() => {
    onSaveStateChange?.(saveStateRef.current);
  }, [onSaveStateChange]);

  // ── 台账渲染数据：三分组＋搜索过滤（空组不渲染） ───────────────────────
  const q = query.trim();
  const groups = HOOK_STATUSES.map((status) => ({
    status: status as HookStatusValue,
    label: GROUP_LABEL[status as HookStatusValue],
    rows: items.filter(
      (h) => h.status === status && (!q || h.description.includes(q)),
    ),
  }));
  const visibleCount = groups.reduce((n, g) => n + g.rows.length, 0);

  /** 章节选择器公共片：按卷 optgroup；悬挂 id 补「章节已删」占位选项（保留值不丢） */
  const chapterOptions = (value: string | null) => {
    const dangling = value && !vols.some((v) => v.chapters.some((c) => c.id === value));
    return (
      <>
        {dangling && <option value={value}>章节已删</option>}
        {vols.map((v, vi) => (
          <optgroup key={v.ref} label={nodeLabel("卷", vi + 1, v.title)}>
            {v.chapters.map((c) => (
              <option key={c.id} value={c.id}>
                第 {String(c.chapter).padStart(2, "0")} 章{c.title ? ` · ${c.title}` : ""}
              </option>
            ))}
          </optgroup>
        ))}
      </>
    );
  };

  if (loading) return <p className="opt">加载中…</p>;

  const stateTagCls =
    selected?.status === "resolved"
      ? "st-resolved"
      : selected?.status === "abandoned"
        ? "st-abandoned"
        : "st-active";

  return (
    <div className="hk-root">
      <div className="hk-sub">
        {/* ═══ 子栏左 · 伏笔台账 ═══ */}
        <nav className="hk-tree" data-od-id="tree-hooks" aria-label="伏笔台账">
          <div className="hk-tree-top">
            伏笔<span className="hk-cnt num">{visibleCount}</span>
          </div>
          <button type="button" className="hk-add" data-od-id="btn-add-hook" onClick={addHook}>
            <Ico d={P.plus} size={13} /> 添加伏笔
          </button>
          <input
            className="hk-search"
            type="search"
            placeholder="搜描述…"
            aria-label="搜索伏笔描述"
            data-od-id="search-hook"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className="hk-list">
            {groups.map((g) =>
              g.rows.length === 0 ? null : (
                <div key={g.status}>
                  <div className="hk-group">
                    <span className={`hk-g-dot ${g.status}`} />
                    {g.label}
                    <span className="hk-g-cnt num">{g.rows.length}</span>
                  </div>
                  {g.rows.map((h) => (
                    <button
                      key={h.id}
                      type="button"
                      className={`hk-item${selectedId === h.id ? " on" : ""}`}
                      onClick={() => {
                        if (h.id === selectedIdRef.current) return;
                        if (timerRef.current) window.clearTimeout(timerRef.current);
                        void flushQueue().then(() => {
                          selectedIdRef.current = h.id;
                          setSelectedId(h.id);
                        });
                      }}
                    >
                      <span className={`hk-dot ${h.status}`} />
                      <span className="hk-b">
                        <span className="hk-name">{h.description || "未填写"}</span>
                        <span className="hk-meta">
                          <span className="hk-type">{typeLabel(h.type)}</span>
                          <span>{priorityLabel(h.priority)}</span>
                          <span className="hk-ch">
                            {h.status === "resolved"
                              ? `收于 ${chLabel(h.resolved_chapter_id) || "未记"}`
                              : chLabel(h.introduced_chapter_id) || "未记章"}
                          </span>
                        </span>
                      </span>
                    </button>
                  ))}
                </div>
              ),
            )}
            {q && visibleCount === 0 && (
              <p className="opt" style={{ padding: "4px 8px" }}>
                没有找到——换个词试试。
              </p>
            )}
          </div>
        </nav>

        {/* ═══ 子栏右 · 选中伏笔卡 ═══ */}
        <div className="hk-main">
          {selected ? (
            <div data-od-id="hook-card">
              <div className="hk-sec-label" style={{ marginTop: 0 }}>
                伏笔卡
                <span className="hk-kv-static num">{selected.code}</span>
                <span className={`hk-sl-tag ${stateTagCls}`}>{GROUP_LABEL[selected.status]}</span>
              </div>
              <div className="hk-kv" data-od-id="kv-hook">
                <div className="hk-kv-row hk-span2">
                  <span className="hk-kv-k">
                    伏笔描述<i className="req">必填</i>
                  </span>
                  <textarea
                    ref={descInputRef}
                    className="textarea"
                    rows={2}
                    maxLength={DESCRIPTION_MAX}
                    data-od-id="input-hook-desc"
                    placeholder="埋了什么钩子、读者会记挂什么。例：父亲失踪前塞给林拾的半页残卷——缺的半页在哪？"
                    value={selected.description}
                    onChange={(e) => setField("description", e.target.value)}
                  />
                </div>
                <div className="hk-kv-row">
                  <span className="hk-kv-k">引入章节</span>
                  <select
                    ref={inSelectRef}
                    className="input"
                    data-od-id="select-hook-in"
                    aria-label="引入章节"
                    value={selected.introduced_chapter_id ?? ""}
                    onChange={(e) => setField("introduced_chapter_id", e.target.value || null)}
                  >
                    {chapterOptions(selected.introduced_chapter_id)}
                  </select>
                </div>
                {selected.status !== "resolved" && (
                  <div className="hk-kv-row">
                    <span className="hk-kv-k">
                      计划收束<span className="hk-kv-hint">章未建可先留空</span>
                    </span>
                    <select
                      ref={planSelectRef}
                      className="input"
                      data-od-id="select-hook-plan"
                      aria-label="计划收束章节"
                      value={selected.planned_chapter_id ?? ""}
                      onChange={(e) => setField("planned_chapter_id", e.target.value || null)}
                    >
                      <option value="">选章节（章未建可先留空）</option>
                      {chapterOptions(selected.planned_chapter_id)}
                    </select>
                  </div>
                )}
                <div className="hk-kv-row">
                  <span className="hk-kv-k">类型</span>
                  <select
                    className="input"
                    data-od-id="select-hook-type"
                    aria-label="伏笔类型"
                    value={selected.type}
                    onChange={(e) => setField("type", e.target.value)}
                  >
                    {HOOK_TYPES.map((t) => (
                      <option key={t.k} value={t.k}>
                        {t.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="hk-kv-row">
                  <span className="hk-kv-k">优先级</span>
                  <div className="hk-cap-row" data-od-id="seg-hook-priority" role="group" aria-label="优先级">
                    {[1, 2, 3].map((pri) => (
                      <button
                        key={pri}
                        type="button"
                        className={`cap cap-sm${selected.priority === pri ? " on" : ""}`}
                        onClick={() => setField("priority", pri)}
                      >
                        {priorityLabel(pri)}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="hk-kv-row">
                  <span className="hk-kv-k">状态</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="hk-cap-row" data-od-id="seg-hook-state" role="group" aria-label="状态">
                      {HOOK_STATUSES.map((s) => (
                        <button
                          key={s}
                          type="button"
                          className={`cap cap-sm${selected.status === s ? " on" : ""}`}
                          onClick={() => switchStatus(s as HookStatusValue)}
                        >
                          {GROUP_LABEL[s as HookStatusValue]}
                        </button>
                      ))}
                    </div>
                    <p className="hk-seg-note">
                      {selected.status === "resolved"
                        ? "已收束的还留着收束记录——改错章随时改回来。"
                        : selected.status === "abandoned"
                          ? "废弃＝不再收束；移回「活跃」可重新埋。"
                          : "切换后这条伏笔会移到对应分组；移错随时切回来（收束记录保留不清）。"}
                    </p>
                  </div>
                </div>
              </div>

              {/* 收束记录：已收束态展开；h2 有结果时对活跃条目也展开（结果落收束记录区）。
                  软引导留痕，不硬拦保存与确认 */}
              {selected.status === "resolved" && (
                <div data-od-id="kv-hook-payoff">
                  <div className="hk-sec-label" style={{ marginTop: 16 }}>
                    收束记录
                    <span className="hk-sl-tag">
                      {selected.status === "resolved" ? "建议留痕" : "拟收束方案待采纳"}
                    </span>
                  </div>
                  <div className="hk-kv">
                    <div className="hk-kv-row">
                      <span className="hk-kv-k">收束章节</span>
                      <select
                        ref={outSelectRef}
                        className="input"
                        data-od-id="select-hook-out"
                        aria-label="收束章节"
                        value={selected.resolved_chapter_id ?? ""}
                        onChange={(e) => setField("resolved_chapter_id", e.target.value || null)}
                      >
                        <option value="">选收束章节（可后补）</option>
                        {chapterOptions(selected.resolved_chapter_id)}
                      </select>
                    </div>
                    <div className="hk-kv-row hk-span2">
                      <span className="hk-kv-k">怎么收的</span>
                      <textarea
                        ref={howInputRef}
                        className="textarea"
                        rows={2}
                        maxLength={PAYOFF_NOTE_MAX}
                        data-od-id="input-hook-how"
                        placeholder="一句留痕：读者在哪一刻对上了。例：通缉令笔迹与赵执事批过的名录对上——林拾当场没声张。"
                        value={selected.payoff_note}
                        onChange={(e) => setField("payoff_note", e.target.value)}
                      />
                    </div>
                  </div>
                  {/* h2 拟收束方案改走弹窗出卡（c-settings-ai-confirm-modal）：
                      已有收束记录 → 卡内确认键转「覆盖并收束」（警示级，不加二次弹窗） */}
                  {!selected.payoff_note.trim() && (
                    <p className="opt" style={{ marginTop: 8 }}>
                      这条已收束但没留痕——补一句「怎么收的」，埋坑体检会一直点名提醒。
                    </p>
                  )}
                </div>
              )}

              {selected.status === "abandoned" && (
                <p className="opt" style={{ marginTop: 12 }}>
                  废弃＝不再收束。移回「活跃」可重新埋。
                </p>
              )}

              <div className="hk-del-row">
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  data-od-id="btn-del-hook"
                  onClick={() => void doDelete()}
                >
                  <Ico d={P.trash} sw={1.7} size={13} /> 删除这条伏笔
                </button>
                <span className="hk-del-hint">删除后 8 秒内可点撤销——按原编号原样找回。</span>
              </div>
            </div>
          ) : items.length > 0 ? (
            /* 有伏笔但未选中：轻空态 */
            <div className="hk-empty slim" data-od-id="empty-hook-selection">
              <p className="se-t">在左侧选一条伏笔</p>
              <p className="se-s">或点「添加伏笔」新埋一条。</p>
            </div>
          ) : (
            /* 空态：主动作＋旁路（旁路＝「编辑区零 AI 按钮」唯一例外，随门控矩阵走） */
            <div className="hk-empty" data-od-id="empty-hooks">
              <Ico d={P.info} size={34} className="se-ico" />
              <p className="se-t">还没有伏笔</p>
              <p className="se-s">
                想到就记一条：埋了什么、打算哪章还。
                <br />
                写正文时回来埋一样算数——但确认「伏笔」前至少要埋一条。
              </p>
              <button type="button" className="btn btn-secondary" data-od-id="btn-empty-add" onClick={addHook}>
                <Ico d={P.plus} size={13} /> 添加伏笔
              </button>
              <p className="opt" style={{ marginTop: 10 }}>
                或者{" "}
                <button
                  type="button"
                  className="text-btn"
                  data-od-id="btn-empty-ai"
                  onClick={() => {
                    if (aiState && aiState !== "ready") {
                      onBlocked?.(aiState);
                      return;
                    }
                    void runAi("h1");
                  }}
                >
                  让 AI 从简介＋主线起草几条候选
                </button>
                。
              </p>
            </div>
          )}

          {/* AI 结果统一进弹窗出卡（c-settings-ai-confirm-modal）：编辑区零 AI 按钮 */}
        </div>
      </div>

      {/* 采纳回执（面板内自管）：精确撤销只回滚本次采纳，8 秒自清 */}
      {aiReceipt && (
        <div className="hk-receipt" data-od-id="receipt-hooks-ai" role="status" aria-live="polite">
          <span>{aiReceipt.text}</span>
          <button type="button" className="hk-receipt-undo" onClick={() => void undoAdopt()}>
            撤销
          </button>
        </div>
      )}

      {/* 回执：面板内自管（不经 SettingsView 回执通道），最近一条，8 秒自清 */}
      {receipt && (
        <div className="hk-receipt" data-od-id="receipt-hooks" role="status" aria-live="polite">
          <span>{receipt.text}</span>
          <button type="button" className="hk-receipt-undo" onClick={() => void doUndo()}>
            撤销
          </button>
        </div>
      )}

      {/* AI 出卡确认弹窗：四行共用（关闭即弃；缓存重开免请求；报告行跳转＝关卡＋聚焦，
          走 skipRestore 防 Modal 焦点还原抢走聚焦，D6） */}
      <AiCardModal
        open={cardOpen && cardAction !== null}
        card={
          cardAction === "h1" && draftSinks
            ? {
                label: "AI 填 · 起草伏笔（勾选后采纳）",
                kind: "pick",
                adoptText: "采纳所选 · 加入活跃",
                cached: cardCached,
                canAdopt: draftSinks.checked.some(Boolean),
                node: (
                  <>
                    {draftSinks.candidates.map((c, i) => (
                      <label className="cand" key={i} data-testid="hook-candidate" data-od-id="hook-candidate">
                        <input
                          type="checkbox"
                          checked={draftSinks.checked[i] ?? true}
                          onChange={(e) =>
                            setDraftSinks({
                              ...draftSinks,
                              checked: draftSinks.checked.map((v, k) =>
                                k === i ? e.target.checked : v,
                              ),
                            })
                          }
                        />
                        <span>
                          <span className="c-tag">
                            候选 {i + 1} · {typeLabel(c.type)} · {priorityLabel(c.priority)}
                          </span>
                          {c.description}
                        </span>
                      </label>
                    ))}
                    <span className="aa-note" data-testid="hook-adopt-count" data-od-id="hook-adopt-count">
                      将加入 {draftSinks.checked.filter(Boolean).length} 条
                    </span>
                  </>
                ),
                adopt: () => void adoptCandidates(draftSinks),
              }
            : cardAction === "h2" && payoffSink
              ? {
                  label: `AI 填 · 拟收束方案（对 ${payoffSink.code} 生效）`,
                  kind: "struct",
                  cached: cardCached,
                  node: (
                    <div>
                      <p className="cand" style={{ margin: "0 0 6px" }}>
                        <span className="c-tag">建议收束章 {payoffSink.resolvedChapterRef}</span>
                        {payoffSink.payoffNote}
                      </p>
                      {(items.find((h) => h.id === payoffSink.hookId)?.resolved_chapter_id ||
                        items.find((h) => h.id === payoffSink.hookId)?.payoff_note.trim()) && (
                        <span className="aa-note">已有收束记录——采纳将覆盖它（可撤销）</span>
                      )}
                    </div>
                  ),
                  adoptText: (() => {
                    const cur = items.find((h) => h.id === payoffSink.hookId);
                    return cur?.resolved_chapter_id || cur?.payoff_note.trim()
                      ? "覆盖并收束"
                      : "采纳 · 写入收束记录";
                  })(),
                  adopt: () => void adoptPayoff(payoffSink),
                }
              : cardAction === "h3" && auditSinks
                ? {
                    label: auditSinks.degraded ? "AI 体检 · 埋坑体检（纯台账自检）" : "AI 体检 · 埋坑体检",
                    kind: "report",
                    cached: cardCached,
                    node: (
                      <>
                        {auditSinks.degraded && (
                          <p className="opt" style={{ margin: "0 0 6px" }}>
                            {auditSinks.degradedReasons.join("、")}
                            {auditSinks.verdict ? `——${auditSinks.verdict}` : "——只提醒不拦确认"}
                          </p>
                        )}
                        {auditSinks.checks.map((c) => {
                          const hook = items.find((h) => h.id === c.hook_id);
                          const labelOf = (x: HookAuditCheck) =>
                            x.status === "ok"
                              ? "在期"
                              : x.status === "miss"
                                ? "超期"
                                : x.goto_field === "payoff"
                                  ? "无留痕"
                                  : "未定期";
                          return (
                            <button
                              type="button"
                              key={c.hook_id}
                              className="chk-line click"
                              data-testid="audit-row"
                              data-od-id="audit-row"
                              data-hook-id={c.hook_id}
                              onClick={() => {
                                // 跳转出口：关卡（跳过焦点还原）＋选中聚焦（D6）
                                cardSkipRestoreRef.current = true;
                                setCardOpen(false);
                                jumpToHook(c.hook_id, c.goto_field);
                              }}
                            >
                              <span className="chk-name">
                                {c.code}
                                {hook?.description ? ` ${hook.description.slice(0, 10)}` : ""}
                              </span>
                              <span className={`chk-res ${c.status}`}>{labelOf(c)}</span>
                              <span className="chk-note">{c.note}</span>
                            </button>
                          );
                        })}
                        {!auditSinks.degraded && auditSinks.checks.length > 0 && (
                          <p className="opt" style={{ margin: "8px 0 0", fontSize: 11.5 }}>
                            只提醒不拦确认
                            {auditSinks.checks.some((c) => c.goto_field)
                              ? "；点一行可跳去对应伏笔补填"
                              : ""}
                            。
                          </p>
                        )}
                      </>
                    ),
                  }
                : cardAction === "h4" && checkSink
                  ? {
                      label: checkSink.degraded
                        ? "AI 体检 · 查一致性（输入不全）"
                        : "AI 体检 · 查一致性",
                      kind: "report",
                      cached: cardCached,
                      node: (
                        <>
                          {checkSink.degraded && (
                            <p className="opt" style={{ margin: "0 0 6px" }}>
                              {checkSink.degradedReasons.join("、")}
                              {checkSink.verdict ? `——${checkSink.verdict}` : "——只提醒不拦确认"}
                            </p>
                          )}
                          {checkSink.checks.map((c) => (
                            <button
                              type="button"
                              key={c.name}
                              className="chk-line click"
                              data-testid="check-row"
                              data-od-id="check-row"
                              data-check={c.name}
                              onClick={() => {
                                // 跳回这条伏笔的描述改：关卡（跳过焦点还原）＋聚焦描述字段
                                cardSkipRestoreRef.current = true;
                                setCardOpen(false);
                                if (selectedIdRef.current !== checkSink.hookId) {
                                  if (timerRef.current) window.clearTimeout(timerRef.current);
                                  void flushQueue().then(() => {
                                    selectedIdRef.current = checkSink.hookId;
                                    setSelectedId(checkSink.hookId);
                                    window.setTimeout(() => {
                                      descInputRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
                                      descInputRef.current?.focus();
                                    }, 60);
                                  });
                                  return;
                                }
                                window.setTimeout(() => {
                                  descInputRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
                                  descInputRef.current?.focus();
                                }, 0);
                              }}
                            >
                              <span className="chk-name">{c.name}</span>
                              <span className={`chk-res ${c.status}`}>
                                {c.status === "ok" ? "达标" : c.status === "warn" ? "风险" : "对不上"}
                              </span>
                              <span className="chk-note">{c.note}</span>
                            </button>
                          ))}
                          <p className="opt" style={{ margin: "8px 0 0", fontSize: 11.5 }}>
                            风险不拦确认；点一行跳回这条伏笔的描述改。
                          </p>
                        </>
                      ),
                    }
                  : null
        }
        running={aiRunning !== null}
        error={aiRunning === null ? cardError : undefined}
        version={cardAction ? versions[cardAction] : undefined}
        onClose={() => setCardOpen(false)}
        onRegenerate={cardAction ? () => void runRequest(cardAction) : undefined}
        skipRestoreRef={cardSkipRestoreRef}
        data-testid="hooks-ai-card"
      />
    </div>
  );
});

export default HooksSettingForm;
