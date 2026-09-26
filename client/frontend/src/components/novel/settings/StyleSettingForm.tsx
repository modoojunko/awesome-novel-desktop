// 文风设定 v2（style-settings-v2）：面板内两页签。
//   文字文风（免费，三区：叙事身份必填/硬约束/描写手法题材预填删改 ＋ 例句 1–3 折叠）
//   量化参数（PRO：蒸馏 3,000–10,000 字样本 → 作者画像确认 → 六行基线只读＋行级锁定）
//
// 契约要点（评审 P0 落纸）：
//   · 撤并键（possible_mistakes/narrator_role/tone）零写回——save() payload 白名单
//     只带 role/rules/craft/few_shot_examples；归一与迁移在后端 put_style 边界
//   · 量化基线只读：前端唯一写路径是行级锁定切换（styleQuantApi.putLocks）
//   · 蒸馏三步端点串联，每步产物落 style-quant.draft，中断续跑；「不像再学一次」＝
//     step3 带 force 重跑；commit 幂等并服务端并入禁用词——成功后回读 style 只把
//     禁用词/句式两键合入表单态与快照（banned-words-into-style D4：防旧快照保存覆盖丢词）
//   · 禁用词收编（banned-words-into-style）：原「禁用词句」面板退役，硬约束区下挂
//     禁用词（≤100）与句式规则（≤20）两个折叠组，提示词/体检单源取本卡
//   · 章节量化变化不做场景卡——写章 AI 按剧情在容差内自行调节（提示词已带指令）
//
// AI 四行在右栏（SettingsView 接 AiWriterAssistant），编辑区零 AI 按钮（伏笔纪律）。

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import { api } from "@/lib/api";
import { useDirtyState } from "@/hooks/useDirtyState";
import { Cfg, ListEditor, type SettingSaveHandle } from "./FormField";
import { Ico, P } from "@/components/icons";
import type { ChangeReceiptState } from "./ChangeReceipt";
import { styleAiApi, styleQuantApi, BASELINE_ROWS, countSampleChars } from "@/lib/styleApi";
import type { StyleQuant } from "@/lib/styleApi";
import StylePasteModal from "./StylePasteModal";
import { toast } from "@/lib/toast";

interface Props {
  projectId: string;
  /** 设定面板统一契约键（settings router key）；本面板读写 /settings/style 与 /settings/style-quant */
  settingKey: string;
  /** P2-1：脏状态回调（未保存修改时 true），父组件切换面板前据此确认 */
  onDirtyChange?: (dirty: boolean) => void;
  /** 面板脚回执（采纳/重置类一触即变；经 SettingsView 的 ChangeReceiptBar 渲染） */
  onReceiptChange?: (r: ChangeReceiptState | null) => void;
}

export interface StylePanelHandle extends SettingSaveHandle {
  /** 右栏四行分发：distill / polish / check / fewshot（SettingsView AiWriterAssistant） */
  runAi?: (key: string) => Promise<void>;
}

const CHECK_PATH = "M5 13l4 4L19 7";

/** 句式规则（banned-words-into-style：自原 AntiAiSettingForm 整体搬入，接 maxItems） */
interface TicPattern {
  pattern: string;
  name: string;
  threshold: number;
  severity: string;
  description: string;
}

const EMPTY_TIC: TicPattern = { pattern: "", name: "", threshold: 3, severity: "medium", description: "" };

function toTics(v: unknown): TicPattern[] {
  if (!Array.isArray(v)) return [];
  return v
    .map((p): TicPattern => {
      const o = (p ?? {}) as Record<string, unknown>;
      return {
        pattern: String(o.pattern ?? ""),
        name: String(o.name ?? ""),
        threshold: typeof o.threshold === "number" && o.threshold >= 1 ? o.threshold : 3,
        severity: o.severity === "high" || o.severity === "low" ? o.severity : "medium",
        description: String(o.description ?? ""),
      };
    })
    .filter((p) => p.pattern.trim() !== "");
}

