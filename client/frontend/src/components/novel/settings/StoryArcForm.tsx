// 主线面板（storyline-settings-v2）：只管主线——
// ① 这本书从头到尾说什么（fullstory 全景，建议 600 字内不硬截）
// ② 结局是什么三问（最后一幕画面 / 主角变成什么样的人 / 读者合上书的感受，
//    第三问旁行内「AI 帮我填」）
// 分卷规划已移交写作阶段；AI 四能力（draft/calibrate/check/tone）经 runAi 句柄
// 由 SettingsView 右栏分发，行内 tone 与 rail 三行共用在途互斥。
// c-settings-ai-confirm-modal：结果统一进弹窗出卡（内嵌结果区退役）；重开同一行
// 直接展示缓存不再发请求，「换一个」才重新生成（D9）；缓存＝面板 state 寿命。
import {
  forwardRef,
  useCallback,
  useImperativeHandle,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { type SettingSaveHandle } from "@/components/novel/settings/FormField";
import { api } from "@/lib/api";
import { toast } from "@/lib/toast";
import { aiBlockReason } from "@/lib/ai";
import AiCardModal, { type AiCardState } from "@/components/novel/settings/AiCardModal";
import {
  useChangeReceipt,
  type ChangeReceiptState,
} from "@/components/novel/settings/ChangeReceipt";
import { useStoryArc, type ArcCtl, type ArcData } from "./useStoryArc";

export type { ArcData } from "./useStoryArc";

export type ArcAiAction = "draft" | "calibrate" | "check" | "tone";

export interface ArcFormHandle extends SettingSaveHandle {
  /** 运行 AI 能力（右栏三行 / 行内 tone 共用）；有缓存时只开弹窗不再发请求。 */
  runAi: (action: ArcAiAction) => Promise<void>;
  /** 是否有 AI 结果在展示（供右栏行描述态） */
  hasAiSink: () => boolean;
}

interface Props {
  projectId: string;
  onDirtyChange?: (dirty: boolean) => void;
  onReceiptChange?: (r: ChangeReceiptState | null) => void;
  /** 外部共享状态（SettingsView 持有）；缺省时自持（单测/独立使用） */
  ctl?: ArcCtl;
}

const StoryArcForm = forwardRef<ArcFormHandle, Props>(function StoryArcForm(
  { projectId, onDirtyChange, onReceiptChange, ctl: external },
  ref,
) {
  const own = useStoryArc(projectId, !external, onDirtyChange);
  const c = external ?? own;
  const { arc, saving } = c;

  const { record: recordChange } = useChangeReceipt(onReceiptChange);
  // 弹窗出卡：按能力分 key 缓存最近一版（重开免请求，D9）；同一时刻只开一张卡
  const [cards, setCards] = useState<Partial<Record<ArcAiAction, AiCardState>>>({});
  const [versions, setVersions] = useState<Partial<Record<ArcAiAction, number>>>({});
  const [cardAction, setCardAction] = useState<ArcAiAction | null>(null);
  const [cardOpen, setCardOpen] = useState(false);
  const [cardError, setCardError] = useState("");
  const [aiRunning, setAiRunning] = useState<ArcAiAction | null>(null);
  const aiBusyRef = useRef(false);
  /** 采纳时刻的真实改前值（卡创建晚于 patch，闭包里的 arc 会过期） */
  const arcRef = useRef(arc);
  arcRef.current = arc;

  useImperativeHandle(
    ref,
    () => ({
      save: () => c.save(),
      markDirty: undefined,
      clearAi: () => {
        setCards({});
        setVersions({});
        setCardAction(null);
        setCardOpen(false);
        setCardError("");
      },
      runAi: (action) => runAi(action),
      hasAiSink: () => Object.keys(cards).length > 0,
    }),
    [c, cards],
  );

  const patch = (p: Partial<ArcData>) => c.patch(p);

  /** 采纳快照 + 回执一步撤销（沿 IntroPanel 模式）；确认后关弹窗 */
  const adoptWithReceipt = useCallback(
    (text: string, apply: () => void, revert: () => void) => {
      recordChange(
        text,
        () => { /* 值在 apply 里落地 */ },
        revert,
      );
      apply();
      setCardOpen(false);
      toast.success("已采纳，可继续改");
    },
    [recordChange],
  );

  /** 缓存命中：只开弹窗展示既有结果，不发请求（D9） */
  const openCached = useCallback((action: ArcAiAction) => {
    setCards((prev) => (prev[action] ? { ...prev, [action]: { ...prev[action]!, cached: true } } : prev));
    setCardError("");
    setCardAction(action);
    setCardOpen(true);
  }, []);

  const runRequest = useCallback(
    async (action: ArcAiAction) => {
      aiBusyRef.current = true;
      setAiRunning(action);
      setCardError("");
      setCardAction(action);
      setCardOpen(true);
      try {
        const r = await api.runArcAi(projectId, action, {});
        const v = r.value ?? {};
        let entry: AiCardState;
        if (action === "draft") {
          entry = {
            label: "AI 填 · 起草主线",
            kind: "struct",
            adoptText: "采纳 · 覆盖全景与结局",
            node: (
              <div>
                <p style={{ margin: "4px 0" }}><b>从头到尾说什么</b>：{String(v.fullstory ?? "")}</p>
                <p style={{ margin: "4px 0" }}><b>最后一幕</b>：{String(v.ending?.scene ?? "")}</p>
                <p style={{ margin: "4px 0" }}><b>主角最终</b>：{String(v.ending?.hero ?? "")}</p>
                <p style={{ margin: "4px 0" }}><b>读后感觉</b>：{String(v.ending?.tone ?? "")}</p>
              </div>
            ),
            adopt: v.fullstory ? () => {
              // 基准取「采纳时刻」（弹窗期间表单不可编辑，但采纳后的手改必须保得住）：
              // revert 只回滚本采纳写过的字段（全景＋结局三问），不动作者其余手写
              const before = arcRef.current;
              adoptWithReceipt(
                "已采纳「AI 起草主线」，全景和结局都写进来了，可改",
                () => c.patch({
                  fullstory: String(v.fullstory ?? ""),
                  ending: {
                    scene: String(v.ending?.scene ?? ""),
                    hero: String(v.ending?.hero ?? ""),
                    tone: String(v.ending?.tone ?? ""),
                  },
                }),
                () => c.patch({ fullstory: before.fullstory, ending: before.ending }),
              );
            } : undefined,
            cached: false,
          };
        } else if (action === "calibrate") {
          entry = {
            label: "AI 填 · 结局校准",
            kind: "struct",
            adoptText: "采纳 · 覆盖结局三问",
            node: (
              <div>
                <p style={{ margin: "4px 0" }}><b>最后一幕</b>：{String(v.scene ?? "")}</p>
                <p style={{ margin: "4px 0" }}><b>主角最终</b>：{String(v.hero ?? "")}</p>
                <p style={{ margin: "4px 0" }}><b>读后感觉</b>：{String(v.tone ?? "")}</p>
                {v.note ? <p style={{ margin: "4px 0", color: "var(--muted)", fontSize: 12 }}>{String(v.note)}</p> : null}
              </div>
            ),
            adopt: (v.scene || v.hero || v.tone) ? () => {
              const before = arcRef.current.ending; // 采纳时刻基准（字段级回滚）
              adoptWithReceipt(
                "已采纳「结局校准」，三问都答好了，可改",
                () => c.patch({
                  ending: {
                    scene: String(v.scene ?? ""),
                    hero: String(v.hero ?? ""),
                    tone: String(v.tone ?? ""),
                  },
                }),
                () => c.patch({ ending: before }),
              );
            } : undefined,
            cached: false,
          };
        } else if (action === "check") {
          const checks: Array<{ name: string; status: string; note: string }> = Array.isArray(v.checks) ? v.checks : [];
          entry = {
            label: "AI 体检 · 主线自检",
            kind: "report",
            node: (
              <div className="chk-grid" data-od-id="arc-check-lines">
                {checks.map((ck) => (
                  <div className="chk-line" key={ck.name}>
                    <span className="chk-name">{ck.name}</span>
                    <span className={`chk-res ${ck.status === "ok" ? "ok" : ck.status === "warn" ? "warn" : "miss"}`}>
                      {ck.status === "ok" ? "达标" : ck.status === "warn" ? "风险" : "缺失"}
                    </span>
                    <span className="chk-note">{ck.note}</span>
                  </div>
                ))}
                {v.summary ? (
                  <p style={{ margin: "8px 0 0", fontSize: 11.5, color: "var(--muted)" }}>{String(v.summary)}</p>
                ) : null}
              </div>
            ),
            cached: false,
          };
        } else {
          // tone：行内基调建议
          entry = {
            label: "AI 填 · 结局基调",
            kind: "text",
            node: <p style={{ margin: "4px 0" }}>{String(v.tone ?? "")}</p>,
            adopt: v.tone ? () => {
              const beforeTone = arcRef.current.ending.tone; // 采纳时刻基准
              adoptWithReceipt(
                "已采纳「AI 填 · 结局基调」，可改",
                () => c.patch({ ending: { ...arcRef.current.ending, tone: String(v.tone) } }),
                () => c.patch({ ending: { ...arcRef.current.ending, tone: beforeTone } }),
              );
            } : undefined,
            cached: false,
          };
        }
        setCards((prev) => ({ ...prev, [action]: entry }));
        setVersions((prev) => ({ ...prev, [action]: (prev[action] ?? 0) + 1 }));
      } catch (e: unknown) {
        const reason = aiBlockReason(e);
        const msg =
          reason === "member_required"
            ? (e as Error).message || "这是会员功能——开通后可用；免费版写作能力完整"
            : reason === "no_key"
              ? (e as Error).message || "先去「模型配置」添加 API Key"
              : reason === "missing_model" || reason === "invalid"
                ? "先在本书选择模型"
                : (e as Error).message || "暂不可用，请重试";
        if (cards[action]) setCardError(msg);
        else {
          // 无既有结果：挡掉原因（未配模型/会员）仍走 toast 分流，生成失败进弹窗错误体
          if (reason === "member_required" || reason === "no_key" || reason === "missing_model" || reason === "invalid") {
            setCardOpen(false);
            toast.info(msg);
          } else {
            setCardError(msg);
          }
        }
      } finally {
        aiBusyRef.current = false;
        setAiRunning(null);
      }
    },
    [projectId, c, adoptWithReceipt, cards],
  );

  const runAi = useCallback(
    async (action: ArcAiAction) => {
      if (aiBusyRef.current) return; // 在途互斥：行内 tone 与 rail 三行共用
      if (cards[action]) {
        openCached(action); // 重开＝展示缓存，不重复生成（D9）
        return;
      }
      await runRequest(action);
    },
    [cards, openCached, runRequest],
  );

  if (c.loading) {
    return <p className="opt">加载主线卡…</p>;
  }

  // 加载失败＝没有可保存的基线：面板替换为失败态（重试成功后恢复表单），
  // 防止「表单显示为空 → 作者补两句 → 保存整卡覆盖库里已有内容」（c-silent-data-guards）
  if (c.loadError) {
    return (
      <div className="opt" data-testid="arc-load-error" style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <span>主线卡没加载出来——为避免覆盖已有内容，暂时不能编辑保存。</span>
        <button className="btn btn-ghost btn-sm" data-testid="arc-reload" onClick={c.reload}>
          重新加载
        </button>
      </div>
    );
  }

  return (
    <div className="story-arc-form">
      {/* ① 这本书从头到尾说什么 */}
      <div className="field">
        <label>
          这本书从头到尾说什么{" "}
          <span className="opt">比简介更全 · 可以剧透 · 建议 600 字以内——写章、定卷纲都照着这段来</span>
        </label>
        <textarea
          className="textarea"
          style={{ minHeight: 150 }}
          rows={6}
          placeholder={"顺着写：主角从哪起步 → 谁在拦他 → 最后换来什么。\n\n例：杂役弟子林拾在柳安坊市当值，捡到父亲留下的残页……"}
          value={arc.fullstory}
          disabled={saving}
          data-od-id="arc-fullstory"
          onChange={(e) => patch({ fullstory: e.target.value })}
        />
      </div>

      {/* ② 结局是什么：三个问题让作家回答，答完即锚 */}
      <div className="field">
        <label>
          结局是什么 <span className="opt">三个问题，想到哪答哪、可全空——答上来，往后写就不容易跑偏</span>
        </label>
        <div style={{ display: "grid", gap: 12 }}>
          <div>
            <label style={{ fontWeight: 600, color: "var(--fg)" }}>
              ① 故事的最后一幕，镜头里是什么画面？
            </label>
            <input
              className="input"
              style={{ marginTop: 5 }}
              placeholder="例：丹阁首座在戒律堂认罪，林拾把父亲的旧物摆回书架，坊市人声如常。"
              value={arc.ending.scene}
              disabled={saving}
              data-od-id="arc-ending-scene"
              onChange={(e) => patch({ ending: { ...arc.ending, scene: e.target.value } })}
            />
          </div>
          <div>
            <label style={{ fontWeight: 600, color: "var(--fg)" }}>
              ② 走到终点时，主角变成了什么样的人？
            </label>
            <input
              className="input"
              style={{ marginTop: 5 }}
              placeholder="例：从怕事的杂役成为青梧宗执卷人——不再依赖听漏，也听得见人心。"
              value={arc.ending.hero}
              disabled={saving}
              data-od-id="arc-ending-hero"
              onChange={(e) => patch({ ending: { ...arc.ending, hero: e.target.value } })}
            />
          </div>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <label style={{ fontWeight: 600, color: "var(--fg)" }}>
                ③ 合上书那一刻，你想让读者心里留下什么感觉？
              </label>
              <button
                type="button"
                className="text-btn"
                style={{ marginLeft: "auto", fontSize: 12 }}
                disabled={saving || aiRunning !== null}
                data-od-id="arc-tone-ai-fill"
                onClick={() => void runAi("tone")}
                title="让 AI 按你的题材给个建议，采不采纳你说了算"
              >
                {aiRunning === "tone" ? "AI 想着…" : "AI 帮我填"}
              </button>
            </div>
            <input
              className="input"
              style={{ marginTop: 5 }}
              placeholder="例：先悲后喜 / 苦尽甘来 / 意难平——用自己的话"
              value={arc.ending.tone}
              disabled={saving}
              data-od-id="arc-ending-tone"
              onChange={(e) => patch({ ending: { ...arc.ending, tone: e.target.value } })}
            />
          </div>
        </div>
      </div>

      {/* 「怎么写」搭建法（guide 家族） */}
      <ArcGuide />

      <p className="opt" style={{ fontSize: 12, margin: "-4px 0 16px" }}>
        主线是总方向盘，不拦写作：没填也不影响直接去建卷写章。
      </p>

      {/* AI 出卡确认弹窗：右栏三行＋行内 tone 共用（关闭即弃；缓存重开免请求） */}
      <AiCardModal
        open={cardOpen && cardAction !== null}
        card={cardAction ? cards[cardAction] ?? null : null}
        running={cardAction !== null && aiRunning === cardAction}
        error={cardAction !== null && aiRunning !== cardAction ? cardError : undefined}
        version={cardAction ? versions[cardAction] : undefined}
        onClose={() => setCardOpen(false)}
        onRegenerate={cardAction ? () => void runRequest(cardAction) : undefined}
        data-testid="arc-ai-card"
      />
    </div>
  );
});

/** 「怎么写」搭建法——编辑口吻，四条 + 公式 + 别踩（storyline-settings-v2 定稿文案） */
function ArcGuide() {
  const [open, setOpen] = useState(false);
  return (
    <div className="guide" data-od-id="arc-guide">
      <button className="guide-toggle" type="button" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <span className="gt-b">「怎么写」搭建法</span>
        <span className="gt-s">和简介有什么不同 → 顺着讲就行 → 心里装个问题 → 结局先想好 · 点开看每条怎么写</span>
        <span className="gt-c">{open ? "收起" : "展开"}</span>
      </button>
      {open && (
        <div className="guide-body">
          <div className="g-row"><span className="g-name">和简介不一样</span><span className="g-body">简介是写给读者的：藏悬念、留钩子、不剧透。这一栏写给你自己（和 AI）看：<b>把谜底摊开说</b>——故事怎么开始、怎么斗、怎么收场，都说透。<em>简介以后改十遍没关系，这一段定了就别轻易动——往后每一章都照着它来。</em></span></div>
          <div className="g-row"><span className="g-name">顺着讲就行</span><span className="g-body">像给朋友剧透一个故事那样写：主角<em>一开始什么处境、碰上什么事</em>，对手<em>怎么一步步紧逼</em>、他付了什么代价，<em>最后怎么收场</em>。不用管分几卷、每卷几章——那是动笔以后的事。</span></div>
          <div className="g-row"><span className="g-name">心里装个问题</span><span className="g-body">好故事都是读者读到最后才解开的那一个问题。<em>例：父亲到底出了什么事？那半卷残页里藏着谁的秘密？</em>写这一栏时心里带着它，每一段都会往它身上使劲。</span></div>
          <div className="g-row"><span className="g-name">结局先想好</span><span className="g-body">最后一幕是什么画面？主角最后成了什么样的人？读者合上书是什么滋味？<em>这三问答上来，往后写每一章都知道自己在往哪儿走。</em>没想好就先空着，想到哪答哪。</span></div>
          <span className="g-formula">搭骨架公式：<b>他从哪起步 + 谁在拦他 + 最后换来什么</b></span>
          <p className="g-dont">别踩：把简介原样抄一遍（这里要的是更全的底细，含糊的地方都说透）；写成一份卷纲（分几卷、每卷几章，动笔再安排）；把配角小传一股脑塞进来（角色的账去角色页记）；结局全空着（越往后写越容易散）。</p>
        </div>
      )}
    </div>
  );
}

export default StoryArcForm;
