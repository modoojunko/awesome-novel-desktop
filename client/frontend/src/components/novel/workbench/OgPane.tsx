// 章纲面板（book.html renderOgPane 复刻）：留存格子按 details.cfg 分组
// + 主情绪选择（9 选 + 自定义 ≤50）
// + 读者获得列表（类型 + 描述）、章末落点、本章目标字数、碰到的挑战、阶段。
// 确认缺读者获得时仅提醒不阻断（存量章不回溯）。
// + 剧情区（c-plot-split 条目列表）、缺字段 chip（点击滚动 flash 1400ms + focus）+ 底部三按钮。
// 必填口径 = 后端 gate_chapter_ready 两项（必须完成的变化、主情绪；c-og-slim-v2 四改二）。
// c-og-slim-v2 退役格子：关键事件/地点/时间/叙事视角/视角指导/预期策略/预期细节/
// 可部分推进/段落规划/本章行动/场景卡（含权重与焦点）——控件与折叠组整组摘除。
// 2026-09-27 查看/编辑两态（对齐卷纲 c-volume-view-storyline 口径）：
//   默认查看态＝一页纸只读（.fro 行，未填占位可见）＋「编辑章纲」进表单；
//   缺项 chip 查看态点击＝进编辑态并滚动聚焦对应格子；取消＝回退最近一次落库值。
import { useRef, useState } from "react";
import { toast } from "@/lib/toast";
import {
  PAYOFF_KINDS,
  PLOT_MAX_ITEMS,
  PLOT_MAX_LEN,
  type OgForm,
  type OgPayoff,
} from "./chapterForm";

interface OgPaneProps {
  form: OgForm;
  /** 本书角色名清单（character-settings-v2）：出场角色多选候选取这里 */
  characterNames?: string[];
  /** 完整章标题（第X章 · 名称，nodeLabel 派生）——原型 panel-head 口径 */
  label: string;
  /** 查看/编辑两态：false＝只读一页纸（默认），true＝表单可写 */
  editing: boolean;
  /** 章纲载入中（查看态据此显示载入中） */
  loading?: boolean;
  onPatch: (patch: Partial<OgForm>) => void;
  /** 剧情区编辑（输入/加/删任一动作）：上层用来收掉常驻采纳回执（拍板②）＋触发润色软提示检查 */
  onPlotEdit?: () => void;
  gaps: { key: string; label: string }[];
  confirmed: boolean;
  saving: boolean;
  onStartEdit: () => void;
  onCancelEdit: () => void;
  /** 查看态缺口 chip：进编辑态并滚动聚焦该格（上层包 flashField） */
  onGapClick: (key: string) => void;
  onSaveDraft: () => void;
  onConfirm: () => void;
  onGoWrite: () => void;
  /** 名单区没卡标旁的行级建卡入口（c-character-intro 4.1；只预填称呼） */
  onQuickCreateChar?: (name: string) => void;
  /** 本书主角名（role=主角的主卡名；名单缺人探测置顶标，c-character-intro 6.x） */
  protagonistName?: string;
}

const MOODS = ["紧张", "悬疑", "温暖", "悲伤", "激昂", "轻松", "压抑", "浪漫", "惊悚"];

const PLOT_PLACEHOLDER =
  "写这一段发生什么：谁在场、在哪、遇到了什么——是场景不是正文，200 字以内";

export function flashField(key: string) {
  const el = document.getElementById(`wf-${key}`);
  if (!el) return;
  // 收起的 details 组先展开（挑战/落点在默认收起组里，不然滚动聚焦都落空）
  el.closest("details")?.setAttribute("open", "");
  el.scrollIntoView({ behavior: "smooth", block: "start" });
  el.classList.add("flash");
  setTimeout(() => el.classList.remove("flash"), 1400);
  // 容器 id（details/field）里找可聚焦控件；id 挂在控件自身时聚焦自身
  const focusable = (
    el.matches("input, textarea, select") ? el : el.querySelector("input, textarea, select")
  ) as HTMLElement | null;
  focusable?.focus({ preventScroll: true });
}

const payoffLabel = (k: string) =>
  PAYOFF_KINDS.find((x) => x.value === k)?.label ?? k;

