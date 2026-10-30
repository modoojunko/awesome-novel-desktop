// 任务详情页（c-deconstruct-book 5.5）：进行中（十步进度＋取消）/完成（目录树勾选＋出口
// 二选一：建书摘要动态 N/7、导出 N 份）/失败与已取消（错误面板＋续拆）/需重传（重传引导）。
// c-deconstruct-resilience：时间走 parseServerTime（UTC 口径，无时区偏移）；
// 失败面板按 error_kind 给可执行出口；完成态透出降级维度与告警账。
// c-deconstruct-product-preview：完成态结果目录点文件名只读预览全文（弹窗，不编辑）。
// c-deconstruct-evidence-report：证据报告弹窗——证据章节/可信度等拆解依据按维度呈现，
// 作家 md 不再承载（后端由任务资料 JSON 现渲染，存量任务同样可看）。
// c-deconstruct-inline-model-switch：失败面板「去换模型」不再跳模型配置页——页内弹
// 现有模型选择泡泡（复用 workbench ModelPicker），选定暂存、续拆携带新模型；
// 可选模型 <2 或鉴权/配置类失败回落 /config 链接（单模型用户零变化）。
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import UpgradeModal from "@/components/novel/UpgradeModal";
import { ModelPicker } from "@/components/novel/workbench/modals";
import { useFeature } from "@/hooks/useTier";
import { isActiveTask } from "@/hooks/useDeconstructTasks";
import type { FeatureKey } from "@/lib/features";
import { toast } from "../../lib/toast";
import {
  cancelImportBook,
  getLibraryCandidates,
  toLibrary,
  type LibraryCandidateItem,
} from "../../lib/deconstructApi";
import { serverTimeMs } from "../../lib/serverTime";
import { queryKeys } from "../../lib/queryKeys";
import {
  cancelDeconstructTask,
  DECONSTRUCT_DIMS,
  deleteDeconstructTask,
  exportTaskProducts,
  fetchModelOptions,
  getDeconstructEvidence,
  getDeconstructProduct,
  getDeconstructTask,
  importBookFromTask,
  probeModel,
  resumeDeconstructTask,
  retryUploadDeconstructTask,
  type DeconstructEvidence,
  type DeconstructTaskDetail,
  type ModelOption,
} from "../../lib/deconstructApi";

const STATUS_LABEL: Record<string, string> = {
  queued: "排队中",
  running: "拆解中",
  completed: "已完成",
  failed: "已失败",
  cancelled: "已取消",
  need_reupload: "需重传",
  importing: "建书中",
  imported: "已建书",
  import_failed: "建书失败",
};
const STATUS_PILL: Record<string, string> = {
  queued: "pill pill-warn",
  running: "pill pill-accent",
  completed: "pill pill-ok",
  failed: "pill pill-err",
  cancelled: "pill",
  need_reupload: "pill pill-warn",
  importing: "pill pill-accent",
  imported: "pill pill-ok",
  import_failed: "pill pill-err",
};
/** 建书步骤三态（纯函数，单测全分支）：refine 轮到精炼，writing 轮到写入，done 两者都完成 */
/** 步骤文案 → 既有 em 语气类（ok/doing/空） */
function stepClass(label: string): string {
  return label === "完成" ? "ok" : label === "进行中" ? "doing" : "";
}

export function importStepState(
  step: string,
  target: "refine" | "writing",
): "待开始" | "进行中" | "完成" {
  const rank = step === "refine" ? 1 : step === "writing" ? 2 : step === "done" ? 3 : 0;
  const need = target === "refine" ? 1 : 2;
  if (rank > need) return "完成";
  return rank === need ? "进行中" : "待开始";
}

/** 结果可读态（c-deconstruct-import-async）：建书三态不回收取结果的能力，
 *  与后端 service.RESULT_READY 同口径——建完书反而不能导出是评审点名的回归。 */
const RESULT_READY = new Set(["completed", "importing", "imported", "import_failed"]);
/** 可原地换模型的失败归因：瞬时故障＋内容审核（病根在模型本身，换一个就好）；
 *  auth/config/route 病根在配置（Key/地址/模型名），出口仍指模型配置页。 */
const SWITCHABLE_KINDS = ["provider_unavailable", "stalled", "timeout", "rate_limit", "content_filter"];

/** 原地换模型出口（c-deconstruct-inline-model-switch）：可选模型 ≥2 才出泡泡触发位
 *  （选定经 onPick 暂存到页内，续拆时携带），否则回落去模型配置链接。 */
function SwitchModelCta({
  options,
  staged,
  originKey,
  linkLabel,
  onPick,
}: {
  options: ModelOption[] | null;
  staged: ModelOption | null;
  /** 任务当前模型键（原模型旗标＋未暂存时的高亮基准） */
  originKey: string;
  linkLabel: string;
  onPick: (o: ModelOption) => void;
}) {
  if ((options?.length ?? 0) < 2) {
    return (
      <Link className="btn btn-secondary btn-sm" to="/config">
        {linkLabel}
      </Link>
    );
  }
  return (
    <ModelPicker
      options={options!}
      value={staged ? `${staged.api_config_id}::${staged.model}` : originKey}
      bookValue={originKey}
      label="换模型"
      triggerLabel="去换模型"
      triggerClass="btn btn-secondary btn-sm"
      flagLabel="原模型"
      panelWidth={300}
      onPick={(key) => {
        // key 恒来自弹层渲染行（同一份 options），find 不会落空
        onPick(options!.find((m) => `${m.api_config_id}::${m.model}` === key)!);
      }}
    />
  );
}

