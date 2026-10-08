// 角色面板（character-settings-v2）：真表 API + 分组列表 + 卷宗人物卡 + 单向关系
// + 删除/合并（L3 名称输入确认）+ 单格自动保存（防抖 + 串行队列 + rev 冲突 409 处理）
// + 右栏 AI 经 SettingsView 分发（本组件暴露 runAi/clearAi 句柄）；出稿/体检统一进 AiCardModal 弹窗（c-settings-ai-confirm-modal）。
// + 首次进入引导与「从简介立主角」（character-bootstrap-from-intro：出稿采纳走既有单格写入）。
// + 整项确认口径（c-chars-confirm-scope）：门禁缺口经 onGateHintChange 上抛给页脚提示；
//   卡片级保存态归位卡头（「这张卡…」），与整项口径分开。
import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { charactersApi, BootstrapDraft, CharacterCard } from "@/lib/charactersApi";
import {
  COG_FIELD_HINTS,
  COG_FILL_KEYS,
  COG_LEVEL_HINTS,
  COG_LAYERS,
  DOSSIER_FIELDS,
  DOSSIER_FILL_KEYS,
  displayName,
  GATE_FIELDS,
  ROLES,
  type CharAiCtx,
} from "@/lib/characterModel";
import { Ico } from "@/components/icons";
import AiCardModal from "./AiCardModal";
import type { AiState } from "@/types/api-config";

interface Props {
  projectId: string;
  /** P2-1：脏状态回调（有未落库修改时 true） */
  onDirtyChange?: (dirty: boolean) => void;
  /** 选中卡变化时上报（右栏四行提示与缺口计数的数据源） */
  onCtxChange?: (ctx: CharAiCtx | null) => void;
  /** 01 简介是否已填（readiness settingsStatus.synopsis）——空态引导卡的分路判据 */
  introReady?: boolean;
  /** 本书 AI 就绪态（D13）：空态引导按钮与右栏行同一门控；不 ready 时点击走 onBlocked */
  aiState?: AiState;
  onBlocked?: (reason: AiState) => void;
  /** 整项确认门禁缺口（c-chars-confirm-scope）：列表载入成功后上报，未载入/载入失败报 null
   *  （页脚据此回落通用提示，不冒充「书里没有主角」） */
  onGateHintChange?: (hint: CharGateHint | null) => void;
  /** 面板数据刷新＝确认存档可能过期（c-chars-stale-reconfirm）：请父层重取确认存档状态。
   *  挂载（进入面板）、单卡保存落库、增删合并后都会走到这里。 */
  onRefreshConfirmState?: () => void;
}

export interface CharacterSaveHandle {
  save: () => Promise<boolean>;
  /** 兼容 SettingSaveHandle 可选成员 */
  clearAi?: () => void;
  runAi?: (key: string) => Promise<void>;
}

/** 整项确认门禁的缺口摘要（c-chars-confirm-scope）——页脚提示与主按钮同一档位口径：
 *  未确认＝第一次确认档（只看主角名称/一句话人设），已确认＝此后档（全书卡扫六项）。 */
export interface CharGateHint {
  /** 书里还没有主角卡（两档的共同前置） */
  noProtagonist: boolean;
  /** 第一次确认档缺的项（空数组＝这一档可过） */
  protagonistMissing: string[];
  /** 主角显示名（点名用；无主角卡时为空串） */
  protagonistName: string;
  /** 此后确认档的缺口卡：主角 + 每张非路人卡六项、路人卡只剧情定位（缺口头由服务端列表下发） */
  gapCards: { role: string; name: string; fields: string[] }[];
}

/** 门禁摘要（纯函数）：缺口取服务端列表下发的 gaps；首档判据＝名称/人设（后端 FIRST_CONFIRM_REQUIRED 同源，
 *  标签仍从 GATE_FIELDS 取，不手抄第二份词表）。 */
export function gateHintOf(list: CharacterCard[], noProtagonist: boolean): CharGateHint {
  const prot = list.find((c) => c.role === "主角");
  const label = (k: string) => GATE_FIELDS.find(([p]) => p === k)?.[1] ?? k;
  const protagonistMissing: string[] = [];
  if (prot) {
    if (!displayName(prot.name)) protagonistMissing.push(label("name"));
    if (!prot.persona.trim()) protagonistMissing.push(label("persona"));
  }
  return {
    noProtagonist,
    protagonistMissing,
    protagonistName: prot ? displayName(prot.name) : "",
    gapCards: list
      .filter((c) => (c.gaps ?? []).length > 0)
      .map((c) => ({ role: c.role, name: displayName(c.name), fields: c.gaps ?? [] })),
  };
}

type SaveState = "saved" | "saving" | "dirty" | "failed";

interface AiDraft {
  target?: string;
  cells: { path: string; value: string }[];
  skipped?: { key: string; why: string }[];
  act: "insert" | "replace";
}

interface CheckResult {
  items: { name: string; status: "ok" | "warn" | "conflict" | "miss"; note: string; goto?: string }[];
  degraded: boolean;
  degraded_reasons: string[];
  verdict: string;
}

const GROUPS = ROLES;

/** 出稿到采纳之间作者可能已手写——逐格以当前卡内容复查，只写空格（纯函数） */
function cellStillEmpty(cardLike: CharacterCard, path: string): boolean {
  const [bucket, key] = path.split(".") as ["dossier" | "cog", string];
  return !String(cardLike[bucket]?.[key] ?? "").trim();
}