/** 多行文本格的查看态文案：非空行以「；」连接；空 → 未填占位 */
const joinLines = (s: string) => {
  const ls = s.split("\n").map((x) => x.trim()).filter(Boolean);
  return ls.length ? ls.join("；") : "";
};

export default function OgPane({
  form,
  characterNames,
  label,
  editing,
  loading,
  onPatch,
  onPlotEdit,
  gaps,
  confirmed,
  saving,
  onStartEdit,
  onCancelEdit,
  onGapClick,
  onSaveDraft,
  onConfirm,
  onGoWrite,
  onQuickCreateChar,
  protagonistName,
}: OgPaneProps) {
  const moodVal = form.mood || "";
  const moodCustom = moodVal && !MOODS.includes(moodVal) ? moodVal : "";
  const moodSel = moodCustom ? "__custom" : moodVal;
  const payoffFilled = form.payoffs.some((p) => p.d.trim());
  // 缺读者获得的确认提醒：一次会话提醒一次，不阻断确认（存量章不回溯）
  const [payoffReminded, setPayoffReminded] = useState(false);
  const showPayoffHint = payoffReminded && !payoffFilled;
  // 名单缺人探测的「忽略」记录（按章；会话内——c-character-intro 6.x 通用逻辑）
  const [missIgnored, setMissIgnored] = useState<Record<string, string[]>>({});

  // 剧情行稳定 key（禁 index key——删除时 React 不得错位复用 textarea）：
  // 平行 id 数组随显示行数伸缩，删除在 delPlot 里同步摘掉对应 id
  const plotSeq = useRef(0);
  const plotIds = useRef<number[]>([]);
  const plotRows = form.plots.length ? form.plots : [""];
  while (plotIds.current.length < plotRows.length) plotIds.current.push(++plotSeq.current);
  if (plotIds.current.length > plotRows.length) plotIds.current.length = plotRows.length;

  const patchPayoff = (i: number, patch: Partial<OgPayoff>) => {
    const payoffs = form.payoffs.slice();
    payoffs[i] = { ...payoffs[i], ...patch };
    onPatch({ payoffs });
  };
  const patchPlot = (i: number, v: string) => {
    const plots = form.plots.slice();
    while (plots.length <= i) plots.push("");
    plots[i] = v;
    onPatch({ plots });
    onPlotEdit?.();
  };
  const addPlot = () => {
    if (form.plots.length >= PLOT_MAX_ITEMS) {
      toast.info("最多 12 条剧情");
      return;
    }
    // 空表点「加一条」＝两行（原型口径：先把隐含的第一行落成真行，再加一行）
    onPatch({ plots: form.plots.length ? form.plots.concat([""]) : ["", ""] });
    onPlotEdit?.();
  };
  const delPlot = (i: number) => {
    const plots = form.plots.slice();
    if (i >= plots.length) return; // 空态占位行：删不动真实数据
    plots.splice(i, 1);
    plotIds.current.splice(i, 1);
    onPatch({ plots });
    onPlotEdit?.();
  };

  const badge = confirmed ? (
    <span className="badge ok">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
        <path d="M5 13l4 4L19 7" />
      </svg>
      章纲已确认
    </span>
  ) : gaps.length ? (
    <span className="badge err">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
        <circle cx="12" cy="12" r="5" fill="currentColor" stroke="none" />
      </svg>
      待配章纲
    </span>
  ) : (
    <span className="badge warn">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
        <circle cx="12" cy="12" r="5" fill="currentColor" stroke="none" />
      </svg>
      草稿
    </span>
  );

  // 名单缺人探测（c-character-intro 通用逻辑，每章查看/编辑都在场）：有卡角色
  // （含别名）被本章文字点名但不在出场名单——确定性文本匹配（零 AI）；主角置顶。
  // 「加入」走 form.chars＋onPatch（3s 自动保存链落库）；「忽略」按章会话内记忆。
  const chapterText = [form.summary ?? "", ...(form.plots ?? [])].join("\n");
  const castLines = form.chars.split("\n").map((x) => x.trim()).filter(Boolean);
  const missingNamed = (characterNames ?? [])
    .filter((n) => n && !castLines.includes(n) && chapterText.includes(n))
    .filter((n, i, arr) => arr.indexOf(n) === i)
    .sort((a, b) => (a === protagonistName ? -1 : b === protagonistName ? 1 : 0))
    .filter((n) => !(missIgnored[label] ?? []).includes(n));
  const addToCast = (n: string) => {
    const lines = (form.chars || "").split("\n").map((x) => x.trim()).filter(Boolean);
    if (!lines.includes(n)) lines.push(n);
    onPatch({ chars: lines.join("\n") });
  };
  const ignoreMiss = (n: string) => {
    const key = label;
    setMissIgnored((d) => ({ ...d, [key]: [...(d[key] ?? []), n] }));
  };
  const missBlock = missingNamed.length > 0 && (
    <div className="cast-miss" data-testid="cast-missing">
      <b>剧情点名、名单没有：</b>
      {missingNamed.map((n) => (
        <span className="chip" key={n} data-testid={`cast-miss-${n}`}>
          {n}
          {n === protagonistName && <span className="no-card">主角</span>}
          <button
            className="lnk"
            data-testid={`cast-add-${n}`}
            title="加进出场名单（走 3 秒自动保存落库）"
            onClick={() => addToCast(n)}
          >
            加入
          </button>
          <button
            className="lnk cast-ig"
            data-testid={`cast-ignore-${n}`}
            aria-label={`忽略「${n}」`}
            title="忽略本条（会话内记忆，不落库）"
            onClick={() => ignoreMiss(n)}
          >
            ×
          </button>
        </span>
      ))}
    </div>
  );

  // ── 查看态（默认）：一页纸只读，未填项占位可见；编辑章纲进表单 ──────────
  if (!editing) {
    if (loading) {
      return (
        <div className="og-pane">
          <div className="panel">
            <div className="panel-head">
              <h2>章纲 · {label}</h2>
              {badge}
            </div>
            <p className="desc">章纲载入中…</p>
          </div>
        </div>
      );
    }
    const charLines = form.chars.split("\n").map((x) => x.trim()).filter(Boolean);
    const known = new Set(characterNames ?? []);
    // 名单缺人探测（c-character-intro 通用逻辑，每章查看/编辑都在场）：有卡角色
    // （含别名）被本章文字点名但不在出场名单——确定性文本匹配（零 AI）；主角置顶。
    // 「加入」走 form.chars＋onPatch（3s 自动保存链落库）；「忽略」按章会话内记忆。
    const chapterText = [form.summary ?? "", ...(form.plots ?? [])].join("\n");
    const missingNamed = (characterNames ?? [])
      .filter((n) => n && !charLines.includes(n) && chapterText.includes(n))
      .filter((n, i, arr) => arr.indexOf(n) === i)
      .sort((a, b) => (a === protagonistName ? -1 : b === protagonistName ? 1 : 0))
      .filter((n) => !(missIgnored[label] ?? []).includes(n));
    const addToCast = (n: string) => {
      const lines = (form.chars || "").split("\n").map((x) => x.trim()).filter(Boolean);
      if (!lines.includes(n)) lines.push(n);
      onPatch({ chars: lines.join("\n") });
    };
    const ignoreMiss = (n: string) => {
      const key = label;
      setMissIgnored((d) => ({ ...d, [key]: [...(d[key] ?? []), n] }));
    };
    const missBlock = missingNamed.length > 0 && (
      <div className="cast-miss" data-testid="cast-missing">
        <b>剧情点名、名单没有：</b>
        {missingNamed.map((n) => (
          <span className="chip" key={n} data-testid={`cast-miss-${n}`}>
            {n}
            {n === protagonistName && <span className="no-card">主角</span>}
            <button
              className="lnk"
              data-testid={`cast-add-${n}`}
              title="加进出场名单（走 3 秒自动保存落库）"
              onClick={() => addToCast(n)}
            >
              加入
            </button>
            <button
              className="lnk cast-ig"
              data-testid={`cast-ignore-${n}`}
              aria-label={`忽略「${n}」`}
              title="忽略本条（会话内记忆，不落库）"
              onClick={() => ignoreMiss(n)}
            >
              ×
            </button>
          </span>
        ))}
      </div>
    );
    const plotItems = form.plots.map((s) => s.trim()).filter(Boolean);
    const filledPayoffs = form.payoffs.filter((p) => p.d.trim());
    return (
      <div className="og-pane" data-testid="og-view">
        <div className="panel">
          <div className="panel-head">
            <h2>章纲 · {label}</h2>
            {badge}
          </div>
          <div className="ol-top">
            <span className="note">章纲 · 明确「这一章写什么」</span>
            <span className="push">
              <button
                className="btn btn-primary"
                style={{ background: "var(--accent-strong)" }}
                onClick={onGoWrite}
                disabled={saving}
              >
                去写正文
              </button>
              <button
                className="btn btn-secondary"
                onClick={onConfirm}
                disabled={confirmed || gaps.length > 0 || saving}
              >
                确认章纲
              </button>
              <button
                className="btn btn-secondary"
                data-testid="og-edit"
                onClick={onStartEdit}
              >
                编辑章纲
              </button>
            </span>
          </div>
          <div className="fro">
            <em>章纲概要</em>
            <p className={form.summary.trim() ? "lead" : "none"}>
              {form.summary.trim() || "（未填）"}
            </p>
          </div>
          {missBlock}
          <div className="fro">
            <em>出场角色</em>
            {charLines.length ? (
              // 查看态逐名渲染（c-character-intro 4.1）：chip＋没卡标＋建卡入口（照读者获得行多子节点先例）
              <div className="og-char-picker" data-testid="og-cast-view">
                {charLines.map((n) => (
                  <span className="chip" key={n}>
                    {n}
                    {!known.has(n) && <span className="no-card">没卡</span>}
                    {!known.has(n) && onQuickCreateChar && (
                      <button
                        className="lnk"
                        data-testid={`claim-${n}`}
                        title="用这个名字建一张角色卡（只带名字，卡面回头在设定页补）"
                        onClick={() => onQuickCreateChar(n)}
                      >
                        建卡
                      </button>
                    )}
                  </span>
                ))}
              </div>
            ) : (
              <p className="none">（未填）</p>
            )}
          </div>
          <div className="fro">
            <em>碰到的挑战</em>
            <p className={form.challenge.trim() ? undefined : "none"}>
              {form.challenge.trim() || "（未填）"}
            </p>
          </div>
          <div className="fro">
            <em>阶段</em>
            <p className={form.stage.trim() ? undefined : "none"}>
              {form.stage.trim() || "（未定）"}
            </p>
          </div>
          <div className="fro">
            <em>必须在本章回收</em>
            <p className={joinLines(form.mres) ? undefined : "none"}>
              {joinLines(form.mres) || "（未填）"}
            </p>
          </div>
          <div className="fro">
            <em>必须维持悬念</em>
            <p className={joinLines(form.mhold) ? undefined : "none"}>
              {joinLines(form.mhold) || "（未填）"}
            </p>
          </div>
          <div className="fro">
            <em>必须完成的变化 <span className="req">*</span></em>
            <p className={joinLines(form.changes) ? undefined : "none"}>
              {joinLines(form.changes) || "（未填）"}
            </p>
          </div>
          <div className="fro">
            <em>禁止事项</em>
            <p className={joinLines(form.ban) ? undefined : "none"}>
              {joinLines(form.ban) || "（未填）"}
            </p>
          </div>
          <div className="fro">
            <em>主情绪 <span className="req">*</span></em>
            <p className={form.mood.trim() ? undefined : "none"}>
              {form.mood.trim() || "（未填）"}
            </p>
          </div>
          <div className="fro">
            <em>读者获得</em>
            {filledPayoffs.length ? (
              <div>
                {filledPayoffs.map((p, i) => (
                  <p key={i}>
                    {payoffLabel(p.k)} · {p.d.trim()}
                  </p>
                ))}
              </div>
            ) : (
              <p className="none">未设置——可后补，不拦截确认</p>
            )}
          </div>
          <div className="fro">
            <em>章末落点</em>
            <p className={form.ladder.trim() ? undefined : "none"}>
              {form.ladder.trim() || "（未填）"}
            </p>
          </div>
          <div className="fro">
            <em>本章目标字数</em>
            <p>{form.wt.trim() ? `${form.wt} 字` : "默认 2500"}</p>
          </div>
          <div className="fro">
            <em>
              剧情 <span className="tag">{plotItems.length} 条</span>
            </em>
            {plotItems.length === 0 ? (
              <p className="none">还没有剧情条目——不填也能写</p>
            ) : (
              <div>
                {plotItems.map((t, i) => (
                  <p key={i} style={{ margin: "0 0 6px" }}>
                    <span className="qno">{String(i + 1).padStart(2, "0")}</span> {t}
                  </p>
                ))}
              </div>
            )}
          </div>
          {gaps.length > 0 && (
            <p className="gap-line">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <circle cx="12" cy="12" r="9" />
                <path d="M12 8v4M12 16h.01" />
              </svg>
              缺：
              {gaps.map((g) => (
                <span
                  key={g.key}
                  className="gap-chip"
                  role="button"
                  tabIndex={0}
                  onClick={() => onGapClick(g.key)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") onGapClick(g.key);
                  }}
                >
                  {g.label}
                </span>
              ))}
            </p>
          )}
        </div>
      </div>
    );
  }

  // 编辑态：表单里有、候选里没有的名字＝没卡（别名已并入候选，不会误标）
  const knownNames = new Set(characterNames ?? []);
  const extraCharNames = form.chars
    .split("\n")
    .map((x) => x.trim())
    .filter(Boolean)
    .filter((n) => !knownNames.has(n))
    .filter((n, i, arr) => arr.indexOf(n) === i);

  return (
    <div className="og-pane">
      <div className="panel">
        <div className="panel-head">
          <h2>章纲 · {label}</h2>
          {/* AI 起草/剧情推演入口收口右栏 AI 助手（2026-09-20），此处不再设按钮 */}
          {badge}
        </div>
        <p className="desc">章纲：明确「这一章写什么」，确认后可作为 AI 生成正文的章级上下文。</p>

        <details className="cfg" open>
          <summary>
            章纲概要 <Chev />
          </summary>
          <div className="inner">
            <div className="field">
              <label>章纲概要</label>
              <textarea
                className="textarea"
                id="wf-summary"
                placeholder="这一章写什么，一两句话说清"
                value={form.summary}
                onChange={(e) => onPatch({ summary: e.target.value })}
              />
            </div>
            <div className="field">
              <label>
                出场角色 <span className="opt">点选角色卡；也可直接输入名字</span>
              </label>
              {missBlock}
              {((characterNames && characterNames.length > 0) || extraCharNames.length > 0) && (
                <div className="og-char-picker" role="group" aria-label="从角色卡选择出场角色">
                  {(characterNames ?? []).map((n) => {
                    const on = form.chars.split("\n").some((line) => line.trim() === n);
                    return (
                      <button
                        key={n}
                        type="button"
                        className={`chip${on ? " on" : ""}`}
                        onClick={() => {
                          const lines = form.chars
                            .split("\n")
                            .map((x) => x.trim())
                            .filter(Boolean);
                          const next = on
                            ? lines.filter((x) => x !== n)
                            : [...lines, n];
                          onPatch({ chars: next.join("\n") });
                        }}
                      >
                        {n}
                      </button>
                    );
                  })}
                  {/* 非候选名字 chip（c-character-intro 4.1）：没卡标＋建卡入口；textarea 照旧 */}
                  {extraCharNames.map((n) => (
                    <span className="chip" key={`extra-${n}`}>
                      {n}
                      <span className="no-card">没卡</span>
                      {onQuickCreateChar && (
                        <button
                          className="lnk"
                          data-testid={`claim-${n}`}
                          title="用这个名字建一张角色卡（只带名字，卡面回头在设定页补）"
                          onClick={() => onQuickCreateChar(n)}
                        >
                          建卡
                        </button>
                      )}
                    </span>
                  ))}
                </div>
              )}
              <textarea
                className="textarea"
                id="wf-chars"
                placeholder="角色名（一行一个）"
                value={form.chars}
                onChange={(e) => onPatch({ chars: e.target.value })}
              />
            </div>
            <div className="tpl-row">
              <div className="field">
                <label>
                  碰到的挑战 <span className="opt">拆章填的「这一章要撞的墙」</span>
                </label>
                <input
                  className="input"
                  id="wf-challenge"
                  placeholder="如：旧档堆不对活人开放——查档本身就要违规"
                  value={form.challenge}
                  onChange={(e) => onPatch({ challenge: e.target.value })}
                />
              </div>
              <div className="field">
                <label>
                  阶段 <span className="opt">本章在卷剧情里的位置</span>
                </label>
                <select
                  className="input"
                  id="wf-stage"
                  value={form.stage}
                  onChange={(e) => onPatch({ stage: e.target.value })}
                >
                  {["开局铺垫", "冲突初现", "矛盾升级", "重要转折", "高潮爆发", "卷末收束"].map((st) => (
                    <option key={st} value={st}>{st}</option>
                  ))}
                </select>
              </div>
            </div>
          </div>
        </details>

        <details className="cfg" open>
          <summary>
            兑现与约束 <Chev />
          </summary>
          <div className="inner">
            <div className="field">
              <label>
                必须在本章回收 <span className="opt">一行一个</span>
              </label>
              <textarea
                className="textarea"
                id="wf-mres"
                placeholder="一个必须回收的伏笔"
                value={form.mres}
                onChange={(e) => onPatch({ mres: e.target.value })}
              />
            </div>
            <div className="field">
              <label>
                必须维持悬念 <span className="opt">一行一个</span>
              </label>
              <textarea
                className="textarea"
                id="wf-mhold"
                placeholder="一个必须维持的悬念"
                value={form.mhold}
                onChange={(e) => onPatch({ mhold: e.target.value })}
              />
            </div>
            <div className="field">
              <label>
                必须完成的变化 <span className="req">*</span>
              </label>
              <textarea
                className="textarea"
                id="wf-changes"
                placeholder="一个必须发生的变化"
                value={form.changes}
                onChange={(e) => onPatch({ changes: e.target.value })}
              />
            </div>
            <div className="field">
              <label>
                禁止事项 <span className="opt">一行一个</span>
              </label>
              <textarea
                className="textarea"
                id="wf-ban"
                placeholder="一个禁止发生的事"
                value={form.ban}
                onChange={(e) => onPatch({ ban: e.target.value })}
              />
            </div>
          </div>
        </details>

        <details className="cfg" open>
          <summary>
            情绪设计 <Chev />
          </summary>
          <div className="inner">
            <div className="field" id="wf-mood">
              <label>
                主情绪 <span className="req">*</span>
              </label>
              <div className="mood-row">
                <select
                  className="input"
                  value={moodSel}
                  onChange={(e) => {
                    const v = e.target.value;
                    onPatch({ mood: v === "__custom" ? "" : v });
                  }}
                >
                  <option value="">请选择主情绪</option>
                  {MOODS.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                  <option value="__custom">自定义…</option>
                </select>
                {moodSel === "__custom" && (
                  <input
                    className="input"
                    placeholder="输入自定义情绪（≤50 字）"
                    maxLength={50}
                    value={moodCustom}
                    onChange={(e) => onPatch({ mood: e.target.value })}
                  />
                )}
              </div>
            </div>
          </div>
        </details>

        <details className="cfg" id="wf-payoffs">
          <summary>
            读者获得与章末落点 <span className="opt">提示词原材料 · 可空</span>
            <Chev />
          </summary>
          <div className="inner">
            <p
              className="note"
              style={{ fontSize: "12.5px", color: "var(--muted)", margin: "0 0 10px" }}
            >
              读者获得 = 本章给读者的爽点（拿到什么/看清什么/情绪被什么击中）。
            </p>
            {showPayoffHint && (
              <p
                className="note"
                data-testid="payoff-hint"
                style={{ fontSize: "12.5px", color: "var(--warn, #b8860b)", margin: "0 0 10px" }}
              >
                本章未设置读者获得——可后补，不拦截确认。
              </p>
            )}
            <div className="seg-list" data-testid="payoff-list">
              {form.payoffs.map((mp, i) => (
                <div className="payoff-row" key={i} data-payoff={i}>
                  <select
                    className="input"
                    data-payoff="k"
                    title="类型"
                    value={mp.k}
                    onChange={(e) => patchPayoff(i, { k: e.target.value })}
                  >
                    {PAYOFF_KINDS.map((x) => (
                      <option key={x.value} value={x.value}>
                        {x.label}
                      </option>
                    ))}
                  </select>
                  <input
                    className="input"
                    data-payoff="d"
                    placeholder="一句话描述，如：主角拿到半块玉佩"
                    value={mp.d}
                    onChange={(e) => patchPayoff(i, { d: e.target.value })}
                  />
                  <span className="acts">
                    <button
                      className="icon-btn"
                      title="删除"
                      onClick={() => {
                        const payoffs = form.payoffs.slice();
                        payoffs.splice(i, 1);
                        onPatch({ payoffs });
                      }}
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" />
                      </svg>
                    </button>
                  </span>
                </div>
              ))}
            </div>
            <div className="seg-add-row">
              <button
                className="btn btn-secondary btn-sm sub-add"
                data-add="payoff"
                onClick={() =>
                  onPatch({ payoffs: [...form.payoffs, { k: "clue", d: "" }] })
                }
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 5v14M5 12h14" />
                </svg>
                添加读者获得
              </button>
            </div>
            <div className="tpl-row">
              <div className="field">
                <label>
                  章末落点 <span className="opt">结尾停在哪个紧张度上</span>
                </label>
                <input
                  className="input"
                  id="wf-ladder"
                  placeholder="如：拿到半张地图，连夜出门，更不安"
                  value={form.ladder}
                  onChange={(e) => onPatch({ ladder: e.target.value })}
                />
              </div>
              <div className="field">
                <label>
                  本章目标字数 <span className="opt">500-6000，留空默认 2500</span>
                </label>
                <input
                  className="input num"
                  id="wf-wt"
                  type="number"
                  min={500}
                  max={6000}
                  step={100}
                  placeholder="2500"
                  value={form.wt}
                  onChange={(e) => onPatch({ wt: e.target.value })}
                />
              </div>
            </div>
          </div>
        </details>

        {/* 章内剧情（c-plot-split）：条目=场景描述非正文；一条一段、≤200 字、≤12 条；不填也能写 */}
        <section className="plot-sec" data-od-id="plot-section">
          <div className="plot-sec-head">
            <h3>剧情</h3>
            <span className="hint-inline">一条一段 · 每条 200 字以内 · 不填也能写</span>
          </div>
          <div className="pi-list">
            {plotRows.map((t, i) => (
              <div key={plotIds.current[i]} data-i={i}>
                <p className="pi-no">{String(i + 1).padStart(2, "0")}</p>
                <div className="pi-row">
                  <textarea
                    aria-label={`第 ${i + 1} 条剧情`}
                    maxLength={PLOT_MAX_LEN}
                    placeholder={PLOT_PLACEHOLDER}
                    value={t}
                    onChange={(e) => patchPlot(i, e.target.value)}
                  />
                  <button
                    className="icon-btn"
                    title="删掉这一条"
                    aria-label="删掉这一条"
                    style={{ color: "var(--warn)" }}
                    onClick={() => delPlot(i)}
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" />
                    </svg>
                  </button>
                </div>
              </div>
            ))}
          </div>
          <div className="plot-sum">
            <button
              className="btn btn-secondary btn-sm"
              disabled={form.plots.length >= PLOT_MAX_ITEMS}
              onClick={addPlot}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 5v14M5 12h14" />
              </svg>
              加一条
            </button>
            <span className="f-hint">写了就自动保存</span>
          </div>
        </section>

        <div className="panel-foot">
          {gaps.length > 0 ? (
            <span className="gap-line">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <circle cx="12" cy="12" r="9" />
                <path d="M12 8v4M12 16h.01" />
              </svg>
              缺：
              {gaps.map((g) => (
                <span key={g.key} className="gap-chip" onClick={() => flashField(g.key)}>
                  {g.label}
                </span>
              ))}
            </span>
          ) : confirmed ? (
            <span className="done-note">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                <path d="M5 13l4 4L19 7" />
              </svg>
              章纲已确认
            </span>
          ) : null}
          <span style={{ flex: 1 }} />
          <button className="btn btn-ghost" onClick={onCancelEdit} disabled={saving}>
            取消
          </button>
          <button className="btn btn-secondary" onClick={onSaveDraft} disabled={saving}>
            保存草稿
          </button>
          <button
            className="btn btn-primary"
            onClick={() => {
              if (!payoffFilled) setPayoffReminded(true);
              onConfirm();
            }}
            disabled={confirmed || gaps.length > 0 || saving}
          >
            确认章纲
          </button>
          <button
            className="btn btn-primary"
            style={{ background: "var(--accent-strong)" }}
            onClick={onGoWrite}
            disabled={saving}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14">
              <path d="M5 12h14M13 6l6 6-6 6" />
            </svg>
            去写正文
          </button>
        </div>
      </div>
    </div>
  );
}

function Chev() {
  return (
    <svg
      className="chev"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      width="13"
      height="13"
    >
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}