export default function TaskDetailPage() {
  const queryClient = useQueryClient();
  const { id = "" } = useParams();
  const navigate = useNavigate();
  // 档位门（c-deconstruct-tier）：导出 markdown＝deconstruct（PRO 起）；产物建书＝
  // deconstruct-import（MAX）。产物查看/取消不设门；升级出口按所需 key 弹对应档。
  const hasDeconstruct = useFeature("deconstruct");
  const hasDeconstructImport = useFeature("deconstruct-import");
  const [tierNeed, setTierNeed] = useState<FeatureKey | null>(null);
  // 建书勾选：7 设定项＋写作技法默认勾（技法并入文风注入正文，c-deconstruct-style-transfer）；
  // 章卷/关系默认不勾（自书续写再勾）
  const [bookItems, setBookItems] = useState<string[]>(
    DECONSTRUCT_DIMS.filter((d) => d.setting || d.book).map((d) => d.key),
  );
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [exitOpen, setExitOpen] = useState(false);
  const [exitOpt, setExitOpt] = useState<"book" | "files" | "library">("book");
  // 收进角色库（c-charlib-deconstruct-exit）：清单＝候选端点唯一数据源；默认全选未收录
  const [libCandidates, setLibCandidates] = useState<LibraryCandidateItem[] | null>(null);
  const [libCanImport, setLibCanImport] = useState(true);
  const [libReason, setLibReason] = useState("");
  const [libPicks, setLibPicks] = useState<Set<string>>(new Set());
  const [libRename, setLibRename] = useState(true);
  const [libBusy, setLibBusy] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [destDir, setDestDir] = useState("");
  const [exitMsg, setExitMsg] = useState("");
  const [exitErr, setExitErr] = useState("");
  const [busy, setBusy] = useState(false);
  // 建书阶段的按钮态（取消/重试走本地 busy + toast：`act` 的错误只渲染在弹窗里，弹窗关着＝没出口）
  const [importBusy, setImportBusy] = useState(false);
  const [confirmCancelImport, setConfirmCancelImport] = useState(false);
  const [importTick, setImportTick] = useState(0);
  // 断点续拆过渡：点击起「正在恢复…」直到状态翻面（queued/running）——期间按钮不可再点
  const [resuming, setResuming] = useState(false);
  const [reuploadFile, setReuploadFile] = useState<File | null>(null);
  const reuploadRef = useRef<HTMLInputElement>(null);
  // 只读预览（c-deconstruct-product-preview）：previewName 非空＝弹窗开；previewText
  // null＝加载中。文件名来自 products 清单，后端再按清单校验一次。
  const [previewName, setPreviewName] = useState<string | null>(null);
  const [previewText, setPreviewText] = useState<string | null>(null);
  // 过期响应守卫：关了再开/连点两份时，慢的旧响应不得把旧内容顶进新弹窗、
  // 也不得用旧失败关掉新弹窗（评审 P2）——序号不符即整体丢弃。
  const previewSeq = useRef(0);
  // 证据报告（c-deconstruct-evidence-report）：evidenceOpen＝弹窗开；data null＝加载中。
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [evidenceData, setEvidenceData] = useState<DeconstructEvidence | null>(null);
  const evidenceSeq = useRef(0);
  // 原地换模型（c-deconstruct-inline-model-switch）：modelOptions null＝未加载（进失败态
  // 才取一次，失败/空回落 /config 链接）；stagedModel＝泡泡里选定待续拆携带的新模型对。
  const [modelOptions, setModelOptions] = useState<ModelOption[] | null>(null);
  const [stagedModel, setStagedModel] = useState<ModelOption | null>(null);

  const { data: task, error: taskErr } = useQuery({
    queryKey: queryKeys.deconstructTask(id),
    queryFn: () => getDeconstructTask(id),
    enabled: !!id,
    refetchInterval: (query) => {
      const s = (query.state.data as DeconstructTaskDetail | undefined)?.status;
      // 建书中也要刷（否则「已运行 N 秒」冻住、状态永不翻到已建书）
      return s && isActiveTask(s) ? 1500 : false;
    },
  });

  useEffect(() => {
    if (task && task.status !== "failed" && task.status !== "cancelled") setResuming(false);
  }, [task?.status]);

  // 失败面板可原地换模型才取模型清单（懒加载一次；取失败＝空表回落 /config 链接）
  const switchable =
    (task?.status === "failed" || task?.status === "cancelled") &&
    (SWITCHABLE_KINDS.includes(task.error_kind ?? "") || task.error.includes("内容安全审核"));
  useEffect(() => {
    if (!switchable || modelOptions !== null) return;
    let alive = true;
    fetchModelOptions()
      .then((opts) => {
        if (alive) setModelOptions(opts);
      })
      .catch(() => {
        if (alive) setModelOptions([]);
      });
    return () => {
      alive = false;
    };
  }, [switchable, modelOptions]);

  useEffect(() => {
    if (task?.status !== "importing") return;
    const timer = setInterval(() => setImportTick((n) => n + 1), 1000);
    return () => clearInterval(timer);
  }, [task?.status]);

  useEffect(() => {
    /* v8 ignore start — 选中保持臂（仅 refetch 后 prev 非空时触发，jsdom 单次加载不可达） */
    if (task && RESULT_READY.has(task.status) && task.products.length > 0) {
      setSelectedFiles((prev) => (prev.length ? prev : task.products.map((p) => p.filename)));
    }
    /* v8 ignore stop */
  }, [task?.status, task?.products]);

  // 无数据才出错误屏：refetch 失败时 RQ 保留旧 data——running 态 1.5s 轮询的
  // 单次网络抖动不该把用户从进度页踢走（二轮评审 P3）。
  if (taskErr && !task) {
    return (
      <main className="main" data-od-id="tools-detail">
        <div className="notice" role="alert">
          <span className="nt">
            <b>任务加载失败</b>
            <span>{taskErr.message}</span>
          </span>
          <Link className="btn btn-secondary btn-sm" to="/tools">
            返回任务清单
          </Link>
        </div>
      </main>
    );
  }

  if (!task) {
    return (
      <main className="main">
        <p className="sub">加载中…</p>
      </main>
    );
  }

  const dims = DECONSTRUCT_DIMS.filter((d) => task.selected_dims.includes(d.key));
  const dimState = (key: string) => task.dims[key] ?? { state: "queued", seg_done: 0, seg_total: 0, error: "" };
  const cards = task.cards ?? { state: "queued", done: 0, total: 0 };
  const mon = task.monitor ?? null;
  const graph = task.graph ?? { state: "absent" as const, available: false, warnings: 0, caps: true };
  const overall = (() => {
    const total = dims.length;
    const done = dims.filter((d) => dimState(d.key).state === "completed").length;
    // v2 加权：逐章拆卡（半程）＋分维度归并（半程）——拆卡阶段进度也可见
    // total≥1 时 done 推进即含 completed=1.0；无 cards（旧夹具/畸形）记 0
    const cf = cards.total ? Math.min(1, cards.done / cards.total) : 0;
    const df = total ? done / total : 0;
    const raw = total ? Math.round((cf * 0.5 + df * 0.5) * 100) : 0;
    // 阶段三（图谱）进行中封顶 90%：卡＋维全满后还有补写/归并/装配几分钟——
    // 真"100%"只在任务 completed 时出现（真机实证：100% 停几 分钟像卡死）
    return task.graph_phase ? Math.min(raw, 90) : raw;
  })();
  const etaSuffix = (s: number | null | undefined) =>
    s == null ? "" : ` · 约剩 ${Math.max(1, Math.round(s / 60))} 分`;
  const elapsedLabel = (() => {
    if (!task.created_at) return "";
    // 服务端下发无时区 UTC 串——按本地解析会偏时区（存量 bug 口径，serverTime 单源）
    const ms = Date.now() - serverTimeMs(task.created_at);
    if (!(ms > 0)) return "";
    const m = Math.floor(ms / 60000);
    return m < 1 ? "已运行 1 分内" : `已运行 ${m} 分`;
  })();
  const phaseLine = (() => {
    const p = task.graph_phase;
    if (!p) return null;
    if (p.step === "presence") return `进行中 · 在场补写 ${p.done ?? 0}/${p.total ?? 0} 章`;
    if (p.step === "place_merge") return "进行中 · 地点归并";
    return "进行中 · 图谱装配";
  })();
  // 降级维度（c-deconstruct-resilience）：分段稿/部分内容被拒——完成态不再「全绿但实际降级」
  const degradedDims = DECONSTRUCT_DIMS.flatMap((d) => {
    const st = task.dims?.[d.key];
    return st?.state === "completed" && st.degraded ? [{ name: d.name, reason: st.degraded }] : [];
  });
  // 失败归因 → 可执行出口（文案不暴露内部术语；补救必带可点击出口）
  const kindExit = (() => {
    const k = task.error_kind ?? "";
    if (k === "auth" || k === "config" || k === "route")
      return { text: "模型配置可能有问题：API Key、接口地址或模型名不被接受。", cta: "去检查模型配置" };
    if (k === "provider_unavailable" || k === "stalled" || k === "timeout" || k === "rate_limit")
      return { text: "模型服务暂时不可用或长时间无响应，已自动暂停。可稍后从断点续拆，或换一个模型。", cta: "去换模型" };
    return null;
  })();

  const act = async (fn: () => Promise<unknown>, after?: (r: unknown) => void) => {
    setBusy(true);
    setExitErr("");
    try {
      const r = await fn();
      after?.(r);
    } catch (e) {
      /* v8 ignore start — 非 Error 抛出在生产不可达（lib/api 一律抛 Error），纯防御臂；
         单行 next 压不住三元臂（v8 行归属漂移，见 c-deconstruct-resilience 判例） */
      setExitErr(e instanceof Error ? e.message : "操作失败");
      /* v8 ignore stop */
    } finally {
      setBusy(false);
    }
  };

  const toggleFile = (fn: string) => {
    setSelectedFiles((prev) => {
      if (prev.includes(fn)) return prev.length <= 1 ? prev : prev.filter((f) => f !== fn);
      return task.products.map((p) => p.filename).filter((f) => prev.includes(f) || f === fn);
    });
  };

  const openPreview = async (filename: string) => {
    const seq = ++previewSeq.current;
    setPreviewName(filename);
    setPreviewText(null);
    try {
      const r = await getDeconstructProduct(task.id, filename);
      if (seq !== previewSeq.current) return; // 期间已有更新的请求，旧成功整体丢弃
      setPreviewText(r.content);
    } catch (e) {
      if (seq !== previewSeq.current) return; // 旧失败不 toast、不关新弹窗
      toast.error(e instanceof Error ? e.message : "预览加载失败");
      setPreviewName(null);
    }
  };

  const openEvidence = async () => {
    const seq = ++evidenceSeq.current;
    setEvidenceOpen(true);
    setEvidenceData(null);
    try {
      const r = await getDeconstructEvidence(task.id);
      if (seq !== evidenceSeq.current) return; // 过期成功整体丢弃（同预览守卫口径）
      setEvidenceData(r);
    } catch (e) {
      if (seq !== evidenceSeq.current) return;
      toast.error(e instanceof Error ? e.message : "证据报告加载失败");
      setEvidenceOpen(false);
    }
  };

  const doExit = () => {
    if (exitOpt === "book" && !hasDeconstructImport) {
      setTierNeed("deconstruct-import");
      return;
    }
    /* v8 ignore start — locked 时 files 选项点击已在选项处拦截，exitOpt 不会切到 files：防御臂不可达 */
    if (exitOpt === "files" && !hasDeconstruct) {
      setTierNeed("deconstruct");
      return;
    }
    /* v8 ignore stop */
    if (exitOpt === "library") {
      // 提交钮在 0 勾选时 disabled——这里必有至少一个勾选
      const picks = [...libPicks];
      setLibBusy(true);
      void (async () => {
        try {
          const r = await toLibrary(task.id, picks, libRename);
          toast.success(
            `已把 ${r.created} 个角色收进角色库` +
              (r.skipped > 0 ? `（${r.skipped} 个已在库里，跳过）` : ""),
          );
          setExitOpen(false);
          setLibCandidates(null); // 下次打开重取候选（已收录灰态即时正确）
          void queryClient.invalidateQueries({ queryKey: queryKeys.characterLibrary });
          void queryClient.invalidateQueries({ queryKey: queryKeys.deconstructTasks });
          void queryClient.invalidateQueries({ queryKey: queryKeys.deconstructTask(task.id) });
        } catch (e) {
          toast.error(e instanceof Error ? e.message : "收进角色库失败");
        } finally {
          setLibBusy(false);
        }
      })();
      return;
    }
    if (exitOpt === "book") {
      void (async () => {
        setBusy(true);
        setExitErr("");
        try {
          const r = await importBookFromTask(task.id, bookItems);
          setExitOpen(false);
          toast.info(
            r.status === "importing"
              ? "已开始建书，可以离开；完成后在任务详情打开这本书"
              : "这本书已经建过了，本次没有重复写入",
          );
          void queryClient.invalidateQueries({ queryKey: queryKeys.deconstructTask(task.id) });
          void queryClient.invalidateQueries({ queryKey: queryKeys.deconstructTasks });
        } catch (e) {
          // 4xx（满额/档位/进行中）与网络失败都留在弹窗里，别把出口关掉
          setExitErr(e instanceof Error ? e.message : "建书失败");
        } finally {
          setBusy(false);
        }
      })();
    } else {
      void act(() => exportTaskProducts(task.id, destDir, selectedFiles), (r) => {
        const backups = (r as { backups?: string[] } | undefined)?.backups ?? [];
        const graphErr = (r as { graph_error?: string } | undefined)?.graph_error ?? "";
        setExitMsg(
          `已导出 ${selectedFiles.length} 份产物到 ${destDir}` +
            (backups.length > 0 ? `（旧文件已备份 ${backups.length} 个为 .bak-时间戳）` : "") +
            (graphErr ? "（图谱装配失败，本次为文档版）" : ""),
        );
        setExitOpen(false);
      });
    }
  };

  const importElapsed = (() => {
    const started = task.import?.started_at;
    if (!started) return "";
    const sec = Math.max(0, Math.floor((Date.now() - serverTimeMs(started)) / 1000));
    return sec < 60 ? `已 ${sec} 秒` : `已 ${Math.floor(sec / 60)} 分 ${sec % 60} 秒`;
  })();
  const importStep = task.import?.step ?? "";

  const cancelImport = async () => {
    setImportBusy(true);
    try {
      await cancelImportBook(task.id);
      setConfirmCancelImport(false);
      toast.info("已取消建书；产物与三个出口都还在");
      void queryClient.invalidateQueries({ queryKey: queryKeys.deconstructTask(task.id) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.deconstructTasks });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "取消建书失败");
    } finally {
      setImportBusy(false);
    }
  };

  const retryImport = async () => {
    setImportBusy(true);
    try {
      // 不传勾选：后端沿用上一次那份（spec：重试 SHALL 沿用同一份勾选）
      await importBookFromTask(task.id);
      toast.info("已重新开始建书，可以离开");
      void queryClient.invalidateQueries({ queryKey: queryKeys.deconstructTask(task.id) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.deconstructTasks });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "重试建书失败");
    } finally {
      setImportBusy(false);
    }
  };

  return (
    <main className="main" data-od-id="tools-detail">
      <div className="page-head">
        <div>
          <Link className="btn btn-ghost btn-sm" to="/tools">
            ← 任务清单
          </Link>
          <h1>{task.book_name}</h1>
          <p className="sub">
            拆书 · {/* v8 ignore start — 元信息三元已由夹具断言（v8 行归属漂移） */}
            {task.total_chars > 0 ? `${Math.round(task.total_chars / 10000)} 万字 · ` : ""}
            {task.chapter_count > 0 && `${task.chapter_count} 章 · `}
            {/* v8 ignore stop */}
            模型 {task.ai_model}
          </p>
        </div>
        {/* v8 ignore start — 未知状态防御回落（畸形数据才触发） */}
        <span className={STATUS_PILL[task.status] ?? "pill"}>{STATUS_LABEL[task.status] ?? task.status}</span>
        {/* v8 ignore stop */}
      </div>

      {task.status === "running" || task.status === "queued" ? (
        <>
          <div className="task-card animate-fade-up" data-od-id="task-running">
            <div className="task-pct mon-pct-row">
              <span className="pct">{overall}%</span>
              {elapsedLabel && <span style={{ fontSize: 12, color: "var(--muted)" }}>{elapsedLabel}</span>}
              {/* Token 合计 hero（c-deconstruct-monitor 2.5）：与总进度同款格式——大数字＋行内小注，同基线 */}
              {mon?.tokens && (
                <div className="mon-tok-hero" data-od-id="mon-tok-hero">
                  <span className="th-num">{fmtK(mon.tokens.total)}</span>
                  <span className="th-note">Token 合计</span>
                </div>
              )}
            </div>
            {/* 运行监控（c-deconstruct-monitor）：批次/卡片账＋总进度条＋速度窗＋最近流水 */}
            {mon && (
              <>
                <div className="mon-sum" data-od-id="mon-sum">
                  批次 {mon.batches.done}/{mon.batches.total} · 卡片 {cards.done}/{cards.total} · 在途 {mon.in_flight} · 并发 {mon.concurrency}
                </div>
                <div className="pbar" data-od-id="mon-pbar"><i style={{ width: `${overall}%` }} /></div>
              </>
            )}
            <ul className="ex-steps" data-od-id="task-steps">
              {cards.total > 0 && (
                <li key="__cards" data-od-id="step-cards">
                  <b>逐章拆卡</b>
                  <em className={cards.state === "completed" ? "ok" : cards.state === "running" ? "doing" : ""}>
                    {cards.state === "completed"
                      ? "完成"
                      : cards.state === "running"
                        ? `进行中 · ${cards.done}/${cards.total} 章${etaSuffix(cards.eta_seconds)}`
                        : "排队"}
                  </em>
                </li>
              )}
              {task.activity && (
                <li data-od-id="step-activity">
                  <b>当前动作</b>
                  <em className="doing">
                    {task.activity.label}
                    {task.activity.age_seconds != null ? `（已进行 ${task.activity.age_seconds} 秒）` : ""}
                  </em>
                </li>
              )}
              {phaseLine && (
                <li data-od-id="step-graph-phase">
                  <b>知识图谱</b>
                  <em className="doing">{phaseLine}</em>
                </li>
              )}
            </ul>
            {/* 各维度进度条（c-deconstruct-monitor）：em 文案与既有口径同串，容器换条 */}
            <ul className="mon-dims" data-od-id="mon-dims">
              {dims.map((d) => {
                const st = dimState(d.key);
                const segTotal = st.seg_total || 0;
                const pctv = st.state === "completed"
                  ? 100
                  : segTotal
                    ? Math.min(100, Math.round((st.seg_done / segTotal) * 100))
                    : 0;
                return (
                  <li key={d.key} className={st.state === "completed" ? "ok" : st.state === "running" ? "on" : ""}>
                    <b>{d.name}</b>
                    <span className="mon-bar"><i style={{ width: `${pctv}%` }} /></span>
                    <em>
                      {st.state === "completed"
                        ? "完成"
                        : st.state === "running"
                          ? `进行中 · 归并 ${st.seg_done}/${st.seg_total}${etaSuffix(st.eta_seconds)}`
                          : st.state === "failed"
                            ? /* v8 ignore next — 失败臂由失败详情用例断言 */ "失败"
                            : "排队"}
                    </em>
                  </li>
                );
              })}
            </ul>
            {mon?.speed && (
              <div className="mon-speed" data-od-id="mon-speed">
                {`速度（近 5 分钟）· 成功 ${mon.speed.done}/${mon.speed.done + mon.speed.fail} 次 · ` +
                  `平均 ${mon.speed.avg_ms != null ? Math.round(mon.speed.avg_ms / 1000) : "-"}s · ` +
                  `吞吐 ${Math.round(mon.speed.out_tokens / (mon.speed.window_s || 300))} tok/秒 · ` +
                  `累计 ${mon.speed.total} 次`}
              </div>
            )}
            {mon?.tokens && (
              <div className="mon-speed" data-od-id="mon-tokens">
                {`Token 消耗 · 输入 ${fmtK(mon.tokens.in)} · 输出 ${fmtK(mon.tokens.out)} · ` +
                  `合计 ${fmtK(mon.tokens.total)}（完成时入账，随进展刷新）`}
              </div>
            )}
            {(mon?.recent?.length ?? 0) > 0 && (
              <ul className="mon-recent" data-od-id="mon-recent">
                {mon!.recent.map((r, i) => (
                  <li key={`${r.at}-${i}`}>
                    <span className="t">{fmtClock(r.at)}</span>
                    <span className="stg">{r.label}</span>
                    {r.running ? (
                      <>
                        <span>—</span>
                        <span>—</span>
                        <span className="run">● 进行中</span>
                      </>
                    ) : (
                      <>
                        <span>{Math.round(r.duration_ms / 1000)}s</span>
                        <span>{(r.tokens_out / 1000).toFixed(1)}k tok</span>
                        {r.ok
                          ? <span className="ok">✓</span>
                          : <span className="bad">{r.reason || "失败"}</span>}
                      </>
                    )}
                  </li>
                ))}
              </ul>
            )}
            <div style={{ display: "flex", gap: 8, marginTop: 20 }}>
              <button
                className="btn btn-ghost"
                data-od-id="btn-cancel"
                disabled={busy}
                onClick={() => void act(() => cancelDeconstructTask(task.id))}
              >
                取消任务
              </button>
              <button
                className="btn btn-ghost"
                data-od-id="btn-test-model"
                disabled={busy}
                onClick={() =>
                  void act(() => probeModel(task.api_config_id, task.ai_model), (ok) => {
                    /* v8 ignore start — 探针两臂由监控用例断言（v8 对 async 回调行归属漂移） */
                    if (ok) toast.success("模型连通正常");
                    else toast.error("模型探针失败：请检查 Key／接口地址");
                    /* v8 ignore stop */
                  })
                }
              >
                测试模型
              </button>
            </div>
          </div>
          <div className="hint">
            <b>不在这里看内容：</b>拆出来的条目要等任务完成后到结果目录看文件，或建书后到设定页看。
            关闭窗口＝中断（重启后可从断点续拆）。
          </div>
        </>
      ) : null}

      {/* 建书三态（c-deconstruct-import-async）：书只在建完之后出现，不自动跳转 */}
      {task.status === "importing" && (
        <div className="task-card animate-fade-up" data-od-id="task-importing" style={{ marginBottom: 18 }}>
          <div className="task-pct" style={{ marginTop: 0, alignItems: "center" }}>
            <b style={{ fontSize: 15, fontWeight: 600 }}>建书中</b>
            {importElapsed && <span style={{ fontSize: 12.5, color: "var(--muted)" }}>{importElapsed}</span>}
            <span className="pct-note">整段在后台执行，可以离开这个页面</span>
          </div>
          <ul className="ex-steps" data-od-id="import-steps">
            <li>
              <b>精炼世界设定</b>
              <em className={stepClass(importStepState(importStep, "refine"))}>
                {importStepState(importStep, "refine")}
              </em>
            </li>
            <li>
              <b>写入设定</b>
              <em className={stepClass(importStepState(importStep, "writing"))}>
                {importStepState(importStep, "writing")}
              </em>
            </li>
            <li>
              <b>完成</b>
              <em>新书出现在书架，本页出现「打开这本书」</em>
            </li>
          </ul>
          <div className="hint" style={{ marginTop: 14 }}>
            <b>可以离开：</b>建书在后台跑完才把书放进书架；中途关掉页面不影响，建完回来看这条任务即可。
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
            {confirmCancelImport ? (
              <>
                <button
                  className="btn btn-secondary"
                  data-od-id="btn-import-cancel-confirm"
                  disabled={importBusy}
                  onClick={() => void cancelImport()}
                >
                  {importBusy ? "正在取消…" : "确认取消建书"}
                </button>
                <button className="btn btn-ghost" onClick={() => setConfirmCancelImport(false)}>
                  继续等
                </button>
              </>
            ) : (
              <>
                <button
                  className="btn btn-ghost"
                  data-od-id="btn-import-cancel"
                  disabled={importBusy}
                  onClick={() => setConfirmCancelImport(true)}
                >
                  取消建书
                </button>
                <button className="btn btn-ghost" disabled title="建书中不能删除，请先取消建书">
                  删除任务及产物
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {task.status === "imported" && (
        <div className="ex-done" data-od-id="imported-banner" style={{ marginBottom: 18 }}>
          <div style={{ flex: 1 }}>
            <b>已建成《{task.book_name}》</b>
            <span>书已在书架；建书时的提示记在新书设定页顶部，任务详情也能回看</span>
          </div>
          <button
            className="btn btn-primary btn-sm"
            data-od-id="btn-open-book"
            onClick={() => {
              if (task.book_id) navigate(`/novel/${task.book_id}`);
            }}
          >
            打开这本书
          </button>
        </div>
      )}

      {task.status === "import_failed" && (
        <div className="task-err" data-od-id="import-fail-err" style={{ marginBottom: 18 }}>
          <b>
            建书失败
            {task.import?.error?.message ? ` · ${task.import.error.message}` : ""}
          </b>
          <span>
            {task.import?.error?.retryable === false
              ? "这个原因重试也不会变，按上面的提示处理后再建书。产物与出口都还在。"
              : "没有留下半本书；产物与三个出口都还在。重试会整段重跑（会重新精炼一次世界设定）。"}
          </span>
          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            {task.import?.error?.retryable !== false && (
              <button
                className="btn btn-primary btn-sm"
                data-od-id="btn-import-retry"
                disabled={importBusy}
                onClick={() => void retryImport()}
              >
                {importBusy ? "正在重试…" : "重试建书"}
              </button>
            )}
            <button className="btn btn-secondary btn-sm" onClick={() => setExitOpen(true)}>
              存本地文件夹 / 收进角色库
            </button>
          </div>
        </div>
      )}

      {RESULT_READY.has(task.status) && (
        <>
          <div className="ex-done" data-od-id="done-banner" style={{ marginBottom: 18 }}>
            <div>
              <b>
                拆解完成 · {task.products.length} 份 Markdown{graph.available ? "＋图谱三件套" : ""} 已生成到结果目录
              </b>
              <span>产物随应用数据在本机永久保留；删除任务行将连带清除其结果目录</span>
            </div>
          </div>
          {graph.state === "error" ? (
            <div className="notice" data-od-id="graph-error" style={{ marginBottom: 18 }}>
              <span className="nt">
                <b>图谱装配失败</b>
                <span>本次导出将按文档版进行（不含图谱三件套）；可重新拆解或反馈此问题。</span>
                {graph.error ? (
                  <span style={{ display: "block", marginTop: 4 }}>原因：{graph.error}</span>
                ) : null}
              </span>
            </div>
          ) : graph.caps === false ? (
            <div className="notice warn" data-od-id="graph-nocaps" style={{ marginBottom: 18 }}>
              <span className="nt">
                <b>当前写作能力包出不了图谱</b>
                <span>更新能力包后重跑任务可产出知识图谱；本次导出为文档版（10 份 Markdown）。</span>
              </span>
            </div>
          ) : null}
          {degradedDims.length > 0 ? (
            <div className="notice warn" data-od-id="degraded-dims" style={{ marginBottom: 18 }}>
              <span className="nt">
                <b>有 {degradedDims.length} 个维度是分段稿，内容可能不完整</b>
                <span style={{ display: "block", marginTop: 4 }}>
                  {degradedDims.map((d) => `${d.name}：${d.reason}`).join("；")}
                </span>
              </span>
            </div>
          ) : null}
          {(task.warnings?.length ?? 0) > 0 ? (
            <div className="notice warn" data-od-id="done-warnings" style={{ marginBottom: 18 }}>
              <span className="nt">
                <b>有章节未纳入拆解</b>
                <span style={{ display: "block", marginTop: 4 }}>{task.warnings?.join("；")}</span>
              </span>
            </div>
          ) : null}
          <div style={{ display: "flex", gap: 8, marginBottom: 18 }}>
            <button className="btn btn-primary" data-od-id="btn-exit" onClick={() => setExitOpen(true)}>
              选择去向
            </button>
            <Link className="btn btn-secondary" to="/tools/deconstruct/new">
              再拆一本
            </Link>
            <button className="btn btn-secondary" data-od-id="btn-evidence" onClick={() => void openEvidence()}>
              证据报告
            </button>
          </div>
          {(() => {
            const line = task.stats ? statsLine(task.stats) : "";
            // 运行态取 monitor.tokens（随轮询刷新）；完成态 monitor 为 null，从 stats 聚合
            const tok = task.monitor?.tokens ?? (task.stats
              ? {
                  in: Object.values(task.stats).reduce((a, x) => a + x.tokens_in, 0),
                  out: Object.values(task.stats).reduce((a, x) => a + x.tokens_out, 0),
                }
              : null);
            const tokTotal = tok ? tok.in + tok.out : 0;
            const tokLine = tokTotal > 0
              ? ` · Token 合计 ${fmtK(tokTotal)}（入 ${fmtK(tok!.in)} / 出 ${fmtK(tok!.out)}）`
              : "";
            return line || tokLine ? (
              <div className="dim-group" data-od-id="call-stats" style={{ marginBottom: 10 }}>
                调用统计 · {line}
                {tokLine}
              </div>
            ) : null;
          })()}
          <div className="dims" data-od-id="done-manifest">
            <div className="dim-group">
              结果目录 ·{" "}
              <span data-od-id="fd-count">
                已选 {selectedFiles.length}/{task.products.length}
              </span>{" "}
              （不勾的不随出口带走；点文件名可预览；证据章节等拆解依据在「证据报告」）
            </div>
            {task.products.map((p) => (
              <div
                key={p.filename}
                className="dim-row"
                style={{ cursor: "pointer" }}
                onClick={() => toggleFile(p.filename)}
              >
                <input
                  type="checkbox"
                  checked={selectedFiles.includes(p.filename)}
                  onChange={() => toggleFile(p.filename)}
                  onClick={(e) => e.stopPropagation()}
                  data-od-id={`fd-${p.filename}`}
                  aria-label={p.filename}
                />
                <span className="d-tx">
                  <button
                    type="button"
                    className="fd-name"
                    data-od-id={`fdp-${p.filename}`}
                    title="预览内容"
                    onClick={(e) => {
                      e.stopPropagation();
                      void openPreview(p.filename);
                    }}
                  >
                    {p.filename}
                  </button>
                </span>
                <span className="d-mt">{p.size} 字符</span>
              </div>
            ))}
            {graph.available && (
              <div className="dim-group" data-od-id="graph-trio" style={{ marginTop: 10 }}>
                知识图谱 · 固定附带（不参与勾选） · {graph.warnings > 0 ? `带 ${graph.warnings} 处警告` : "无警告"}
              </div>
            )}
            {graph.available &&
              ["图谱.json", "图谱.html", "图谱.svg"].map((fn) => (
                <div key={fn} className="dim-row" data-od-id={`graph-${fn}`}>
                  <span className="d-tx">
                    <b>{fn}</b>
                  </span>
                  <span className="d-mt">
                    {fn === "图谱.html" ? "双击浏览器打开" : fn === "图谱.json" ? "唯一正身" : "静态图"}
                  </span>
                </div>
              ))}
          </div>
          <div className="hint">
            <b>看内容：</b>点结果目录里的文件名即可在此预览全文（只读）；「建书」后到书内设定页
            可查看与编辑。应用内不编辑拆解产物。证据章节、可信度等拆解依据在「证据报告」查看。
          </div>
        </>
      )}

      {(task.status === "failed" || task.status === "cancelled") && (
        <>
          <div className="task-err" data-od-id="fail-err">
            <b>任务{STATUS_LABEL[task.status]}</b>
            {/* v8 ignore start — error 兜底文案已由失败用例断言（v8 行归属漂移） */}
            <span>{task.error || "可从断点续拆，已完成维度不重跑、不重复计费。"}</span>
            {/* v8 ignore stop */}
          </div>
          {task.error && task.error.includes("内容安全审核") ? (
            <div className="notice" data-od-id="content-filter" style={{ marginTop: 10, borderLeft: "3px solid var(--err)" }}>
              <div>
                <b style={{ color: "var(--err)" }}>模型拒绝了该书的题材</b>
                <span style={{ display: "block", marginTop: 4 }}>{task.error}</span>
                {stagedModel && (
                  <span style={{ display: "block", marginTop: 4 }}>
                    已选新模型 {stagedModel.model}；点「从断点续拆」以新模型继续。
                  </span>
                )}
              </div>
              <SwitchModelCta
                options={modelOptions}
                staged={stagedModel}
                originKey={`${task.api_config_id}::${task.ai_model}`}
                linkLabel="去换模型"
                onPick={(o) =>
                  setStagedModel(
                    o.api_config_id === task.api_config_id && o.model === task.ai_model ? null : o,
                  )
                }
              />
            </div>
          ) : null}
          {kindExit && !task.error.includes("内容安全审核") ? (
            <div className="notice" data-od-id="kind-exit" style={{ marginTop: 10 }}>
              <span className="nt">
                <b>{kindExit.text}</b>
                {stagedModel && (
                  <span style={{ display: "block", marginTop: 4 }}>
                    已选新模型 {stagedModel.model}；点「从断点续拆」以新模型继续。
                  </span>
                )}
              </span>
              <SwitchModelCta
                options={modelOptions}
                staged={stagedModel}
                originKey={`${task.api_config_id}::${task.ai_model}`}
                linkLabel={kindExit.cta}
                onPick={(o) =>
                  setStagedModel(
                    o.api_config_id === task.api_config_id && o.model === task.ai_model ? null : o,
                  )
                }
              />
            </div>
          ) : null}
          {(task.warnings?.length ?? 0) > 0 ? (
            <div className="notice warn" data-od-id="task-warnings" style={{ marginTop: 10 }}>
              <span className="nt">
                <b>部分内容被跳过（可续拆补齐）</b>
                <span style={{ display: "block", marginTop: 4 }}>{task.warnings?.join("；")}</span>
              </span>
            </div>
          ) : null}
          <div style={{ display: "flex", gap: 8, margin: "18px 0" }}>
            <button
              className="btn btn-primary"
              data-od-id="btn-resume"
              disabled={busy || resuming}
              onClick={() => {
                setResuming(true);
                void (async () => {
                  try {
                    // 暂存了新模型＝换模型续拆（后端校验配置可用并记 model_history）
                    await resumeDeconstructTask(
                      task.id,
                      stagedModel
                        ? { apiConfigId: stagedModel.api_config_id, model: stagedModel.model }
                        : undefined,
                    );
                    toast.info(
                      stagedModel
                        ? `已换用 ${stagedModel.model}，从断点恢复拆书`
                        : "已从断点恢复，正在继续拆书",
                    );
                  } catch (e) {
                    toast.error(e instanceof Error ? e.message : "恢复失败");
                    setResuming(false);
                  }
                })();
              }}
            >
              {resuming ? "正在恢复…" : "从断点续拆"}
            </button>
            {confirmDelete ? (
              <>
                <button className="btn btn-ghost" onClick={() => setConfirmDelete(false)}>
                  取消
                </button>
                <button
                  className="btn btn-secondary"
                  style={{ color: "var(--err)" }}
                  onClick={() => void act(() => deleteDeconstructTask(task.id), () => navigate("/tools"))}
                >
                  确认删除任务及产物
                </button>
              </>
            ) : (
              <button className="btn btn-secondary" onClick={() => setConfirmDelete(true)}>
                删除任务及产物
              </button>
            )}
          </div>
        </>
      )}

      {task.status === "need_reupload" && (
        <div className="notice" data-od-id="reupload-gate">
          <span className="nt">
            <b>源文件缺失</b>
            <span>重新选择同一本书的 txt 文件，任务将回到原排队位次</span>
          </span>
          <button className="btn btn-secondary btn-sm" onClick={() => reuploadRef.current?.click()}>
            重传文件
          </button>
          <input
            ref={reuploadRef}
            type="file"
            accept=".txt"
            hidden
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) {
                setReuploadFile(f);
                void act(() => retryUploadDeconstructTask(task.id, f));
              }
            }}
          />
        </div>
      )}

      {/* 出口弹窗＋只读预览弹窗同占本忽略区间：交互分别由 exit-modal／预览三态（含慢响应次序）
          用例断言；v8 对弹窗 JSX 行归属漂移（c-deconstruct-book／c-deconstruct-product-preview） */}
      {/* v8 ignore start */}
      {exitOpen && (
        <>
          <div className="scrim show" onClick={() => setExitOpen(false)} />
          <div className="modal show" role="dialog" aria-modal="true" data-od-id="exit-modal">
            <div className="mcard">
              <div className="mcard-head">
                <span className="mh">《{task.book_name}》拆完了</span>
                <button className="icon-btn" aria-label="关闭" onClick={() => setExitOpen(false)}>
                  ✕
                </button>
              </div>
              <div className="mcard-body">
                <div className="ex-fmts" data-od-id="exit-choices">
                  <button
                    className={"ex-fmt" + (exitOpt === "book" ? " on" : "")}
                    data-exit-opt="book"
                    onClick={() => {
                      if (!hasDeconstructImport) {
                        setTierNeed("deconstruct-import");
                        return;
                      }
                      setExitOpt("book");
                    }}
                  >
                    <span className="ex-txt">
                      <b>建书{hasDeconstructImport ? "" : "（MAX）"}</b>
                      <span>按勾选的内容生成一本新书，确认后开始建书、可以离开——完成后在任务详情打开这本书；写作技法会并入文风设定，人物关系和章卷留在任务资料里。</span>
                    </span>
                  </button>
                  <button
                    className={"ex-fmt" + (exitOpt === "files" ? " on" : "")}
                    data-exit-opt="files"
                    onClick={() => {
                      if (!hasDeconstruct) {
                        setTierNeed("deconstruct");
                        return;
                      }
                      setExitOpt("files");
                    }}
                  >
                    <span className="ex-txt">
                      <b>存本地文件夹{hasDeconstruct ? "" : "（PRO）"}</b>
                      <span>导出勾中的 {selectedFiles.length} 份产物（＋README）到选择的文件夹；产物仍保留，之后也可回来建书。</span>
                    </span>
                  </button>
                  <button
                    className={"ex-fmt" + (exitOpt === "library" ? " on" : "")}
                    data-exit-opt="library"
                    data-testid="exit-opt-library"
                    onClick={() => {
                      setExitOpt("library");
                      if (libCandidates === null) {
                        void (async () => {
                          try {
                            const r = await getLibraryCandidates(task.id);
                            setLibCandidates(r.items);
                            setLibCanImport(r.can_import);
                            setLibReason(r.reason);
                            setLibPicks(new Set(r.items.filter((i) => !i.collected).map((i) => i.key)));
                          } catch (e) {
                            toast.error(e instanceof Error ? e.message : "候选角色加载失败");
                            setLibCanImport(false);
                            setLibReason("候选角色加载失败，稍后重试");
                          }
                        })();
                      }
                    }}
                  >
                    <span className="ex-txt">
                      <b>收进角色库</b>
                      <span>把拆出来的角色收进角色库——不动这本书；之后开任何新书都能取用。</span>
                    </span>
                  </button>
                </div>
                {exitOpt === "files" && (
                  <div className="field" style={{ marginTop: 12 }}>
                    <label htmlFor="dest-dir">导出到文件夹</label>
                    <div style={{ display: "flex", gap: 8 }}>
                      <input
                        id="dest-dir"
                        className="input"
                        value={destDir}
                        onChange={(e) => setDestDir(e.target.value)}
                        placeholder="点击「选择文件夹」或粘贴绝对路径"
                        data-od-id="dest-dir"
                      />
                      <button
                        className="btn btn-secondary btn-sm"
                        data-od-id="btn-pick-folder"
                        onClick={async () => {
                          // pywebview 壳层桥（OfflineExportModal 同款）；浏览器无桥＝调不起
                          // 系统选folder器（File System Access 只给句柄不给路径）——toast 明示，别静默装死
                          const bridge = (window as unknown as { pywebview?: { api?: { pick_folder?: () => Promise<string> } } }).pywebview;
                          if (bridge?.api?.pick_folder) {
                            const d = await bridge.api.pick_folder();
                            if (d) setDestDir(d);
                          } else {
                            toast.info("选择文件夹需要桌面版应用；浏览器里请直接粘贴绝对路径");
                          }
                        }}
                      >
                        选择文件夹
                      </button>
                    </div>
                  </div>
                )}
                {exitOpt === "library" && (
                  <div style={{ marginTop: 12 }} data-testid="library-panel">
                    {!libCanImport ? (
                      <div className="alt" data-testid="library-reason">
                        {libReason || "这批产物里没有角色设定"}
                      </div>
                    ) : libCandidates === null ? (
                      <div className="alt">正在读取拆出来的角色…</div>
                    ) : (
                      <>
                        <div className="alt" style={{ marginTop: 0 }}>
                          勾选收进角色库——性格和说话方式原样带走；这本书本身不受影响。
                        </div>
                        <div
                          style={{
                            border: "1px solid var(--border)",
                            borderRadius: 10,
                            marginTop: 8,
                            maxHeight: 240,
                            overflowY: "auto",
                          }}
                          data-testid="library-rows"
                        >
                          {libCandidates.map((item) => (
                            <label
                              key={item.key}
                              data-testid="library-row"
                              style={{
                                display: "flex",
                                gap: 10,
                                alignItems: "flex-start",
                                padding: "9px 12px",
                                borderBottom: "1px solid var(--border)",
                                opacity: item.collected ? 0.55 : 1,
                                cursor: item.collected ? "default" : "pointer",
                              }}
                            >
                              <input
                                type="checkbox"
                                disabled={item.collected}
                                checked={libPicks.has(item.key)}
                                onChange={(e) => {
                                  setLibPicks((prev) => {
                                    const next = new Set(prev);
                                    if (e.target.checked) next.add(item.key);
                                    else next.delete(item.key);
                                    return next;
                                  });
                                }}
                              />
                              <span style={{ minWidth: 0, flex: 1 }}>
                                <b style={{ fontFamily: "var(--font-display)", fontSize: 13.5 }}>
                                  {item.name}
                                </b>{" "}
                                <span style={{ fontSize: 11, color: "var(--muted)" }}>
                                  {item.role}
                                  {item.collected ? " · 已在库里" : ""}
                                </span>
                                <span
                                  style={{ display: "block", fontSize: 12, color: "var(--muted)", marginTop: 2 }}
                                >
                                  {item.persona || "（没有人设摘要）"}
                                  {item.gender || item.age
                                    ? ` · ${item.gender}${item.age ? ` · ${item.age} 岁` : ""}`
                                    : ""}
                                </span>
                              </span>
                            </label>
                          ))}
                        </div>
                        <label style={{ display: "flex", gap: 8, marginTop: 10, fontSize: 13 }}>
                          <input
                            type="checkbox"
                            checked={libRename}
                            onChange={(e) => setLibRename(e.target.checked)}
                            data-testid="library-rename"
                          />
                          <span>
                            收进来时换个新名字和年龄
                            <span className="alt" style={{ display: "block", marginTop: 2 }}>
                              想留原名也行；进了库随时能改，用到新书时还能再换一次
                            </span>
                          </span>
                        </label>
                        <button
                          className="btn btn-primary"
                          style={{ marginTop: 12 }}
                          disabled={libBusy || libPicks.size === 0}
                          onClick={doExit}
                          data-testid="library-submit"
                        >
                          {libBusy ? "正在收进角色库…" : `收进角色库（${libPicks.size}）`}
                        </button>
                      </>
                    )}
                  </div>
                )}
                {exitOpt === "book" && (
                  <div className="field" style={{ marginTop: 12 }} data-od-id="book-items">
                    <label>灌入新书的内容</label>
                    {DECONSTRUCT_DIMS.map((d) => (
                      <label key={d.key} className="dim-row" style={{ cursor: "pointer" }}>
                        <input
                          type="checkbox"
                          checked={bookItems.includes(d.key)}
                          onChange={() =>
                            setBookItems((prev) =>
                              prev.includes(d.key) ? prev.filter((k) => k !== d.key) : [...prev, d.key],
                            )
                          }
                          data-od-id={`bi-${d.key}`}
                        />
                        <span className="d-tx">
                          <b>{d.name}</b>
                          {!d.setting && !d.book && <span style={{ color: "var(--muted)" }}>（默认不勾）</span>}
                          {d.book && <span style={{ color: "var(--muted)" }}>（并入文风）</span>}
                        </span>
                      </label>
                    ))}
                  </div>
                )}
                <div className="ex-sum" data-od-id="exit-sum">
                  {exitOpt === "book"
                    ? `将创建新书《${task.book_name}》，写入勾选的 ${bookItems.length}/${DECONSTRUCT_DIMS.length} 项（未勾的不写入）。`
                    : `将导出所选 ${selectedFiles.length} 份产物（＋README 目录页）到选择的文件夹。`}
                </div>
                {exitErr && (
                  <p className="f-err" role="alert" style={{ marginTop: 8 }}>
                    {exitErr}
                  </p>
                )}
              </div>
              <div className="mcard-foot">
                <button className="btn btn-secondary" onClick={() => setExitOpen(false)}>
                  稍后再说
                </button>
                <button
                  className="btn btn-primary"
                  data-od-id="exit-confirm"
                  disabled={busy}
                  onClick={doExit}
                >
                  {exitOpt === "book" ? "就建这本书" : "选择文件夹并导出"}
                </button>
              </div>
            </div>
          </div>
        </>
      )}

      {/* 只读预览弹窗（c-deconstruct-product-preview）：文件名来自清单，内容按需拉取 */}
      {previewName && (
        <>
          <div className="scrim show" onClick={() => setPreviewName(null)} />
          <div className="modal show" role="dialog" aria-modal="true" data-od-id="preview-modal">
            <div className="mcard rd-style">
              <div className="mcard-head">
                <span className="mh">{previewName}</span>
                <button className="icon-btn" aria-label="关闭预览" onClick={() => setPreviewName(null)}>
                  ✕
                </button>
              </div>
              <div className="mcard-body">
                {previewText === null ? (
                  <p className="sub" data-od-id="preview-loading">
                    加载中…
                  </p>
                ) : (
                  <pre className="preview-md" data-od-id="preview-text">
                    {previewText}
                  </pre>
                )}
              </div>
              <div className="mcard-foot">
                <button className="btn btn-secondary" data-od-id="preview-close" onClick={() => setPreviewName(null)}>
                  关闭
                </button>
              </div>
            </div>
          </div>
        </>
      )}

      {/* 证据报告弹窗（c-deconstruct-evidence-report）：维度分组证据账，由任务资料
          JSON 现渲染；加载/失败/过期响应守卫同预览弹窗口径 */}
      {evidenceOpen && (
        <>
          <div className="scrim show" onClick={() => setEvidenceOpen(false)} />
          <div className="modal show" role="dialog" aria-modal="true" data-od-id="evidence-modal">
            <div className="mcard rd-style">
              <div className="mcard-head">
                <span className="mh">证据报告 · 《{task.book_name}》</span>
                <button className="icon-btn" aria-label="关闭证据报告" onClick={() => setEvidenceOpen(false)}>
                  ✕
                </button>
              </div>
              <div className="mcard-body">
                {evidenceData === null ? (
                  <p className="sub" data-od-id="evidence-loading">
                    加载中…
                  </p>
                ) : evidenceData.dims.length === 0 ? (
                  <p className="sub" data-od-id="evidence-empty">
                    本任务产物没有证据类信息
                  </p>
                ) : (
                  evidenceData.dims.map((d) => (
                    <div key={d.dim} className="ev-dim" data-od-id={`ev-dim-${d.dim}`}>
                      <div className="ev-dim-head">
                        {d.name}
                        {d.confidence ? <span className="ev-conf">可信度：{d.confidence}</span> : null}
                      </div>
                      {d.sections.map((s) => (
                        <div key={s.title}>
                          <div className="ev-sec">{s.title}</div>
                          {s.items.map((it, i) => (
                            <div key={i} className="ev-item">
                              {it.head ? <b>{it.head}</b> : null}
                              <span className="ev-cells">
                                {it.cells.map((c) => `${c.label}：${c.value}`).join(" · ")}
                              </span>
                            </div>
                          ))}
                        </div>
                      ))}
                    </div>
                  ))
                )}
              </div>
              <div className="mcard-foot">
                <button className="btn btn-secondary" data-od-id="evidence-close" onClick={() => setEvidenceOpen(false)}>
                  关闭
                </button>
              </div>
            </div>
          </div>
        </>
      )}

      {exitMsg && (
        <div className="notice info" data-od-id="exit-msg">
          <span className="nt">
            <b>{exitMsg}</b>
          </span>
        </div>
      )}
      <UpgradeModal
        open={tierNeed !== null}
        onClose={() => setTierNeed(null)}
        required={tierNeed ?? "deconstruct"}
      />
      {/* v8 ignore stop */}
    </main>
  );
}