/** 句式规则编辑器：首行 句式名/严重度/阈值/删除 ＋ 正则 pattern（mono）＋ 修复说明 */
function TicPatternEditor({ items, onChange }: { items: TicPattern[]; onChange: (v: TicPattern[]) => void }) {
  const update = (i: number, patch: Partial<TicPattern>) => {
    const n = [...items];
    n[i] = { ...(n[i] || EMPTY_TIC), ...patch };
    onChange(n);
  };
  return (
    <div data-od-id="list-tic-patterns">
      {items.length === 0 && <p className="sub-empty">暂无句式规则 · 点下方添加</p>}
      {items.map((item, i) => (
        <div className="sub-block" key={i}>
          <div className="sub-row tics">
            <input
              className="input"
              value={item.name}
              onChange={(e) => update(i, { name: e.target.value })}
              placeholder="句式名，如：不是而是句式"
            />
            <select
              className="input"
              value={item.severity}
              onChange={(e) => update(i, { severity: e.target.value })}
            >
              <option value="high">高</option>
              <option value="medium">中</option>
              <option value="low">低</option>
            </select>
            <input
              className="input num"
              type="number"
              min={1}
              value={item.threshold}
              onChange={(e) => update(i, { threshold: Math.max(1, Number(e.target.value) || 1) })}
              title="单章出现次数阈值"
            />
            <button
              className="icon-btn"
              type="button"
              title="删除本条"
              onClick={() => onChange(items.filter((_, j) => j !== i))}
            >
              <Ico d={P.trash} sw={1.7} />
            </button>
          </div>
          <input
            className="input mono"
            value={item.pattern}
            onChange={(e) => update(i, { pattern: e.target.value })}
            placeholder="正则 pattern，如：不是[^，。]{1,20}(而是|是)"
          />
          <input
            className="input"
            value={item.description}
            onChange={(e) => update(i, { description: e.target.value })}
            placeholder="修复说明（可选）：命中后如何改写"
          />
        </div>
      ))}
      {items.length < 20 && (
        <button
          className="text-btn"
          type="button"
          data-od-id="btn-add-tic"
          onClick={() => onChange([...items, { ...EMPTY_TIC }])}
        >
          <Ico d={P.plus} sw={2} size={13} />
          添加句式规则
        </button>
      )}
      {items.length > 0 && <span className="opt li-cnt num">{items.length}/20 条</span>}
    </div>
  );
}

type Tab = "text" | "quant";
type DistillView = "closed" | "samples" | "steps" | "portrait";

function checkResClass(res: string): string {
  if (res.includes("达标") || res.includes("同源")) return "ok";
  if (res.includes("风险") || res.includes("重复")) return "warn";
  return "miss";
}