const CharacterManager = forwardRef<CharacterSaveHandle, Props>(function CharacterManager(
  props,
  ref,
) {
  const {
    projectId, onDirtyChange, onCtxChange, introReady, aiState, onBlocked, onGateHintChange,
    onRefreshConfirmState,
  } = props;
  const [list, setList] = useState<CharacterCard[]>([]);
  const [gate, setGate] = useState<{ ok: boolean; no_protagonist: boolean; confirmed: boolean }>({
    ok: false, no_protagonist: true, confirmed: false,
  });
  /** 列表是否已成功载入（c-chars-confirm-scope 评审补丁）：未载入/载入失败时不上报门禁摘要——
   *  初值 gate.no_protagonist=true 是「还不知道」，直接上报会把空列表当成「书里没有主角」。 */
  const [listLoaded, setListLoaded] = useState(false);
  const [selectedId, setSelectedId] = useState("");
  const [card, setCard] = useState<CharacterCard | null>(null);
  const [groupsOpen, setGroupsOpen] = useState<Record<string, boolean>>({
    "\u4e3b\u89d2": true, "\u914d\u89d2": true, "\u53cd\u6d3e": true, "\u8def\u4eba": false,
  });
  const [query, setQuery] = useState("");
  const [saveState, setSaveState] = useState<SaveState>("saved");
  const [opsPanel, setOpsPanel] = useState<"" | "del" | "merge">("");
  const [opsName, setOpsName] = useState("");
  const [mergeTarget, setMergeTarget] = useState("");
  const [cogOpen, setCogOpen] = useState<Record<string, boolean>>({});
  const [relForm, setRelForm] = useState(false);
  const [relDraft, setRelDraft] = useState({ other: "", rel_type: "\u540c\u76df", stance: "", note: "" });
  const [sink, setSink] = useState<AiDraft | null>(null);
  /** 最近一次出稿的能力（缓存命中判定：重开同一行展示缓存不再发请求，D9） */
  const [sinkAction, setSinkAction] = useState<"persona" | "dossier" | "cog" | null>(null);
  /** 「从简介立主角」出稿（character-bootstrap-from-intro）：出稿过目，采纳才写入；
      c-char-ai-card-generic 起同一槽位兼收配角/反派「一键立卡」稿（bootstrapKind 区分来路） */
  const [bootstrapSink, setBootstrapSink] = useState<BootstrapDraft | null>(null);
  const [bootstrapKind, setBootstrapKind] = useState<"bootstrap" | "cardDraft">("bootstrap");
  const [check, setCheck] = useState<CheckResult | null>(null);
  // AI 出卡确认弹窗（c-settings-ai-confirm-modal）：出稿/体检统一进弹窗，内嵌预览块退役
  const [cardAction, setCardAction] = useState<"persona" | "dossier" | "cog" | "bootstrap" | "cardDraft" | "check" | null>(null);
  const aiBusyRef = useRef(false); // ref 同步判定：同一 tick 连点不穿透
  const [versions, setVersions] = useState<Partial<Record<"persona" | "dossier" | "cog" | "bootstrap" | "cardDraft" | "check", number>>>({});
  const [cardOpen, setCardOpen] = useState(false);
  const [cardCached, setCardCached] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [toast, setToast] = useState("");
  /** 删除/合并后的撤销句柄（后端 ops token），随下一次操作或刷新消失 */
  const [undoOp, setUndoOp] = useState<{ opId: string } | null>(null);

  const queueRef = useRef<{ path: string; value: unknown }[]>([]);
  const runningRef = useRef(false);
  const revRef = useRef(1);
  const timerRef = useRef<number | null>(null);
  const selectedIdRef = useRef("");
  const [dirty, setDirty] = useState(false);
  const markDirty = useCallback(() => setDirty(true), []);
  const clearDirty = useCallback(() => setDirty(false), []);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(""), 2600);
  }, []);

  const reloadList = useCallback(async (): Promise<CharacterCard[]> => {
    const data = await charactersApi.list(projectId);
    setList(data.items);
    setGate({ ok: data.gate.ok, no_protagonist: data.gate.no_protagonist, confirmed: data.confirmed });
    setListLoaded(true); // 只有真拿到列表才放行门禁摘要（失败路径保持静默，见 listLoaded 声明处）
    onRefreshConfirmState?.(); // 数据已刷新＝存档可能过期：请父层重取（c-chars-stale-reconfirm）
    return data.items;
  }, [projectId, onRefreshConfirmState]);

  const loadCard = useCallback(async (id: string) => {
    const full = await charactersApi.get(projectId, id);
    setCard(full);
    revRef.current = full.rev;
    setSaveState("saved");
    clearDirty();
    onDirtyChange?.(false);
    setSink(null);
    setCheck(null);
    // 出稿槽随卡清：bootstrapSink 泛化收配角/反派「一键立卡」稿后不清会把 A 卡的稿
    // 借给 B 卡当缓存（评审 P2）——主角待立时代只有一张卡，这条不存在
    setBootstrapSink(null);
    setBootstrapKind("bootstrap");
    setCardOpen(false); // 换卡＝弹窗随结果一起清（D9 缓存面板级寿命）
    setVersions({}); // 版数随卡复位：新卡首稿是「第 1 版」，不带上一张卡的计数
  }, [projectId, clearDirty, onDirtyChange]);

  // 右栏 AI 作用域随卡走：加载与每次字段编辑都重报（一键立卡行门控吃 role/缺口，
  // 卡上切类型、填格后行与「当前角色」行须即时进退——c-char-ai-card-generic）
  useEffect(() => {
    if (!card) return;
    onCtxChange?.({
      name: displayName(card.name) || "未命名",
      nameless: !displayName(card.name),
      code: card.code,
      role: card.role,
      personaGap: card.persona.trim() ? 0 : 1,
      dossierGap: DOSSIER_FILL_KEYS.filter((k) => !(card.dossier[k] ?? "").trim()).length,
      cogGap:
        card.role === "路人"
          ? 0
          : COG_FILL_KEYS.filter((k) => !(card.cog[k] ?? "").trim()).length,
    });
  }, [card, onCtxChange]);

  useEffect(() => {
    setListLoaded(false); // 换书重取：旧书的缺口摘要不得借道新书的首帧（评审补丁）
    (async () => {
      try {
        const items = await reloadList();
        if (items.length) {
          selectedIdRef.current = items[0].id;
          setSelectedId(items[0].id);
          await loadCard(items[0].id);
        }
      } catch {
        showToast("\u89d2\u8272\u52a0\u8f7d\u5931\u8d25\uff0c\u8bf7\u5237\u65b0\u91cd\u8bd5");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  // 整项确认门禁缺口上报（c-chars-confirm-scope）：页脚提示的数据源。
  // 列表在单卡保存落库后会重取（reloadList），缺口因此天然新鲜；
  // 未载入/载入失败时上报 null（页脚回落通用提示）——空列表不等于「书里没有主角」（评审补丁）。
  const gateHint = useMemo(
    () => (listLoaded ? gateHintOf(list, gate.no_protagonist) : null),
    [listLoaded, list, gate.no_protagonist],
  );
  useEffect(() => {
    onGateHintChange?.(gateHint);
  }, [gateHint, onGateHintChange]);

  const flushQueue = useCallback(async () => {
    if (runningRef.current || queueRef.current.length === 0 || !card) return;
    runningRef.current = true;
    setSaveState("saving");
    try {
      while (queueRef.current.length > 0) {
        const next = queueRef.current.shift()!;
        await charactersApi.patch(projectId, card.id, next.path, next.value, revRef.current);
        revRef.current += 1;
      }
      setSaveState("saved");
      clearDirty();
      onDirtyChange?.(false);
      // 落库后同步左侧分组列表：身份/名字/别名只写在卡上不刷列表的话，
      // 归组与行名要作家整页刷新才变（配角改反派滞留旧组的老毛病）
      try {
        await reloadList();
      } catch {
        // 列表同步失败不翻保存态：格已落库，下次保存或重进角色页会再刷
      }
    } catch (e) {
      const err = e as Error & { status?: number; field?: string; rev?: number };
      if (err.status === 409 && err.rev !== undefined) {
        revRef.current = err.rev;
        setSaveState("dirty");
        showToast("\u8fd9\u4e00\u683c\u5df2\u88ab\u5176\u5b83\u6539\u52a8\u66f4\u65b0\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5");
      } else {
        setSaveState("failed");
        showToast("\u81ea\u52a8\u4fdd\u5b58\u5931\u8d25\u2014\u2014\u8bf7\u68c0\u67e5\u7f51\u7edc\u540e\u91cd\u8bd5");
      }
    } finally {
      runningRef.current = false;
      if (queueRef.current.length > 0) void flushQueue();
    }
  }, [card, projectId, clearDirty, onDirtyChange, showToast, reloadList]);

  const enqueue = useCallback(
    (path: string, value: unknown) => {
      queueRef.current = queueRef.current.filter((p) => p.path !== path);
      queueRef.current.push({ path, value });
      markDirty();
      onDirtyChange?.(true);
      setSaveState("dirty");
      if (timerRef.current) window.clearTimeout(timerRef.current);
      timerRef.current = window.setTimeout(() => void flushQueue(), 600);
    },
    [flushQueue, markDirty, onDirtyChange],
  );

  const setField = useCallback(
    (path: string, value: unknown) => {
      setCard((prev) => {
        if (!prev) return prev;
        const next: CharacterCard = { ...prev };
        if (path.includes(".")) {
          const [bucket, key] = path.split(".") as ["dossier" | "cog", string];
          next[bucket] = { ...prev[bucket], [key]: String(value) };
        } else {
          (next as unknown as Record<string, unknown>)[path] = value;
        }
        return next;
      });
      enqueue(path, value);
    },
    [enqueue],
  );

  useImperativeHandle(ref, () => ({
    save: async () => {
      if (timerRef.current) window.clearTimeout(timerRef.current);
      await flushQueue();
      return queueRef.current.length === 0 && saveState !== "failed";
    },
    clearAi: () => {
      setSink(null);
      setCheck(null);
      setBootstrapSink(null);
      setBootstrapKind("bootstrap");
      setCardAction(null);
      setCardOpen(false);
      setVersions({});
    },
    runAi: async (key: string) => {
      if (aiBusyRef.current) return;
      if (key === "bootstrap" || key === "cardDraft") {
        // 从简介立主角：允许无卡（空态）触发；主角待立时带当前卡 id（出稿只补空格）。
        // 一键立卡（c-char-ai-card-generic）：只挂在选中配角/反派卡的右栏行上，永远有卡。
        if (bootstrapSink && bootstrapKind === key) {
          setCardCached(true); // 重开＝展示缓存，不重复生成（D9）
          setCardAction(key);
          setCardOpen(true);
          return;
        }
        await runBootstrap(key);
        return;
      }
      if (key !== "persona" && key !== "dossier" && key !== "cog" && key !== "check") return;
      if (key === "check" && check) {
        setCardCached(true);
        setCardAction("check");
        setCardOpen(true);
        return;
      }
      if (key !== "check" && sink && sinkAction === key) {
        setCardCached(true);
        setCardAction(key);
        setCardOpen(true);
        return;
      }
      if (!card) return;
      aiBusyRef.current = true;
      setAiBusy(true);
      setCardAction(key as "persona" | "dossier" | "cog" | "check"); // 首跑先开弹窗给 loading 占位
      setCardOpen(true);
      const cardId = card.id;
      try {
        if (key === "check") {
          const res = await charactersApi.aiCheck(projectId, cardId);
          if (selectedIdRef.current === cardId) {
            setCheck(res);
            setCardCached(false);
            setCardAction("check");
            setCardOpen(true);
            setVersions((prev) => ({ ...prev, check: (prev.check ?? 0) + 1 }));
          }
        } else {
          const res = await charactersApi.aiDraft(projectId, cardId, key as "persona" | "dossier" | "cog");
          if (selectedIdRef.current === cardId) {
            setSink(res);
            setSinkAction(key);
            setCardCached(false);
            setCardAction(key);
            setCardOpen(true);
            setVersions((prev) => ({ ...prev, [key]: (prev[key] ?? 0) + 1 }));
          }
        }
      } catch (e) {
        // 走到请求＝该能力无缓存：失败关门走 toast（对齐 world fail-close），
        // 防空卡弹窗滞留（角色无 cardError 机制，弹窗内无错误体可显示）
        setCardOpen(false);
        showToast((e as Error).message || "AI \u751f\u6210\u5931\u8d25\uff0c\u53ef\u91cd\u8bd5");
      } finally {
        aiBusyRef.current = false;
        setAiBusy(false);
      }
    },
  }));

  const pick = useCallback(
    async (id: string) => {
      if (id === selectedIdRef.current) return;
      if (timerRef.current) window.clearTimeout(timerRef.current);
      await flushQueue();
      selectedIdRef.current = id;
      setSelectedId(id);
      setOpsPanel("");
      setRelForm(false);
      setCogOpen({});
      setBootstrapSink(null);
      await loadCard(id);
    },
    [flushQueue, loadCard],
  );

  const addCharacter = useCallback(async () => {
    try {
      // 首卡默认主角（character-bootstrap-from-intro）；之后添加仍默认配角
      const created = await charactersApi.create(projectId, "", { role: list.length === 0 ? "主角" : "配角" });
      await reloadList();
      selectedIdRef.current = created.id;
      setSelectedId(created.id);
      setOpsPanel("");
      setRelForm(false);
      await loadCard(created.id);
      showToast("\u540d\u5b57\u4e00\u5199\u5c31\u51fa\u73b0\u5728\u5de6\u8fb9\u5217\u8868");
    } catch (e) {
      showToast((e as Error).message || "\u521b\u5efa\u5931\u8d25");
    }
  }, [projectId, list.length, reloadList, loadCard, showToast]);

  const adoptSink = useCallback(async () => {
    if (!sink || !card) return;
    // 逐格采纳：以服务端返回的 rev 为准（本地 +1 会与真实版本脱钩）；
    // 单格 409 不整批中止——重同步 rev 后跳过该格继续，结果逐格汇报
    let applied = 0;
    const skipped: string[] = [];
    try {
      for (const cell of sink.cells) {
        try {
          const { rev } = await charactersApi.patch(
            projectId, card.id, cell.path, cell.value, revRef.current,
          );
          revRef.current = rev;
          applied += 1;
        } catch (e) {
          const err = e as Error & { status?: number; rev?: number };
          if (err.status === 409 && err.rev !== undefined) {
            revRef.current = err.rev;
            skipped.push(cell.path);
            continue;
          }
          throw e;
        }
      }
      setSink(null); // 采纳即作废旧稿（只补空格的稿采纳后无二次价值）：重开会重新出稿，D9 的缓存例外
      setCardOpen(false); // 确认写回＝弹窗自动关
      await loadCard(card.id);
      await reloadList();
      showToast(
        skipped.length
          ? `\u5df2\u91c7\u7eb3 ${applied} \u683c\uff1b${skipped.length} \u683c\u51b2\u7a81\u8df3\u8fc7\uff08\u8bf7\u624b\u52a8\u6838\u5bf9\uff09`
          : "\u5df2\u91c7\u7eb3\uff0c\u53ef\u7ee7\u7eed\u6539",
      );
    } catch (e) {
      showToast((e as Error).message || "\u91c7\u7eb3\u5931\u8d25\uff0c\u8bf7\u91cd\u8bd5");
    }
  }, [sink, card, projectId, loadCard, reloadList, showToast]);

  /** 采纳「从简介立主角」草稿：空态=建主角卡+逐格补写；主角待立=只补空格（含名字/别名/人设） */
  const adoptBootstrap = useCallback(async () => {
    if (!bootstrapSink) return;
    const draft = bootstrapSink;
    try {
      if (timerRef.current) window.clearTimeout(timerRef.current);
      await flushQueue();
      if (card) {
        const steps: { path: string; value: unknown }[] = [];
        if (!displayName(card.name) && draft.name) steps.push({ path: "name", value: draft.name });
        if (!card.aliases.length && draft.aliases.length)
          steps.push({ path: "aliases", value: draft.aliases });
        if (!card.persona.trim() && draft.persona) steps.push({ path: "persona", value: draft.persona });
        steps.push(...draft.cells.filter((c) => cellStillEmpty(card, c.path)));
        for (const s of steps) {
          await charactersApi.patch(projectId, card.id, s.path, s.value, revRef.current);
          revRef.current += 1;
        }
        setBootstrapSink(null);
        setCardOpen(false);
        await loadCard(card.id);
        await reloadList();
      } else {
        if (bootstrapKind === "cardDraft") return; // 一键立卡不建卡（行只在有卡时出现）
        const created = await charactersApi.create(projectId, draft.name, { role: "主角" });
        selectedIdRef.current = created.id;
        setSelectedId(created.id);
        setOpsPanel("");
        setRelForm(false);
        await loadCard(created.id);
        const steps: { path: string; value: unknown }[] = [];
        if (draft.aliases.length) steps.push({ path: "aliases", value: draft.aliases });
        if (draft.persona) steps.push({ path: "persona", value: draft.persona });
        steps.push(...draft.cells.filter((c) => cellStillEmpty(created, c.path)));
        for (const s of steps) {
          await charactersApi.patch(projectId, created.id, s.path, s.value, revRef.current);
          revRef.current += 1;
        }
        setBootstrapSink(null);
        setCardOpen(false);
        await loadCard(created.id);
        await reloadList();
      }
      showToast("\u5df2\u91c7\u7eb3\uff0c\u53ef\u7ee7\u7eed\u6539");
    } catch (e) {
      const err = e as Error & { status?: number; rev?: number };
      if (err.status === 409 && err.rev !== undefined) {
        // rev 冲突：同步到服务端 rev 并重取卡；草稿保留，可直接重试
        revRef.current = err.rev;
        if (card) await loadCard(card.id);
      }
      showToast((e as Error).message || "\u91c7\u7eb3\u5931\u8d25");
    }
  }, [bootstrapSink, bootstrapKind, card, projectId, flushQueue, loadCard, reloadList, showToast]);

  /** 空态引导卡入口与右栏行共用：门控（不 ready → onBlocked）后出稿；
      kind＝「从简介立主角」/ 配角/反派「一键立卡」（同一端点，后端按卡角色分派模板） */
  const runBootstrap = useCallback(async (kind: "bootstrap" | "cardDraft" = "bootstrap") => {
    if (aiBusyRef.current) return; // ref 同步判定（与 runAi 同锁）
    if (kind === "cardDraft" && !card) return; // 一键立卡只挂在有卡上下文
    if (aiState && aiState !== "ready") {
      onBlocked?.(aiState);
      return;
    }
    aiBusyRef.current = true;
    setAiBusy(true);
    try {
      const res = await charactersApi.bootstrapDraft(projectId, card?.id || undefined);
      setSink(null);
      setCheck(null);
      setBootstrapSink(res);
      setBootstrapKind(kind);
      setCardCached(false);
      setCardAction(kind);
      setCardOpen(true);
      setVersions((prev) => ({ ...prev, [kind]: (prev[kind] ?? 0) + 1 }));
    } catch (e) {
      showToast((e as Error).message || "AI \u751f\u6210\u5931\u8d25\uff0c\u53ef\u91cd\u8bd5");
    } finally {
      aiBusyRef.current = false;
      setAiBusy(false);
    }
  }, [aiBusy, aiState, onBlocked, card, projectId, showToast]);

  const doDelete = useCallback(async () => {
    if (!card) return;
    try {
      const res = await charactersApi.remove(projectId, card.id);
      await reloadList();
      const rest = (await charactersApi.list(projectId)).items;
      if (rest.length) {
        selectedIdRef.current = rest[0].id;
        setSelectedId(rest[0].id);
        await loadCard(rest[0].id);
      } else {
        setCard(null);
        onCtxChange?.(null);
      }
      setOpsPanel("");
      setUndoOp({ opId: res.undo.op_id });
      showToast(res.receipt);
    } catch (e) {
      showToast((e as Error).message || "\u5220\u9664\u5931\u8d25");
    }
  }, [card, projectId, reloadList, loadCard, showToast]);

  const doMerge = useCallback(async () => {
    if (!card || !mergeTarget) return;
    try {
      const res = await charactersApi.merge(projectId, card.id, mergeTarget);
      await reloadList();
      selectedIdRef.current = mergeTarget;
      setSelectedId(mergeTarget);
      await loadCard(mergeTarget);
      setOpsPanel("");
      setUndoOp({ opId: res.undo.op_id });
      showToast(res.receipt);
    } catch (e) {
      showToast((e as Error).message || "\u5408\u5e76\u5931\u8d25");
    }
  }, [card, mergeTarget, projectId, reloadList, loadCard, showToast]);

  const doUndo = useCallback(async () => {
    if (!undoOp) return;
    try {
      await charactersApi.undo(projectId, undoOp.opId);
      setUndoOp(null);
      const items = (await charactersApi.list(projectId)).items;
      await reloadList();
      const first = items[0];
      if (first) {
        selectedIdRef.current = first.id;
        setSelectedId(first.id);
        await loadCard(first.id);
      } else {
        setCard(null);
        onCtxChange?.(null);
      }
      showToast("\u5df2\u64a4\u9500\uff0c\u89d2\u8272\u5df2\u627e\u56de");
    } catch (e) {
      showToast((e as Error).message || "\u64a4\u9500\u5931\u8d25");
    }
  }, [undoOp, projectId, reloadList, loadCard, showToast, onCtxChange]);

  const q = query.trim();
  const grouped = GROUPS.map((role) => ({
    role,
    items: list.filter(
      (c) => c.role === role && (!q || c.name.includes(q) || c.aliases.some((a) => a.includes(q))),
    ),
  }));
  const sealChar = displayName(card?.name)?.trim()?.[0] ?? "\uff1f";

  /** 出稿逐格行（弹窗卡体内渲染；内嵌预览块词汇已退役） */
  const draftRows = (data: { cells: { path: string; value: string }[]; skipped?: { key: string; why: string }[] }) => (
    <>
      {data.cells.map((cell) => (
        <div key={cell.path} style={{ display: "flex", gap: 8, margin: "5px 0", alignItems: "baseline" }}>
          <span style={{ flex: "none", width: 108, fontSize: 12, color: "var(--muted)" }}>{cell.path}</span>
          <span style={{ minWidth: 0, fontSize: 12.5 }}>{cell.value}</span>
        </div>
      ))}
      {data.skipped?.map((s, i) => (
        <div key={`${s.key}-${i}`} className="opt">跳过 {s.key}：{s.why}</div>
      ))}
    </>
  );

  return (
    <div className="sub-wrap char-sub">
      <nav className="sub-list char-list" aria-label="角色列表">
        <div className="sub-list-head">
          角色列表
          <span style={{ marginLeft: "auto", fontSize: 10.5, color: "var(--muted)" }}>{list.length}</span>
        </div>
        <button type="button" className="char-add" onClick={() => void addCharacter()}>
          <Ico d="plus" size={13} /> 添加角色
        </button>
        <input
          className="char-search"
          type="search"
          placeholder="搜名字 / 别名"
          aria-label="搜索角色"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className="char-groups">
          {grouped.map(({ role, items }) =>
            q && !items.length ? null : (
              <div key={role} className={`char-group${groupsOpen[role] ? " open" : ""}`}>
                <button
                  type="button"
                  className="char-group-head"
                  onClick={() => setGroupsOpen((g) => ({ ...g, [role]: !g[role] }))}
                >
                  <span className="nm">{role}</span>
                  <span className="cnt">{items.length}</span>
                </button>
                {groupsOpen[role] && (
                  <div className="char-rows">
                    {items.map((c) => (
                      <button
                        key={c.id}
                        type="button"
                        className={`char-row-btn${selectedId === c.id ? " on" : ""}`}
                        onClick={() => void pick(c.id)}
                      >
                        <i className="char-ava">{displayName(c.name)?.[0] ?? "？"}</i>
                        <span className="char-row-main">
                          <span className="nm">{displayName(c.name) || "未命名"}</span>
                          <span className="sub num">
                            {c.first_chapter != null
                              ? `第 ${String(c.first_chapter).padStart(2, "0")} 章`
                              : "未出场"}
                          </span>
                        </span>
                        {c.role === "主角" && (!c.name || !c.persona) && (
                          <span className="pill pill-warn">待立</span>
                        )}
                      </button>
                    ))}
                    {!items.length && <span className="opt">空</span>}
                  </div>
                )}
              </div>
            ),
          )}
        </div>
      </nav>

      <div className="sub-form char-main">
        {!card ? (
          list.length === 0 ? (
            <div className="char-empty-guide" data-testid="char-empty-guide">
              <p className="guide-t">
                {introReady
                  ? "简介里已经有主角的线索了"
                  : "先去 01 简介写几句，主角就有了眉目"}
              </p>
              <p className="opt">
                「从简介立主角」会读你的简介，把名字、人设和各空格先拟一稿——在弹窗里看过再采纳；也可以直接手动建一张主角卡。
              </p>
              <div className="guide-act">
                {introReady && (
                  <button
                    type="button"
                    className="btn btn-primary"
                    data-testid="char-bootstrap"
                    disabled={aiBusy}
                    onClick={() => void runBootstrap()}
                  >
                    {aiBusy ? "AI 正在拟…" : "从简介立主角"}
                  </button>
                )}
                <button type="button" className="btn btn-secondary" onClick={() => void addCharacter()}>
                  手动建主角
                </button>
              </div>
            </div>
          ) : (
            <p className="opt">左侧添加或选择一个角色。</p>
          )
        ) : (
          <>
            <header className="char-head">
              <span className="char-seal">{sealChar}</span>
              <div className="char-idblock">
                <div className="char-name-row">
                  <input
                    className="char-name-input"
                    value={displayName(card.name)}
                    placeholder="姓名 / 称号"
                    aria-label="角色名称"
                    onChange={(e) => setField("name", e.target.value)}
                  />
                  <span role="group" aria-label="角色类型" style={{ display: "inline-flex", gap: 6 }}>
                    {ROLES.map((role) => (
                      <button
                        key={role}
                        type="button"
                        className={`chip${card.role === role ? " on" : ""}`}
                        onClick={() => setField("role", role)}
                      >
                        {role}
                      </button>
                    ))}
                  </span>
                </div>
                <input
                  className="char-alias-input"
                  value={card.aliases.join(" · ")}
                  placeholder="别名 / 称号（可选）"
                  aria-label="别名"
                  onChange={(e) =>
                    setField("aliases", e.target.value.split("·").map((s) => s.trim()).filter(Boolean))
                  }
                />
                <div className="char-meta num">
                  #{card.code} · 首次出场{" "}
                  {card.first_chapter != null
                    ? `第 ${String(card.first_chapter).padStart(2, "0")} 章`
                    : "未出场"}
                  {card.updated_at &&
                    ` · 更新于 ${card.updated_at.slice(5, 16).replace("T", " ")}`}
                </div>
              </div>
              <div className="char-side">
                {/* 卡片级保存态：与主角徽标/合并·删除同列（原型 ch-side），限定词「这张卡」
                    与页脚的整项口径分开——c-chars-confirm-scope */}
                <span className={`char-save-state ${saveState}`}>
                  {saveState === "saving" && "这张卡保存中…"}
                  {saveState === "saved" && "这张卡已自动保存"}
                  {saveState === "dirty" && "这张卡有未保存修改"}
                  {saveState === "failed" && "这张卡保存失败 · 请重试"}
                </span>
                <span className={`badge ${card.role === "主角" ? (card.name && card.persona ? "ok" : "warn") : "empty"}`}>
                  {card.role === "主角" ? (card.name && card.persona ? "已立主角" : "主角待立") : card.role}
                </span>
                <div className="char-ops">
                  <button type="button" onClick={() => { setOpsPanel(opsPanel === "merge" ? "" : "merge"); setOpsName(""); }}>合并…</button>
                  <button type="button" onClick={() => { setOpsPanel(opsPanel === "del" ? "" : "del"); setOpsName(""); }}>删除</button>
                </div>
              </div>
            </header>

            {(card.role === "配角" || card.role === "反派") && !displayName(card.name) && !card.persona.trim() && (
              <p className="opt" data-testid="char-ai-hint" style={{ margin: "2px 0 0" }}>
                右侧「一键立卡」可以先为 TA 拟一稿——只补空格，采纳才写入。
              </p>
            )}

            {opsPanel === "del" && (
              <div className="char-ops-panel danger">
                <span className="op-t">
                  删除《{displayName(card.name) || "未命名"}》？相关关系会一并移除。
                  {card.role === "主角" && " 主角位会空出来。"}
                  删错了可撤销——撤销保留到你继续编辑或刷新之前。
                </span>
                <input
                  placeholder={`输入「${displayName(card.name) || "未命名"}」以确认`}
                  aria-label="输入角色名以确认"
                  value={opsName}
                  onChange={(e) => setOpsName(e.target.value)}
                />
                <button
                  type="button"
                  className="btn btn-danger"
                  disabled={opsName.trim() !== (displayName(card.name) || "未命名")}
                  onClick={() => void doDelete()}
                >
                  删除
                </button>
                <button type="button" className="btn btn-secondary" onClick={() => setOpsPanel("")}>取消</button>
              </div>
            )}
            {opsPanel === "merge" && (
              <div className="char-ops-panel">
                <span className="op-t">
                  把《{displayName(card.name) || "未命名"}》并到另一张卡：<b>那张卡写过的不动，空格用这张补上</b>。可撤销。
                </span>
                <select aria-label="合并到哪张卡" value={mergeTarget} onChange={(e) => setMergeTarget(e.target.value)}>
                  <option value="">合并到…</option>
                  {list.filter((x) => x.id !== card.id).map((x) => (
                    <option key={x.id} value={x.id}>{displayName(x.name) || "未命名"} · #{x.code}</option>
                  ))}
                </select>
                <input
                  placeholder={`输入「${displayName(card.name) || "未命名"}」以确认`}
                  aria-label="输入角色名以确认"
                  value={opsName}
                  onChange={(e) => setOpsName(e.target.value)}
                />
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={!mergeTarget || opsName.trim() !== (displayName(card.name) || "未命名")}
                  onClick={() => void doMerge()}
                >
                  合并
                </button>
                <button type="button" className="btn btn-secondary" onClick={() => setOpsPanel("")}>取消</button>
              </div>
            )}

            <div className="char-persona">
              <span className="char-persona-label">一句话人设 · 每章都会带上这张卡的这句</span>
              <textarea
                rows={2}
                value={card.persona}
                placeholder="此人是谁、凭什么是他"
                aria-label="一句话人设"
                onChange={(e) => setField("persona", e.target.value)}
              />
            </div>

            {/* AI 出稿预览改走弹窗出卡（c-settings-ai-confirm-modal） */}

            <section className="sec">
              <header className="sec-h">
                <h3>基础档案</h3>
                <span className="sec-sub">写每一章都用得上的硬信息——点一下就能改。</span>
              </header>
              <div>
                <div className="char-dossier-row">
                  <span className="char-dossier-k">性别 · 年龄 · 种族</span>
                  <span className="char-dossier-v char-tri">
                    <input value={card.dossier.gender ?? ""} placeholder="性别" aria-label="性别" onChange={(e) => setField("dossier.gender", e.target.value)} />
                    <input value={card.dossier.age ?? ""} placeholder="年龄" aria-label="年龄" onChange={(e) => setField("dossier.age", e.target.value)} />
                    <input value={card.dossier.race ?? ""} placeholder="种族" aria-label="种族" onChange={(e) => setField("dossier.race", e.target.value)} />
                  </span>
                </div>
                <div className="char-dossier-row">
                  <span className="char-dossier-k">势力 · 身份</span>
                  <span className="char-dossier-v">
                    <input value={card.dossier.faction ?? ""} placeholder="例：青梧宗外门 · 杂役弟子" aria-label="势力·身份" onChange={(e) => setField("dossier.faction", e.target.value)} />
                  </span>
                </div>
                <div className="char-dossier-row">
                  <span className="char-dossier-k">外貌标签</span>
                  <span className="char-dossier-v">
                    <input value={card.dossier.look ?? ""} placeholder="例：瘦长个 · 旧道袍" aria-label="外貌标签" onChange={(e) => setField("dossier.look", e.target.value)} />
                  </span>
                </div>
                <div className="char-dossier-row">
                  <span className="char-dossier-k">语言特征</span>
                  <span className="char-dossier-v">
                    <input value={card.dossier.speech ?? ""} placeholder="例：说话慢半拍 · 口头禅" aria-label="语言特征" onChange={(e) => setField("dossier.speech", e.target.value)} />
                  </span>
                </div>
                <div className="char-dossier-row">
                  <span className="char-dossier-k">背景</span>
                  <span className="char-dossier-v">
                    <textarea rows={1} value={card.dossier.background ?? ""} placeholder="出身与来路" aria-label="背景" onChange={(e) => setField("dossier.background", e.target.value)} />
                  </span>
                </div>
                <div className="char-dossier-row">
                  <span className="char-dossier-k">剧情定位 <i className="req">必填</i></span>
                  <span className="char-dossier-v">
                    <input value={card.dossier.plot ?? ""} placeholder="在故事里干什么——主角必填" aria-label="剧情定位" onChange={(e) => setField("dossier.plot", e.target.value)} />
                  </span>
                </div>
              </div>
            </section>

            <section className="sec">
              <header className="sec-h">
                <h3>认知内核</h3>
                <span className="sec-sub">六层是一条链：世界观 → 自我观 → 价值观 → 能力 → 行为 → 环境。</span>
              </header>
              {/* 体检报告改走弹窗报告卡（c-settings-ai-confirm-modal） */}
              <div className="char-cog">
                {COG_LAYERS.map((layer) => {
                  const open = !!cogOpen[layer.id];
                  const filledCount = layer.fields.filter((f) => String(card.cog[f.k] ?? "").trim()).length;
                  const missingReq = layer.fields.filter((f) => f.req && !String(card.cog[f.k] ?? "").trim());
                  const primary = card.cog[layer.primary] ?? "";
                  return (
                    <article
                      key={layer.id}
                      className={`cog-layer${open ? " open" : ""}${missingReq.length ? " missing" : filledCount ? " filled" : ""}`}
                    >
                      <button
                        type="button"
                        className="cog-layer-head"
                        onClick={() => setCogOpen((m) => ({ ...m, [layer.id]: !m[layer.id] }))}
                      >
                        <span className="cog-layer-no">{layer.no}</span>
                        <span className="cog-layer-name">{layer.name}</span>
                        <span className="cog-layer-tag">{layer.tag}</span>
                        <span className="cog-layer-hint" title={COG_LEVEL_HINTS[layer.id]}>
                          {COG_LEVEL_HINTS[layer.id]}
                        </span>
                        <span className={`cog-layer-prev${primary ? " has" : ""}`}>
                          {primary || "还没写——展开补这一层的核心一句"}
                        </span>
                        {missingReq.length ? (
                          <span className="cog-layer-miss">还差 {missingReq.length} 项必填</span>
                        ) : (
                          <span className="cog-layer-state">{filledCount}/{layer.fields.length}</span>
                        )}
                      </button>
                      {open && (
                        <div className="cog-layer-grid">
                          {layer.fields.map((f) => (
                            <div key={f.k} className={`cog-field${f.k === layer.primary ? " full" : ""}`}>
                              <div className="f-label">
                                <b>
                                  {f.label}
                                  {f.req && <i className="req">必填</i>}
                                </b>
                              </div>
                              {COG_FIELD_HINTS[f.k] && (
                                <p className="f-hint">{COG_FIELD_HINTS[f.k]}</p>
                              )}
                              <input
                                value={card.cog[f.k] ?? ""}
                                aria-label={f.label}
                                onChange={(e) => setField(`cog.${f.k}`, e.target.value)}
                              />
                            </div>
                          ))}
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>
            </section>

            <section className="sec">
              <header className="sec-h">
                <h3>人物关系</h3>
                <span className="sec-sub">只记这个角色怎么看别人——同一对方一条。</span>
                <button type="button" className="text-btn" onClick={() => setRelForm((v) => !v)}>＋记一段关系</button>
              </header>
              <div>
                {(card.relations ?? []).map((rel) => (
                  <div key={rel.id} className="rel-row-item">
                    <div className="rel-line">
                      <span className="rel-who">
                        <span className="pill pill-status">{rel.rel_type}</span>
                        <span className="rel-other-name">{rel.other_name || rel.other_id.slice(0, 8)}</span>
                      </span>
                      <span className="rel-note">
                        {rel.stance}
                        {rel.stance && rel.note ? "——" : ""}
                        {rel.note}
                      </span>
                      {rel.ch_ref && <span className="rel-meta">记于 {rel.ch_ref}</span>}
                      <span className="rel-acts">
                        <button
                          type="button"
                          onClick={() => {
                            setRelForm(true);
                            setRelDraft({ other: rel.other_id, rel_type: rel.rel_type, stance: rel.stance, note: rel.note });
                          }}
                        >
                          编辑
                        </button>
                        <button
                          type="button"
                          onClick={() =>
                            void charactersApi
                              .deleteRelation(projectId, card.id, rel.other_id)
                              .then(() => loadCard(card.id))
                          }
                        >
                          删除
                        </button>
                      </span>
                    </div>
                  </div>
                ))}
                {!card.relations?.length && (
                  <p className="opt">还没有关系记录——遇到值得记的人，点「＋记一段关系」。</p>
                )}
              </div>
              {relForm && (
                <div className="rel-form-inline">
                  <select
                    aria-label="对方角色"
                    value={relDraft.other}
                    onChange={(e) => setRelDraft((d) => ({ ...d, other: e.target.value }))}
                  >
                    <option value="">选对方…</option>
                    {list.filter((x) => x.id !== card.id).map((x) => (
                      <option key={x.id} value={x.id}>{x.name || "未命名"}</option>
                    ))}
                  </select>
                  <select
                    aria-label="关系类型"
                    value={relDraft.rel_type}
                    onChange={(e) => setRelDraft((d) => ({ ...d, rel_type: e.target.value }))}
                  >
                    {["父子", "母女", "兄弟", "姐妹", "血亲", "师徒", "同门", "举荐", "同盟", "友好", "主仆", "上下级", "竞争", "纵容", "管束", "恩情", "亏欠", "敌对", "仇人", "畏惧"].map((t) => (
                      <option key={t}>{t}</option>
                    ))}
                  </select>
                  <input placeholder="一句立场" aria-label="立场" value={relDraft.stance} onChange={(e) => setRelDraft((d) => ({ ...d, stance: e.target.value }))} />
                  <input placeholder="一句说明" aria-label="关系说明" value={relDraft.note} onChange={(e) => setRelDraft((d) => ({ ...d, note: e.target.value }))} />
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={async () => {
                      if (!relDraft.other) {
                        showToast("先选对方");
                        return;
                      }
                      try {
                        await charactersApi.upsertRelation(projectId, card.id, relDraft.other, {
                          rel_type: relDraft.rel_type,
                          stance: relDraft.stance,
                          note: relDraft.note,
                        });
                        setRelForm(false);
                        await loadCard(card.id);
                      } catch (e) {
                        showToast((e as Error).message || "保存失败");
                      }
                    }}
                  >
                    记下
                  </button>
                  <button type="button" className="btn btn-secondary" onClick={() => setRelForm(false)}>取消</button>
                </div>
              )}
            </section>

          </>
        )}

        {toast && (
          <p className="opt" role="status">
            {toast}
            {undoOp && (
              <>
                {" "}
                <button type="button" className="char-undo" onClick={() => void doUndo()}>
                  撤销
                </button>
              </>
            )}
          </p>
        )}
      </div>

      {/* AI 出卡确认弹窗：出稿（bootstrap/persona/dossier/cog）＋体检统一进卡，
          关闭即弃；缓存重开免请求（D9）；「去改」＝关卡＋展开对应认知层 */}
      <AiCardModal
        open={cardOpen && cardAction !== null}
        card={
          cardAction != null && (cardAction === "bootstrap" || cardAction === "cardDraft") && bootstrapSink
            ? {
                label:
                  cardAction === "cardDraft"
                    ? `AI 拟稿 · 为「${card ? displayName(card.name) || "未命名" : ""}」立卡（采纳才写入）`
                    : "AI 拟稿 · 从简介立主角（采纳才写入）",
                kind: "struct",
                adoptText: "采纳 · 写入",
                cached: cardCached,
                node: (
                  <>
                    {bootstrapSink.name && (
                      <p style={{ margin: "5px 0" }}><b>名称</b>：{bootstrapSink.name}</p>
                    )}
                    {bootstrapSink.aliases.length > 0 && (
                      <p style={{ margin: "5px 0" }}><b>别名</b>：{bootstrapSink.aliases.join(" · ")}</p>
                    )}
                    {bootstrapSink.persona && (
                      <p style={{ margin: "5px 0" }}><b>一句话人设</b>：{bootstrapSink.persona}</p>
                    )}
                    {draftRows(bootstrapSink)}
                    <p style={{ margin: "8px 0 0", fontSize: 11.5, color: "var(--muted)" }}>
                      只补空格——你写过的字一个不动。
                    </p>
                  </>
                ),
                adopt: () => void adoptBootstrap(),
              }
            : cardAction && cardAction !== "bootstrap" && cardAction !== "check" && sink
              ? {
                  label: "AI 生成 · 采纳才写入（只补空格）",
                  kind: "struct",
                  adoptText: "采纳 · 写入",
                  cached: cardCached,
                  node: (
                    <>
                      {draftRows(sink)}
                      <p style={{ margin: "8px 0 0", fontSize: 11.5, color: "var(--muted)" }}>
                        这一格你写过就不动；采纳走既有单格写入。
                      </p>
                    </>
                  ),
                  adopt: () => void adoptSink(),
                }
              : cardAction === "check" && check
                ? {
                    label: `AI 体检 · ${check.verdict || "角色 × 整体设定"}`,
                    kind: "report",
                    cached: cardCached,
                    node: (
                      <>
                        {check.items.map((item) => (
                          <div key={item.name} className="chk-row">
                            <span className="chk-name">{item.name}</span>
                            <span className={`chk-res ${item.status}`}>
                              {item.status === "ok" ? "达标" : item.status === "warn" ? "风险" : item.status === "conflict" ? "矛盾" : "缺输入"}
                            </span>
                            <span className="chk-note">{item.note}</span>
                            {item.goto?.startsWith("layer:") && (
                              <button
                                type="button"
                                className="chk-go"
                                onClick={() => {
                                  setCardOpen(false); // 关卡再展开对应层（跳转优先于报告常驻）
                                  setCogOpen((m) => ({ ...m, [item.goto!.split(":")[1]]: true }));
                                }}
                              >
                                去改
                              </button>
                            )}
                          </div>
                        ))}
                      </>
                    ),
                  }
                : null
        }
        running={aiBusy}
        version={cardAction ? versions[cardAction] : undefined}
        onRegenerate={
          cardAction
            ? () => {
                if (cardAction === "bootstrap" || cardAction === "cardDraft") void runBootstrap(cardAction);
                else if (cardAction === "check") {
                  // 体检「重新检查」：报告卡在会话内可刷新（D2 报告卡骨架）
                  if (!card) return;
                  aiBusyRef.current = true;
                  setAiBusy(true);
                  void (async () => {
                    try {
                      const res = await charactersApi.aiCheck(projectId, card.id);
                      if (selectedIdRef.current === card.id) {
                        setCheck(res);
                        setCardCached(false);
                        setVersions((prev) => ({ ...prev, check: (prev.check ?? 0) + 1 }));
                      }
                    } catch (e) {
                      showToast((e as Error).message || "AI \u751f\u6210\u5931\u8d25\uff0c\u53ef\u91cd\u8bd5");
                    } finally {
                      aiBusyRef.current = false;
                      setAiBusy(false);
                    }
                  })();
                } else {
                  // 出稿重生成：清缓存标记走原请求路径（cache 判定键 sinkAction 不变即重开，
                  // 这里直接驱动句柄级重跑）
                  void (async () => {
                    aiBusyRef.current = true;
                    setAiBusy(true);
                    try {
                      const res = await charactersApi.aiDraft(projectId, card!.id, cardAction as "persona" | "dossier" | "cog");
                      setSink(res);
                      setSinkAction(cardAction);
                      setCardCached(false);
                      setVersions((prev) => ({ ...prev, [cardAction]: (prev[cardAction] ?? 0) + 1 }));
                    } catch (e) {
                      showToast((e as Error).message || "AI \u751f\u6210\u5931\u8d25\uff0c\u53ef\u91cd\u8bd5");
                    } finally {
                      aiBusyRef.current = false;
                      setAiBusy(false);
                    }
                  })();
                }
              }
            : undefined
        }
        onClose={() => setCardOpen(false)}
        data-testid="char-ai-card"
      />
    </div>
  );
});

export default CharacterManager;