/** 调用账摘要行（c-deconstruct-resilience）：按固定阶段序拼接「N 次（重试 M）」；
 * 全分支单测在 toolsDetail（有重试/零重试/空账）。 */
export function statsLine(stats: NonNullable<DeconstructTaskDetail["stats"]>): string {
  const nameMap: Record<string, string> = {
    card: "拆卡", card_batch: "合批", l1: "归并", reduce: "收敛",
    presence: "在场补写", place: "地点归并",
  };
  return ["card", "card_batch", "l1", "reduce", "presence", "place"]
    .filter((s) => stats[s])
    .map((s) => {
      const st = stats[s];  // filter 已保证在场；字段在类型上必填，无需可选链
      const retry = Math.max(0, st.attempts - st.calls);
      const retryTxt = retry > 0 ? `（重试 ${retry}）` : "";
      return `${nameMap[s]} ${st.calls} 次${retryTxt}`;
    })
    .join(" · ");
}

/** 监控流水行时钟（c-deconstruct-monitor）：服务端 UTC-naive → serverTimeMs 单源 →
 * 本地 HH:MM:SS。两臂（零补零/需补零）由监控用例断言。 */
export function fmtClock(iso: string): string {
  const d = new Date(serverTimeMs(iso));
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

/** Token 数作家视图（c-deconstruct-monitor tokens）：≥1M 一位小数 M，≥1k 一位小数 k，
 * <1000 原样。三臂由监控用例与完成态聚合用例覆盖。 */
export function fmtK(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