const StyleSettingForm = forwardRef<StylePanelHandle, Props>(function StyleSettingForm(
  { projectId, settingKey: _settingKey, onDirtyChange, onReceiptChange },
  ref,
) {
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<Tab>("text");
  const [role, setRole] = useState("");
  const [rules, setRules] = useState<string[]>([""]);
  const [craft, setCraft] = useState<string[]>([""]);
  const [fewShots, setFewShots] = useState<string[]>([""]);
  // 禁用词收编（banned-words-into-style）：词表 ≤100／句式规则 ≤20，无占位空行
  const [banned, setBanned] = useState<string[]>([]);
  const [tics, setTics] = useState<TicPattern[]>([]);
  const [error, setError] = useState("");
  // 题材默认快照（首次加载的归一三区）——页签徽标「已自定义 · N 处」的 diff 基准
  const presetRef = useRef<{ role: string; rules: string[]; craft: string[] } | null>(null);

  // 量化层
  const [quant, setQuant] = useState<StyleQuant | null>(null);
  const [samples, setSamples] = useState<import("@/lib/styleApi").StyleSamples | null>(null);
  const [selFiles, setSelFiles] = useState<Set<string>>(new Set());
  const [selChapters, setSelChapters] = useState<Set<string>>(new Set());
  const [distillView, setDistillView] = useState<DistillView>("closed");
  const [distillStep, setDistillStep] = useState<0 | 1 | 2 | 3>(0);
  const [distillBusy, setDistillBusy] = useState(false);
  // 粘贴样本（c-style-paste-distill）：弹窗开合 + 本次粘贴链的活动文本。
  // 存组件态是为重试——step1 失败后点重试必须继续携带同一粘贴文本，
  // 否则按空文件/章节路装配会报「样本合计 0 字」（粘贴直开路径 samples 为 null 无从补救）。
  const [pasteOpen, setPasteOpen] = useState(false);
  const [pasteText, setPasteText] = useState<string | null>(null);
  const [checkSink, setCheckSink] = useState<{
    checks: Array<{ name: string; res: string; note: string }>;
    verdict: string;
  } | null>(null);

  const shape = useMemo(
    () => ({ role, rules, craft, fewShots, banned, tics }),
    [role, rules, craft, fewShots, banned, tics],
  );
  const { isDirty, snapshotLoaded, markSaved, getSnapshot } = useDirtyState(shape, onDirtyChange);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    Promise.all([api.get(`/novels/${projectId}/settings/style`), styleQuantApi.get(projectId)])
      .then(([style, quant]) => {
        if (!alive) return;
        const roleN = String(style?.role ?? "");
        const rulesN: string[] = Array.isArray(style?.rules) ? style.rules.map(String) : [];
        const craftN: string[] = Array.isArray(style?.craft) ? style.craft.map(String) : [];
        const fewN: string[] = Array.isArray(style?.few_shot_examples)
          ? style.few_shot_examples.map(String)
          : [];
        const bannedN: string[] = Array.isArray(style?.banned_words)
          ? style.banned_words.map(String).filter(Boolean)
          : [];
        const ticsN = toTics(style?.tic_patterns);
        setRole(roleN);
        setRules(rulesN.length ? rulesN : [""]);
        setCraft(craftN.length ? craftN : [""]);
        setFewShots(fewN.slice(0, 3).length ? fewN.slice(0, 3) : [""]);
        setBanned(bannedN);
        setTics(ticsN);
        presetRef.current = { role: roleN, rules: rulesN, craft: craftN };
        setQuant(quant);
        snapshotLoaded({ role: roleN, rules: rulesN, craft: craftN, fewShots: fewN, banned: bannedN, tics: ticsN });
      })
      .catch((e: Error) => {
        if (alive) setError(e.message || "加载失败");
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const publishReceipt = (r: ChangeReceiptState | null) => onReceiptChange?.(r);

  /** 采纳类动作：apply 后挂回执，撤销恢复快照（ChangeReceipt 语义）。 */
  const record = (text: string, apply: () => void, revert: () => void) => {
    apply();
    publishReceipt({
      text,
      undo: () => {
        revert();
        toast.success("已撤销，恢复采纳前内容");
      },
    });
  };

  async function handleSave(): Promise<boolean> {
    setError("");
    try {
      // 白名单 payload（撤并键零写回）：六键之外不带；禁用词/句式随卡保存
      await api.put(`/novels/${projectId}/settings/style`, {
        role: role.trim(),
        rules: rules.map((r) => r.trim()).filter(Boolean),
        craft: craft.map((c) => c.trim()).filter(Boolean).slice(0, 8),
        few_shot_examples: fewShots.map((s) => s.trim()).filter(Boolean).slice(0, 3),
        banned_words: banned.map((w) => w.trim()).filter(Boolean).slice(0, 100),
        tic_patterns: tics
          .filter((t) => t.pattern.trim() !== "")
          .map((t) => ({ ...t, name: t.name.trim(), description: t.description.trim() }))
          .slice(0, 20),
      });
      markSaved();
      publishReceipt(null);
      return true;
    } catch (e: unknown) {
      setError((e as Error).message || "保存失败");
      return false;
    }
  }

  const canConfirm = () => role.trim().length > 0;

  useImperativeHandle(
    ref,
    () => ({
      save: handleSave,
      canConfirm,
      markDirty: () => onDirtyChange?.(true),
      clearAi: () => {
        setCheckSink(null);
        publishReceipt(null);
      },
      runAi: async (key: string) => {
        try {
          await runAiByKey(key);
        } catch (e: unknown) {
          // 运行时失败（后端 400 前置缺失 / 502 超时解析）必须可见——沿 hooks runAi 兜底口径
          toast.error((e as Error).message || "AI 处理失败，可重试");
        }
      },
    }),
  );

  async function runAiByKey(key: string) {
    if (key === "distill") {
      setTab("quant");
      await openDistill();
      return;
    }
    if (key === "polish") {
      const out = await styleAiApi.polish(projectId, {
        role: role.trim(),
        rules: rules.map((r) => r.trim()).filter(Boolean),
        craft: craft.map((c) => c.trim()).filter(Boolean),
      });
      const prev = { role, rules: [...rules], craft: [...craft] };
      record(
        "已采纳「润色文字文风」：三区按题材＋简介重写（覆盖原内容，可撤销）",
        () => {
          setRole(out.role);
          setRules(out.rules.length ? out.rules : [""]);
          setCraft(out.craft.length ? out.craft : [""]);
        },
        () => {
          setRole(prev.role);
          setRules(prev.rules);
          setCraft(prev.craft);
        },
      );
      toast.success("已起草文字文风三区——每条都能改，锚定体检建议跑一遍");
      return;
    }
    if (key === "check") {
      setCheckSink(
        await styleAiApi.check(projectId, {
          role: role.trim(),
          rules: rules.map((r) => r.trim()).filter(Boolean),
          craft: craft.map((c) => c.trim()).filter(Boolean),
        }),
      );
      return;
    }
    if (key === "fewshot") {
      const out = await styleAiApi.fewshotMine(projectId);
      const prev = [...fewShots];
      record(
        `已提炼 ${out.lines.length} 条例句（来自已归档正文）`,
        () => setFewShots(out.lines.length ? out.lines : [""]),
        () => setFewShots(prev),
      );
    }
  }

  // ── 量化页签 ──────────────────────────────────────────────────────
  const quantReady = !!quant && Number(quant.confidence) > 0;
  const draft = quant?.draft ?? null;
  const draftStep = Number(draft?.step ?? 0);

  async function refreshQuant() {
    setQuant(await styleQuantApi.get(projectId));
  }

  async function openDistill() {
    try {
      const s = await styleQuantApi.samples(projectId);
      setSamples(s);
      setSelFiles(new Set(s.files.map((f) => f.name)));
      setSelChapters(new Set(s.chapters.map((c) => c.id)));
      // 续跑：draft 已到 step3 → 画像确认；其余从样本起
      if (draft?.step3?.portrait) {
        setDistillStep(3);
        setDistillView("portrait");
      } else {
        setDistillStep(draftStep as 0 | 1 | 2 | 3);
        setDistillView("samples");
      }
    } catch (e: unknown) {
      setError((e as Error).message || "样本加载失败");
    }
  }

  async function toggleLock(row: string, locked: boolean) {
    const next = await styleQuantApi.putLocks(projectId, { [row]: locked });
    setQuant(next);
    toast.success(locked ? "已锁定——重蒸馏保持这行基线" : "已解锁——重蒸馏会更新这行");
  }

  /**
   * 蒸馏三步串联。opts.startStep 显式起跑（粘贴重启必须传 0——state distillStep 的
   * 闭包旧值会跳过 step1 拿旧产物跑 step3）；opts.text 为粘贴样本，step1 持续携带
   * 直至成功或取消（后端 text 非空＝显式重启，幂等）。
   */
  async function runSteps(from: 1 | 3, force = false, opts?: { startStep?: 0 | 1 | 2 | 3; text?: string | null }) {
    if (distillBusy) return;
    setDistillBusy(true);
    setError("");
    const activePaste = opts?.text ?? null;
    try {
      let step: 0 | 1 | 2 | 3 = opts?.startStep ?? distillStep;
      if (from === 1) {
        while (step < 3) {
          const next = (step + 1) as 1 | 2 | 3;
          const body =
            next === 1
              ? { files: [...selFiles], chapter_ids: [...selChapters], ...(activePaste ? { text: activePaste } : {}) }
              : {};
          await styleQuantApi.distillStep(projectId, next, body);
          step = next;
          setDistillStep(step);
        }
      } else {
        // 只重跑 step3（「不像，再学一次」——step1/2 产物保留）
        await styleQuantApi.distillStep(projectId, 3, { force });
        setDistillStep(3);
      }
      const q = await styleQuantApi.get(projectId);
      setQuant(q);
      if (q.draft?.step3?.portrait) {
        setDistillView("portrait");
        if (activePaste) setPasteText(null); // 粘贴链成功：活动样本使命完成
      }
    } catch (e: unknown) {
      setError((e as Error).message || "蒸馏失败，可重试");
    } finally {
      setDistillBusy(false);
    }
  }

  /** 粘贴样本提交（c-style-paste-distill）：弹窗只管输入，重启跑三步，结果进画像确认卡。 */
  async function startPasteDistill(text: string) {
    setPasteOpen(false);
    setTab("quant");
    setPasteText(text);
    setDistillView("steps");
    await runSteps(1, false, { startStep: 0, text });
  }

  function closeDistill() {
    setPasteText(null); // 用户放弃本次蒸馏：粘贴链样本随之作废
    setDistillView("closed");
  }

  async function commitPortrait() {
    if (distillBusy) return;
    setDistillBusy(true);
    setError("");
    try {
      const out = await styleQuantApi.commit(projectId);
      setQuant(out.quant);
      setDistillView("closed");
      setDistillStep(0);
      // D4 竞态缓解：服务端已 append 禁用词——回读 style 取服务端两键，
      // 与表单态做**并集**合并（评审 P1-1：整体替换会吞掉用户本会话未保存的
      // 禁用词/句式编辑），再基于旧快照局部替换两键（三区快照保持原值：
      // 用户未保存的编辑仍 dirty）
      if (out.banned_added > 0) {
        const fresh = await api.get(`/novels/${projectId}/settings/style`);
        const serverBanned: string[] = Array.isArray(fresh?.banned_words)
          ? fresh.banned_words.map(String).filter(Boolean)
          : [];
        const serverTics = toTics(fresh?.tic_patterns);
        const wordKey = (w: string) => w.normalize("NFKC").trim().toLowerCase();
        const mergedBanned = [...banned];
        for (const w of serverBanned) {
          if (!mergedBanned.some((x) => wordKey(x) === wordKey(w))) mergedBanned.push(w);
        }
        const mergedTics = [...tics];
        for (const t of serverTics) {
          if (!mergedTics.some((x) => x.pattern.trim() === t.pattern)) mergedTics.push(t);
        }
        setBanned(mergedBanned);
        setTics(mergedTics);
        const snap = getSnapshot() as Record<string, unknown> | null;
        // 快照未就绪（异常路径）时跳过——残缺快照会让后续渲染恒 dirty（评审 P2-2）
        if (snap) snapshotLoaded({ ...snap, banned: mergedBanned, tics: mergedTics });
      }
      toast.success("画像已确认——六行基线更新了，写章时生效");
      publishReceipt({
        text: `已落卡：六行基线更新（置信度 ${out.quant.confidence}）· 蒸馏禁用词并入 ${out.banned_added} 条`,
        undo: () => {
          toast.info(
            "蒸馏落卡不走撤销——历史快照在「重新蒸馏」旁保留；要回到上一版可重新蒸馏并锁定差异行",
          );
        },
      });
    } catch (e: unknown) {
      setError((e as Error).message || "落卡失败，可重试");
    } finally {
      setDistillBusy(false);
    }
  }

  // ── 渲染 ─────────────────────────────────────────────────────────
  if (loading) return <p className="opt">加载中…</p>;

  // 页签徽标：题材默认 ↔ 已自定义 · N 处（与首次加载快照比，N＝有差异的区数）
  let changed = 0;
  const preset = presetRef.current;
  if (preset) {
    if (role.trim() !== preset.role.trim()) changed += 1;
    if (JSON.stringify(rules.map((r) => r.trim()).filter(Boolean)) !== JSON.stringify(preset.rules))
      changed += 1;
    if (JSON.stringify(craft.map((c) => c.trim()).filter(Boolean)) !== JSON.stringify(preset.craft))
      changed += 1;
  }

  const totalSel =
    (samples?.files ?? []).filter((f) => selFiles.has(f.name)).reduce((a, f) => a + f.chars, 0) +
    (samples?.chapters ?? []).filter((c) => selChapters.has(c.id)).reduce((a, c) => a + c.chars, 0);
  const inRange = !!samples && totalSel >= samples.min && totalSel <= samples.max;
  const showDistill = distillView !== "closed";

  const STEPS: Array<[number, string, string]> = [
    [1, "读样本，逐段标注写法", "哪段在叙述、哪段在对话、情绪藏在动作里还是说出口"],
    [2, "统计写法习惯", "句长、对话占比、爱用的词、情绪怎么外化——拿数字说话"],
    [3, "归纳成六行基线和画像", "数字归基线（写章按「约 X（±容差）」执行），人话归画像（等你确认）"],
  ];

  return (
    <div>
      {error && (
        <p className="opt" style={{ color: "var(--err)" }} data-od-id="style-error">
          {error}
        </p>
      )}

      <div className="ptabs" data-od-id="style-tabs" role="tablist">
        <button
          className={`ptab${tab === "text" ? " on" : ""}`}
          type="button"
          role="tab"
          aria-selected={tab === "text"}
          data-tab="text"
          data-od-id="ptab-text"
          onClick={() => setTab("text")}
        >
          文字文风
          <span className={`badge ${changed > 0 ? "warn" : "ok"}`} data-od-id="style-tab-badge">
            {changed > 0 ? `已自定义 · ${changed} 处` : "题材默认"}
          </span>
        </button>
        <button
          className={`ptab${tab === "quant" ? " on" : ""}`}
          type="button"
          role="tab"
          aria-selected={tab === "quant"}
          data-tab="quant"
          data-od-id="ptab-quant"
          onClick={() => setTab("quant")}
        >
          量化参数
          <span className="ptab-pro">PRO</span>
          <span className={`badge ${quantReady ? "acc" : "empty"}`} data-od-id="quant-tab-badge">
            {quantReady ? `置信度 ${quant?.confidence}` : "未蒸馏"}
          </span>
        </button>
      </div>

      {tab === "text" ? (
        <div data-od-id="style-text-tab">
          <p className="opt" style={{ margin: "-2px 0 12px" }}>
            进页即按题材蓝图填好——要动笔的只有身份一句和几条红线，手法预填删改即可；蒸馏之前 AI 只按这部分写。
          </p>
          <div className="anchor-chain" data-od-id="chain-anchor">
            <button className="ac-node" type="button" onClick={() => document.getElementById("fRole")?.focus()}>
              叙事身份
            </button>
            <span className="ac-arrow" aria-hidden="true">→</span>
            <button className="ac-node" type="button" onClick={() => document.getElementById("fRules")?.focus()}>
              硬约束
            </button>
            <span className="ac-arrow" aria-hidden="true">→</span>
            <button className="ac-node" type="button" onClick={() => document.getElementById("fCraft")?.focus()}>
              描写层次和手法
            </button>
            <span className="ac-note">
              定镜头 → 立红线 → 给做法——先定身份，才知道不能做什么、用什么手法最自然。
            </span>
          </div>

          <div className="fblock" data-od-id="field-role">
            <div className="fb-head">
              <span className="fb-no">①</span>
              <b>叙事身份</b>
              <span className="hint">
                一句话说清两件事：<em>镜头离人多近</em>（贴主角／俯瞰全局）＋
                <em>叙述者什么态度</em>（冷静／共情／讽刺）。读了知道「我以什么身份在写」才算够。
              </span>
            </div>
            <textarea
              id="fRole"
              className="textarea"
              data-od-id="input-style-role"
              rows={2}
              value={role}
              onChange={(e) => setRole(e.target.value)}
            />
          </div>

          <div className="fblock" data-od-id="field-rules">
            <div className="fb-head">
              <span className="fb-no">②</span>
              <b>硬约束</b>
              <span className="hint">
                这个身份<em>绝对不能做什么</em>。每条都要能检查——最好带数量，超没超一眼看得出来（3–5 条）。
                风格特有的禁令写这里；通用 AI 腔词与高频句式归下方「禁用词」「句式规则」两组拦（同一处管体检）。
              </span>
            </div>
            <div data-od-id="list-rules">
              <ListEditor
                items={rules}
                onChange={setRules}
                onMoveUp={(i) => {
                  const n = [...rules];
                  [n[i - 1], n[i]] = [n[i], n[i - 1]];
                  setRules(n);
                }}
                showCount
                maxItems={5}
                placeholder="可执行的硬规则。例：「突然」每章不超过 4 次"
              />
            </div>
          </div>

          {/* 折叠组：禁用词（banned-words-into-style 收编，原「禁用词句」面板退役） */}
          <Cfg
            title="禁用词"
            tag="≤100 条"
            sum={`已填 ${banned.filter((w) => w.trim()).length} 条 · 出现在正文即拦；蒸馏学到的词自动并入去重`}
          >
            <div data-od-id="list-banned-words">
              <ListEditor
                items={banned.length ? banned : [""]}
                onChange={setBanned}
                maxLength={50}
                maxItems={100}
                placeholder="添加禁用词。如：本章讲述了、与此同时、他感到"
              />
            </div>
            <p className="opt" style={{ marginTop: 6 }}>
              通用 AI 腔词写这里（模板已按七类预填：总结叙事／抽象情绪／学术腔……）；
              <b>带量的风格禁令</b>（如「突然 ≤4 次/章」）写在上面②硬约束，两边不重复。
            </p>
          </Cfg>

          {/* 折叠组：句式规则 */}
          <Cfg
            title="句式规则"
            tag="≤20 条"
            sum={`已填 ${tics.filter((t) => t.pattern.trim()).length} 条 · 正则拦「不是…而是」类高频癖好，写完的章按条体检`}
          >
            <TicPatternEditor items={tics} onChange={setTics} />
            <p className="opt" style={{ marginTop: 6 }}>
              每条＝正则＋单章允许次数＋修复说明；写章提示词与程序化体检同源取这里（提示词注入前 5 条，体检全量）。
            </p>
          </Cfg>

          <div className="fblock" data-od-id="field-craft">
            <div className="fb-head">
              <span className="fb-no">③</span>
              <b>描写层次和手法</b>
              <span className="hint">
                已预填一套可用起点——<em>删改成你自己的即可</em>。每条给做法＋例子，读了能照着改一段（至多 8 条）。
              </span>
            </div>
            <div data-od-id="list-craft">
              <ListEditor
                items={craft}
                onChange={setCraft}
                onMoveUp={(i) => {
                  const n = [...craft];
                  [n[i - 1], n[i]] = [n[i], n[i - 1]];
                  setCraft(n);
                }}
                showCount
                maxItems={8}
                placeholder="可操作的手法＋例子。例：紧张时抠指甲，不写「他很紧张」"
              />
            </div>
          </div>

          <Cfg
            title="文风例句"
            tag="1–3 条"
            sum="最能代表目标文风的完整句子，AI 写章时照着这个手感写"
          >
            <div data-od-id="list-fewshots">
              <ListEditor
                items={fewShots}
                onChange={setFewShots}
                maxItems={3}
                placeholder="如：雨点砸在铁皮棚上，他没有抬头。"
              />
            </div>
            <p className="opt" style={{ marginTop: 6 }}>
              将作为案例段透传进整章写作提示词；没有也可以——蒸馏会替你从正文里挑。
            </p>
          </Cfg>

          {checkSink && (
            <div className="ai-sink" data-od-id="sink-style-check">
              <div className="aiz-head">AI 体检 · 文字文风三区锚定 × 禁用词（同源）</div>
              {checkSink.checks.map((c, i) => (
                <div className="chk-line" key={i}>
                  <span className="chk-name">{c.name}</span>
                  <span className={`chk-res ${checkResClass(c.res)}`}>{c.res}</span>
                  <span className="chk-note">{c.note}</span>
                </div>
              ))}
              {checkSink.verdict && (
                <p className="opt" style={{ marginTop: 6 }}>
                  {checkSink.verdict}
                </p>
              )}
              <div className="ans-act">
                <button className="primary" type="button" onClick={() => setCheckSink(null)}>
                  收起
                </button>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div data-od-id="style-quant-tab">
          {!quantReady && !showDistill && (
            <div className="sub-empty" data-od-id="quant-empty">
              <p className="se-t">还没有量化参数</p>
              <p className="se-s">
                只用「文字文风」就能写出合格的一章。
                <br />
                蒸馏是会员功能：交 3,000–10,000 字你认可的案例，AI 学出六行基线。
              </p>
              <div style={{ display: "flex", gap: 10, justifyContent: "center", flexWrap: "wrap" }}>
                <button
                  className="btn btn-primary"
                  type="button"
                  data-od-id="btn-open-paste"
                  onClick={() => setPasteOpen(true)}
                >
                  粘贴文本蒸馏
                </button>
                <button
                  className="btn btn-secondary"
                  type="button"
                  data-od-id="btn-open-distill"
                  onClick={() => void openDistill()}
                >
                  从文件/章节选样本
                </button>
              </div>
            </div>
          )}

          {quantReady && !showDistill && quant && (
            <div data-od-id="quant-panel">
              <div className="dims-meta">
                <span>主卡 general</span>
                <span className="num">v{quant.history.length || 1}</span>
                <span>{quant.updated_at || "—"}</span>
                <span className="num">{quant.sample_chars.toLocaleString()} 字样本</span>
                <span className="spacer" />
                <span>写章时按「约 X（±容差）」执行——章节的变化由写章 AI 按剧情自行调节</span>
                <span className="spacer" />
                <button
                  className="text-btn"
                  type="button"
                  data-od-id="btn-redistill"
                  onClick={() => void openDistill()}
                >
                  重新蒸馏
                </button>
              </div>
              <div className="dims" data-od-id="quant-baseline">
                {BASELINE_ROWS.map(([key, label]) => {
                  const row = quant.baseline[key];
                  if (!row) return null;
                  return (
                    <div className="bx-row" key={key}>
                      <div className="bx-head">
                        <span className="bx-name">{label}</span>
                        <button
                          className={`lock-btn${row.locked ? " on" : ""}`}
                          type="button"
                          data-od-id={`lock-${key}`}
                          aria-pressed={row.locked}
                          onClick={() => void toggleLock(key, !row.locked)}
                        >
                          {row.locked ? "已锁定 · 重蒸馏跳过" : "锁定"}
                        </button>
                      </div>
                      <div className="bx-vals">
                        约 {row.value}（±{row.tolerance}%）
                      </div>
                    </div>
                  );
                })}
              </div>
              {Object.keys(quant.details || {}).length > 0 && (
                <Cfg
                  title="统计明细"
                  tag="九维全量"
                  sum="蒸馏的原始账，只读——界面只常用上面 6 行，账本留给校准与争议"
                >
                  <div data-od-id="quant-details">
                    {Object.entries(quant.details).map(([k, v]) => (
                      <div className="det-row" key={k}>
                        <span className="dk">{k}</span>
                        <span className="dv2">{String(v)}</span>
                      </div>
                    ))}
                  </div>
                </Cfg>
              )}
              <p className="quant-note" data-od-id="quant-note">
                章节的量化变化不在这里设——写章的 AI 按本章剧情自行调节，容差就是它的法定空间；调节结果在章纲确认与写作现场可见。
              </p>
            </div>
          )}

          {showDistill && (
            <div data-od-id="distill-panel">
              {distillView !== "portrait" && (
                <>
                  {pasteText ? (
                    <div className="sample-box" data-od-id="distill-paste-source">
                      <div className="sample-row">
                        <span className="s-name">粘贴文本</span>
                        <span className="s-cnt num">{countSampleChars(pasteText).toLocaleString()} 字</span>
                      </div>
                      <div className="sample-total">
                        <span>本次蒸馏用你粘贴的文本；换文件/章节请先「取消」再重新选。</span>
                      </div>
                    </div>
                  ) : (
                    <div className="sample-box" data-od-id="distill-samples">
                      <div style={{ display: "flex", justifyContent: "flex-end" }}>
                        <button
                          className="text-btn"
                          type="button"
                          data-od-id="btn-open-paste"
                          onClick={() => setPasteOpen(true)}
                        >
                          直接粘贴文本
                        </button>
                      </div>
                    {(samples?.files ?? []).map((f) => (
                      <label className="sample-row" key={f.name}>
                        <input
                          type="checkbox"
                          checked={selFiles.has(f.name)}
                          onChange={(e) => {
                            const n = new Set(selFiles);
                            if (e.target.checked) n.add(f.name);
                            else n.delete(f.name);
                            setSelFiles(n);
                          }}
                        />
                        <span className="s-name">novel-samples/{f.name}</span>
                        <span className="s-cnt num">{f.chars.toLocaleString()} 字</span>
                      </label>
                    ))}
                    {(samples?.chapters ?? []).map((c) => (
                      <label className="sample-row" key={c.id}>
                        <input
                          type="checkbox"
                          checked={selChapters.has(c.id)}
                          onChange={(e) => {
                            const n = new Set(selChapters);
                            if (e.target.checked) n.add(c.id);
                            else n.delete(c.id);
                            setSelChapters(n);
                          }}
                        />
                        <span className="s-name">{c.label}</span>
                        <span className="s-cnt num">{c.chars.toLocaleString()} 字</span>
                      </label>
                    ))}
                    <div className="sample-total">
                      <span>
                        合计 <b className="num">{totalSel.toLocaleString()}</b> 字
                        {samples != null &&
                          `（区间 ${samples.min.toLocaleString()}–${samples.max.toLocaleString()}）`}
                      </span>
                      {samples != null && !samples.in_range && totalSel > 0 && (
                        <span className="opt">{samples.hint}</span>
                      )}
                    </div>
                    </div>
                  )}

                  {distillStep > 0 && (
                    <div className="sample-box" style={{ marginTop: 12 }} data-od-id="distill-steps">
                      {STEPS.map(([no, t, d]) => {
                        const done = distillStep >= no;
                        return (
                          <div className={`dist-step${done ? "" : " pending"}`} key={no}>
                            <span className="ds-no">{no}</span>
                            <span className="ds-b">
                              <b>{t}</b>
                              <i>{d}</i>
                            </span>
                            {done && (
                              <span className="ds-ok">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" width="12" height="12">
                                  <path d={CHECK_PATH} />
                                </svg>
                                完成
                              </span>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}

                  <div className="pz-act" style={{ marginTop: 12 }}>
                    <button
                      className="btn btn-primary"
                      type="button"
                      data-od-id="btn-run-distill"
                      disabled={distillBusy || (distillStep === 0 && samples != null && !inRange)}
                      onClick={() =>
                        // 粘贴链重试必须显式从 step1 起跑：state distillStep 可能还挂着
                        // 旧蒸馏的步数（甚至旧 draft 的步数），而带 text 的 step1 是重启语义
                        void runSteps(1, false, pasteText ? { text: pasteText, startStep: 0 } : undefined)
                      }
                    >
                      {distillBusy ? "蒸馏中…" : distillStep === 0 ? "开始蒸馏" : "继续蒸馏"}
                    </button>
                    <button className="btn btn-ghost" type="button" onClick={() => closeDistill()}>
                      取消
                    </button>
                    {samples != null && !samples.in_range && distillStep === 0 && (
                      <span className="opt">{samples.hint}</span>
                    )}
                  </div>
                </>
              )}

              {distillView === "portrait" && draft?.step3?.portrait && (
                <div className="portrait" data-od-id="author-portrait">
                  <div className="pz-head">作者画像</div>
                  <p className="pz-note">
                    以下是你文风在 AI 眼里的理解——不是文学评价，AI 会照着这个写。哪里不对直接说。
                  </p>
                  <p>{draft.step3.portrait}</p>
                  <p className="pz-ask">读起来像你的写法吗？不像 → 直接说「不像」，我会再学一次。</p>
                  {draft.step3.rows && (
                    <div style={{ marginTop: 12 }} data-od-id="portrait-baseline-preview">
                      <div className="pz-head">落卡基线预览</div>
                      <p className="pz-note" style={{ marginBottom: 8 }}>
                        确认后原样写入量化参数；带「保留上一版」的行是你的锁定行——这次不更新。
                      </p>
                      {BASELINE_ROWS.map(([key, label]) => {
                        const row = draft.step3?.rows?.[key];
                        if (!row) return null;
                        const prev = quant?.baseline?.[key];
                        return (
                          <div className="bx-row" key={key}>
                            <div className="bx-head">
                              <span className="bx-name">{label}</span>
                              {prev && prev.locked && <span className="badge empty">保留上一版</span>}
                            </div>
                            <div className="bx-vals">
                              {/* 锁定行落卡＝{**新行, value: 上一版}——value 保留旧值，容差取新构建行值（评审 P2：预览＝落卡逐字段一致） */}
                              {prev && prev.locked
                                ? `约 ${prev.value || "（上一版为空）"}（±${row.tolerance}%）`
                                : `约 ${row.value}（±${row.tolerance}%）`}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                  <div className="pz-act">
                    <button
                      className="btn btn-primary"
                      type="button"
                      data-od-id="btn-portrait-keep"
                      disabled={distillBusy}
                      onClick={() => void commitPortrait()}
                    >
                      就是这样，落卡
                    </button>
                    <button
                      className="btn btn-ghost"
                      type="button"
                      data-od-id="btn-portrait-retry"
                      disabled={distillBusy}
                      onClick={() => {
                        setDistillView("steps");
                        void runSteps(3, true);
                      }}
                    >
                      不像，再学一次
                    </button>
                    <button
                      className="btn btn-ghost"
                      type="button"
                      data-od-id="btn-portrait-later"
                      disabled={distillBusy}
                      onClick={() => closeDistill()}
                    >
                      取消，稍后再说
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <StylePasteModal
        open={pasteOpen}
        onClose={() => setPasteOpen(false)}
        onSubmit={(t) => void startPasteDistill(t)}
      />
    </div>
  );
});

export default StyleSettingForm;
