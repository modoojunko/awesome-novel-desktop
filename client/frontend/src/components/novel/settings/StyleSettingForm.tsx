// 文风设定 v2（style-settings-v2）：面板内两页签。
//   文字文风（免费，三区：叙事身份必填/硬约束/描写手法题材预填删改 ＋ 例句 1–3 折叠）
//   量化参数（PRO：蒸馏 3,000–10,000 字样本 → 作者画像确认 → 六行基线只读＋行级锁定）
//
// 契约要点（评审 P0 落纸）：
//   · 撤并键（possible_mistakes/narrator_role/tone）零写回——save() payload 白名单
//     只带 role/rules/craft/few_shot_examples；归一与迁移在后端 put_style 边界
//   · 量化基线只读：前端唯一写路径是行级锁定切换（styleQuantApi.putLocks）
//   · 蒸馏三步端点串联，每步产物落 style-quant.draft，中断续跑；「不像再学一次」＝
//     step3 带 force 重跑；commit 幂等并服务端并入禁用词句
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
import type { ChangeReceiptState } from "./ChangeReceipt";
import { styleAiApi, styleQuantApi, BASELINE_ROWS } from "@/lib/styleApi";
import type { StyleQuant } from "@/lib/styleApi";
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
  const [checkSink, setCheckSink] = useState<{
    checks: Array<{ name: string; res: string; note: string }>;
    verdict: string;
  } | null>(null);

  const shape = useMemo(
    () => ({ role, rules, craft, fewShots }),
    [role, rules, craft, fewShots],
  );
  const { isDirty, snapshotLoaded, markSaved } = useDirtyState(shape, onDirtyChange);

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
        setRole(roleN);
        setRules(rulesN.length ? rulesN : [""]);
        setCraft(craftN.length ? craftN : [""]);
        setFewShots(fewN.slice(0, 3).length ? fewN.slice(0, 3) : [""]);
        presetRef.current = { role: roleN, rules: rulesN, craft: craftN };
        setQuant(quant);
        snapshotLoaded({ role: roleN, rules: rulesN, craft: craftN, fewShots: fewN });
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
      // 白名单 payload（撤并键零写回）：role/rules/craft/few_shot_examples 之外不带
      await api.put(`/novels/${projectId}/settings/style`, {
        role: role.trim(),
        rules: rules.map((r) => r.trim()).filter(Boolean),
        craft: craft.map((c) => c.trim()).filter(Boolean).slice(0, 8),
        few_shot_examples: fewShots.map((s) => s.trim()).filter(Boolean).slice(0, 3),
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

  async function runSteps(from: 1 | 3, force = false) {
    if (distillBusy) return;
    setDistillBusy(true);
    setError("");
    try {
      let step: 0 | 1 | 2 | 3 = distillStep;
      if (from === 1) {
        while (step < 3) {
          const next = (step + 1) as 1 | 2 | 3;
          const body =
            next === 1
              ? { files: [...selFiles], chapter_ids: [...selChapters] }
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
      if (q.draft?.step3?.portrait) setDistillView("portrait");
    } catch (e: unknown) {
      setError((e as Error).message || "蒸馏失败，可重试");
    } finally {
      setDistillBusy(false);
    }
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
      toast.success("画像已确认——六行基线更新了，写章时生效");
      publishReceipt({
        text: `已落卡：六行基线更新（置信度 ${out.quant.confidence}）· 蒸馏禁用词并入 ${out.banned_added} 条`,
        undo: () =>
          toast.info(
            "蒸馏落卡不走撤销——历史快照在「重新蒸馏」旁保留；要回到上一版可重新蒸馏并锁定差异行",
          ),
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
                这个身份<em>绝对不能做什么</em>。每条都要能检查——超没超，一眼看得出来（3–5 条）。
                风格特有的禁令写这里；通用的 AI 词句归「禁用词句」面板拦。
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
              <div className="aiz-head">AI 体检 · 文字文风三区锚定 × 禁用词句</div>
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
              <button
                className="btn btn-secondary"
                type="button"
                data-od-id="btn-open-distill"
                onClick={() => void openDistill()}
              >
                去蒸馏我的文风
              </button>
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
                  <div className="sample-box" data-od-id="distill-samples">
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
                      onClick={() => void runSteps(distillStep === 0 ? 1 : 1)}
                    >
                      {distillBusy ? "蒸馏中…" : distillStep === 0 ? "开始蒸馏" : "继续蒸馏"}
                    </button>
                    <button className="btn btn-ghost" type="button" onClick={() => setDistillView("closed")}>
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
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
});

export default StyleSettingForm;
