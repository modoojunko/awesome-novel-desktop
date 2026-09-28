// 书工作台弹窗群（book.html 遮罩弹窗的 React 化，PR 5）：
//   DeleteConfirmModal  删除确认（章=内容盘点 chips / 卷=带章数字数文案）
//   UnlockModal         解除只读（归档章 AI 链的前置确认）
//   ArchiveModal        归档本章
//   HistoryModal        版本历史（wide · ver-rows + 恢复；产品扩展=行内对比）
//   AiModal             AI 生成正文（tall · 提示词预览可编辑 + 追加语义提示）
// 文案与结构与原型 modalDelete/modalUnlock/modalArchive/modalHistory/modalAi 逐字对齐；
// 产品化差异（升级跳 S端 等）见 docs/design-c/prototypes/ADJUSTMENTS.md。
import { useEffect, useState } from "react";
import Modal from "@/components/design/Modal";
import VersionDiff from "@/components/novel/VersionDiff";
import { api, request } from "@/lib/api";
import { polishWritePrompt } from "@/lib/ai";
import { cnNum } from "@/lib/nodeTitle";
import { toast } from "@/lib/toast";

const fmt = (n: number) => n.toLocaleString("zh-CN");

// ---------------------------------------------------------------------------
// 删除确认（分级：空章无盘点；有内容章 chips 盘点；卷带章数字数）
// ---------------------------------------------------------------------------

export function DeleteConfirmModal({
  open,
  onClose,
  kind,
  title,
  chips,
  chapterCount,
  totalWords,
  onConfirm,
}: {
  open: boolean;
  onClose: () => void;
  kind: "chapter" | "volume";
  /** 名称（不含序号前缀，#164 名称即标题口径） */
  title: string;
  /** 章：内容盘点（章纲已确认 / 章纲草稿 / 自定义提示词 / 正文 N 字） */
  chips: string[];
  /** 卷：卷内章数与总字数 */
  chapterCount: number;
  totalWords: number;
  onConfirm: () => void;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="删除确认"
      wbStyle
      hideClose
      footer={
        <>
          <button className="btn btn-secondary" onClick={onClose}>
            取消
          </button>
          <button
            className="btn btn-primary"
            style={{ background: "var(--err)" }}
            data-testid="del-confirm"
            onClick={() => {
              onClose();
              onConfirm();
            }}
          >
            确认删除
          </button>
        </>
      }
    >
      {kind === "chapter" ? (
        <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.7 }}>
          确定删除章节 <b>《{title}》</b>？
        </p>
      ) : (
        <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.7 }}>
          确定删除卷 <b>《{title}》</b> 及其全部 {chapterCount} 章（{fmt(totalWords)} 字）？
        </p>
      )}
      {kind === "chapter" && chips.length > 0 && (
        <div className="del-inventory">
          <span className="inv-title">本章包含</span>
          {chips.map((c) => (
            <span key={c} className="inv-chip">
              {c}
            </span>
          ))}
        </div>
      )}
      <p style={{ margin: "8px 0 0", fontSize: 12.5, color: "var(--muted)" }}>
        此操作不可恢复。
      </p>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// 重拆整卷（c-chapter-plan-ai D14）：盘点将被移除的拟定章 → 确认后逐章删（降序）
// ---------------------------------------------------------------------------

export function ResplitConfirmModal({
  open,
  onClose,
  onConfirm,
  planned,
  kept,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  /** 将被移除的拟定章（章号 + 标题） */
  planned: Array<{ no: number; title: string }>;
  /** 保留的章（有正文/已归档） */
  kept: number;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="重拆本卷"
      wbStyle
      hideClose
      footer={
        <>
          <button className="btn btn-secondary" onClick={onClose}>
            取消
          </button>
          <button
            className="btn btn-primary"
            data-testid="resplit-confirm"
            disabled={planned.length === 0}
            onClick={() => {
              onClose();
              onConfirm();
            }}
          >
            清掉这 {planned.length} 章，重新拆
          </button>
        </>
      }
    >
      {planned.length === 0 ? (
        <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.7 }}>
          本卷没有可清掉的拟定章——有正文或已归档的章不会被移除。
        </p>
      ) : (
        <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.7 }}>
          将清掉本卷 <b>{planned.length}</b> 章拟定章（没有正文的），卷纲保留；之后可以重新拆。
        </p>
      )}
      {planned.length > 0 && (
        <div className="del-inventory" data-testid="resplit-list">
          <span className="inv-title">将被移除</span>
          {planned.map((c) => (
            <span key={c.no} className="inv-chip">
              第{c.no}章 {c.title}
            </span>
          ))}
        </div>
      )}
      {kept > 0 && (
        <p style={{ margin: "8px 0 0", fontSize: 12.5, color: "var(--muted)" }}>
          另有 {kept} 章有正文或已归档，保留不动。
        </p>
      )}
      <p style={{ margin: "8px 0 0", fontSize: 12.5, color: "var(--muted)" }}>
        此操作不可恢复。
      </p>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// 解除只读（归档章点 AI → 确认解锁并继续）
// ---------------------------------------------------------------------------

export function UnlockModal({
  open,
  onClose,
  onConfirm,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="解除只读"
      wbStyle
      hideClose
      footer={
        <>
          <button className="btn btn-secondary" onClick={onClose}>
            取消
          </button>
          <button
            className="btn btn-primary"
            data-testid="unlock-confirm"
            onClick={() => {
              onClose();
              onConfirm();
            }}
          >
            解除只读并继续
          </button>
        </>
      }
    >
      <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.7 }}>
        本章已<b>归档</b>，正文处于<b>只读</b>状态。
      </p>
      <p style={{ margin: "8px 0 0", fontSize: 12.5, color: "var(--muted)" }}>
        AI 生成将解除只读并继续编辑，请确认是否继续。
      </p>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// 归档本章
// ---------------------------------------------------------------------------

export function ArchiveModal({
  open,
  onClose,
  onConfirm,
  isPro,
  rearchive,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  /** 收尾计划预览：PRO 列伏笔/世界要素两件（c-chapter-dossier 三件已迁章档） */
  isPro?: boolean;
  /** 重归档覆盖警示（c-chapter-dossier）：{rows, accepted} 有值则警示清空重提 */
  rearchive?: { rows: number; accepted: number } | null;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="归档本章"
      wbStyle
      hideClose
      footer={
        <>
          <button className="btn btn-secondary" onClick={onClose}>
            取消
          </button>
          <button
            className="btn btn-primary"
            data-testid="arch-confirm"
            onClick={() => {
              onClose();
              onConfirm();
            }}
          >
            归档本章
          </button>
        </>
      }
    >
      <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.7 }}>
        点归档后先 <b>AI 提取本章章档</b>（设定 / 关系 / 物品 / 角色认知四域，用你配置的模型），
        提取成功本章才正式归档；提取期间本章<b>锁定</b>。
      </p>
      <p style={{ margin: "8px 0 0", fontSize: 12.5, color: "var(--muted)" }}>
        四域变化进「章档」页签逐条确认后，喂给下一章提示词；未配置模型则归档即刻生效（无章档，可后补）。仍可在版本历史中查看与恢复。
      </p>
      {rearchive && rearchive.rows > 0 && (
        <p
          style={{
            margin: "10px 0 0", padding: "8px 10px", borderRadius: 6,
            background: "color-mix(in oklch, var(--fg) 4%, transparent)", fontSize: 12.5,
          }}
          data-testid="archive-rewarn"
        >
          重新归档将<b>清空并重提</b>本章章档 {rearchive.rows} 条（含已采纳 {rearchive.accepted} 条）。
        </p>
      )}
      {/* 收尾计划预览（c-chapter-dossier 后：三件迁章档，收尾只剩两件 PRO 提案） */}
      <div className="arch-plan" data-od-id="archive-plan" data-testid="archive-plan">
        <p className="ap-h">归档收尾（PRO）</p>
        {isPro ? (
          <>
            <p className="ap-lead">
              归档成功后 AI 在后台接着跑下面 2 件事；产出是待确认的提案，点过确认才写进全书设定。
            </p>
            <ul className="ap-list">
              <li>登记伏笔（埋下 / 收束）</li>
              <li>识别世界要素</li>
            </ul>
            <p className="ap-lead">
              设定变化 / 角色关系 / 物品 / 角色认知已升级为「章档」——全档可用，随归档提取。
            </p>
          </>
        ) : (
          <p className="ap-lead">
            章档提取全档可用（配置了模型即可）；伏笔登记与世界要素提案为 PRO 能力。
          </p>
        )}
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// 版本历史（wide；行 = vtime / 版本 N · M 字 / 备注 / 当前 | 恢复）
// ---------------------------------------------------------------------------

interface VersionRow {
  version: string;
  time: number;
  comment: string;
  isCurrent: boolean;
  words?: number;
}

/** 版本时间（原型形态：今天 HH:mm / 昨天 HH:mm / N 天前 HH:mm / 更早 M月D日 HH:mm）。 */
function fmtVersionTime(ms: number): string {
  if (!ms) return "—";
  // 后端为 13 位毫秒；历史脏数据可能为秒级 → 归一
  const t = ms > 1e12 ? ms : ms * 1000;
  const d = new Date(t);
  const hm = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  const dayStart = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const days = Math.round((dayStart(new Date()) - dayStart(d)) / 86400000);
  if (days <= 0) return `今天 ${hm}`;
  if (days === 1) return `昨天 ${hm}`;
  if (days < 7) return `${days} 天前 ${hm}`;
  return `${d.getMonth() + 1}月${d.getDate()}日 ${hm}`;
}

export function HistoryModal({
  open,
  onClose,
  projectId,
  chapterRef,
  label,
  onRestored,
}: {
  open: boolean;
  onClose: () => void;
  projectId: string;
  chapterRef: string;
  /** 章标签（第一章 · 锚点） */
  label: string;
  /** 恢复成功回调（刷新章 store / 树） */
  onRestored: () => void;
}) {
  const [versions, setVersions] = useState<VersionRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [restoring, setRestoring] = useState<string | null>(null);
  // 产品扩展（ADJUSTMENTS）：行内行/词对比，默认旧=所选版本、新=当前
  const [diffOld, setDiffOld] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setDiffOld(null);
    api
      .get(`/novels/${projectId}/chapters/${chapterRef}/versions`)
      .then((data: VersionRow[]) => setVersions(Array.isArray(data) ? data : []))
      .catch(() => setVersions([]))
      .finally(() => setLoading(false));
  }, [open, projectId, chapterRef]);

  const handleRestore = async (versionId: string) => {
    setRestoring(versionId);
    try {
      await api.post(
        `/novels/${projectId}/chapters/${chapterRef}/versions/${versionId}/restore`,
      );
      toast.success("已恢复至该版本");
      onRestored();
      onClose();
    } catch {
      toast.error("恢复失败，请重试");
    } finally {
      setRestoring(null);
    }
  };

  const currentId = versions.find((v) => v.isCurrent)?.version;
  const showDiff = diffOld && currentId && diffOld !== currentId;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`版本历史 · ${label}`}
      wbStyle
      width={620}
      footer={
        <button className="btn btn-secondary" onClick={onClose}>
          关闭
        </button>
      }
    >
      {loading ? (
        <p style={{ margin: 0, padding: "20px 0", textAlign: "center", fontSize: 13, color: "var(--muted)" }}>
          加载中…
        </p>
      ) : versions.length === 0 ? (
        <p style={{ margin: 0, padding: "20px 0", textAlign: "center", fontSize: 13, color: "var(--muted)" }}>
          暂无版本记录
        </p>
      ) : showDiff ? (
        <div>
          <button className="btn btn-secondary btn-sm" onClick={() => setDiffOld(null)}>
            返回列表
          </button>
          <VersionDiff
            projectId={projectId}
            chapterRef={chapterRef}
            versions={versions}
            initialOldVersionId={diffOld ?? undefined}
            initialNewVersionId={currentId}
          />
        </div>
      ) : (
        <div id="hist-list">
          {versions.map((v, i) => (
            <div className="ver-row" key={v.version}>
              <span className="vtime">{fmtVersionTime(v.time)}</span>
              <div className="vinfo">
                <b>
                  {v.isCurrent
                    ? "当前版本"
                    : `版本 ${versions.length - i}${v.words ? ` · ${fmt(v.words)} 字` : ""}`}
                </b>
                <span>{v.comment || "自动保存"}</span>
              </div>
              {v.isCurrent ? (
                <span className="cur">当前</span>
              ) : (
                <span style={{ display: "inline-flex", gap: 6 }}>
                  <button
                    className="btn btn-secondary btn-sm"
                    disabled={restoring !== null}
                    onClick={() => setDiffOld(v.version)}
                  >
                    对比
                  </button>
                  <button
                    className="btn btn-secondary btn-sm"
                    disabled={restoring !== null}
                    onClick={() => void handleRestore(v.version)}
                  >
                    {restoring === v.version ? "恢复中…" : "恢复"}
                  </button>
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// AI 生成正文（tall；两段式 ai-prompt-crafting：打开展示存量/粗组 →
// 「AI 润色」→ 作家过目/编辑 →「生成正文」流式追加）
// c-prompt-tab-retire：提示词页签退役后本弹窗兼任「查看/编辑/存稿」入口——
// 「存为本章提示词」把编辑稿落库（PUT prompts/write），此后每次生成本弹窗
// 打开即显示这一版；只查看不生成＝打开后取消（零副作用）。
// 「刷新提示词」＝GET ?fresh=1 忽略存量行按当前素材重新组装（只换预览稿，
// 不动存量行）；章纲/设定改过之后用它拿到新组装稿。
// ---------------------------------------------------------------------------

export function AiModal({
  open,
  onClose,
  projectId,
  chapterRef,
  onConfirm,
  onPromptSaved,
}: {
  open: boolean;
  onClose: () => void;
  projectId: string;
  chapterRef: string;
  /** 携带编辑后的提示词启动生成 */
  onConfirm: (prompt: string) => void;
  /** 提示词落库成功（润色或「存为本章提示词」）→ 右栏状态行刷新 */
  onPromptSaved?: () => void;
}) {
  const [prompt, setPrompt] = useState("");
  const [hasOutline, setHasOutline] = useState(true);
  // polished：true = 存量提示词（润色或作家编辑落库）；false = 程序粗组稿
  const [polished, setPolished] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [polishing, setPolishing] = useState(false);
  const [polishError, setPolishError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setPolishError(null);
    request(`/novels/${projectId}/chapters/${chapterRef}/write/prompt`, {
      quiet: true,
    })
      .then(
        (d: {
          prompt?: string;
          has_outline?: boolean;
          polished?: boolean;
        }) => {
          if (cancelled) return;
          setPrompt(d?.prompt ?? "");
          setHasOutline(!!d?.has_outline);
          setPolished(!!d?.polished);
        },
      )
      .catch((e: Error) => {
        if (!cancelled) setError(e?.message || "提示词组装失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, projectId, chapterRef, reloadKey]);

  const handlePolish = async () => {
    if (polishing) return;
    setPolishing(true);
    setPolishError(null);
    try {
      const text = await polishWritePrompt(projectId, chapterRef);
      setPrompt(text);
      setPolished(true);
      toast.success("AI 润色完成 · 已保存，可继续编辑");
      onPromptSaved?.();
    } catch (e) {
      // 502（润色未过校验/模型出错）不动既有行 → 就地提示可重试
      setPolishError((e as Error)?.message || "润色失败，请重试");
    } finally {
      setPolishing(false);
    }
  };

  /** 「刷新提示词」：fresh=1 绕过存量行重新组装；成功清错误态（初始失败后可当
   *  恢复路径），失败不动当前稿也不动错误标志 */
  const handleRefresh = async () => {
    if (refreshing || loading) return;
    setRefreshing(true);
    try {
      const d = await request(
        `/novels/${projectId}/chapters/${chapterRef}/write/prompt?fresh=1`,
        { quiet: true },
      );
      setPrompt(d?.prompt ?? "");
      setHasOutline(!!d?.has_outline);
      setPolished(false);
      setError(null);
      setPolishError(null);
    } catch (e) {
      toast.error((e as Error)?.message || "刷新失败，请重试");
    } finally {
      setRefreshing(false);
    }
  };

  /** 「存为本章提示词」（c-prompt-tab-retire）：编辑稿落库，此后每次生成沿用 */
  const handleSavePrompt = async () => {
    if (saving || !prompt.trim()) return;
    setSaving(true);
    try {
      await api.put(`/novels/${projectId}/chapters/${chapterRef}/prompts/write`, {
        content: prompt,
      });
      setPolished(true);
      toast.success("已存为本章提示词");
      onPromptSaved?.();
    } catch (e) {
      toast.error((e as Error)?.message || "保存失败，请重试");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="AI 生成正文"
      wbStyle
      width={560}
      afterTitle={
        <span className="ai-tag">
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2l2.4 6.2L21 9l-5 4.4 1.6 6.6L12 16.6 6.4 20 8 13.4 3 9l6.6-.8z" />
          </svg>
          PRO
        </span>
      }
      footer={
        <>
          <button className="btn btn-secondary" onClick={onClose}>
            取消
          </button>
          {polished === false && (
            <button
              className="btn btn-secondary"
              data-testid="ai-polish"
              disabled={polishing || loading || refreshing}
              onClick={() => void handlePolish()}
            >
              {polishing ? "润色中…" : "AI 润色"}
            </button>
          )}
          <button
            className="btn btn-primary"
            data-testid="ai-confirm"
            disabled={loading || !!error || polishing || refreshing}
            onClick={() => {
              onClose();
              onConfirm(prompt);
            }}
          >
            生成正文
          </button>
        </>
      }
    >
      <div className="field">
        <label>
          本章提示词{" "}
          {polished === false ? (
            <span className="badge warn" data-testid="ai-raw-tag">
              未润色
            </span>
          ) : polished === true ? (
            <span className="badge ok" data-testid="ai-polished-tag">
              已润色
            </span>
          ) : null}{" "}
          <span className="opt">由「设定 + 章纲」组装，可先 AI 润色再编辑</span>
        </label>
        <textarea
          className="ai-prompt"
          value={prompt}
          disabled={loading || polishing || refreshing}
          placeholder={loading ? "组装中…" : ""}
          onChange={(e) => setPrompt(e.target.value)}
          data-testid="ai-prompt"
        />
        {/* 刷新＋存稿行：刷新＝fresh 组装稿仅换预览（不动存量行）；存稿＝编辑稿落库 */}
        <div className="ai-prompt-save">
          <span>
            「刷新提示词」按最新「设定＋章纲」重新组装（不动已存稿）；直接生成＝这一版只用于本次，存下来则本章以后每次生成都用它。
          </span>
          <div style={{ display: "flex", gap: 8, flex: "none" }}>
            <button
              className="btn btn-ghost btn-sm"
              data-testid="ai-prompt-refresh"
              title="按最新「设定＋章纲」重新组装；不改动已存稿，可再润色或编辑"
              disabled={loading || polishing || refreshing}
              onClick={() => void handleRefresh()}
            >
              {refreshing ? "刷新中…" : "刷新提示词"}
            </button>
            <button
              className="btn btn-ghost btn-sm"
              data-testid="ai-prompt-save"
              disabled={loading ||
                polishing ||
                refreshing ||
                saving ||
                !!error ||
                !prompt.trim()}
              onClick={() => void handleSavePrompt()}
            >
              {saving ? "保存中…" : "存为本章提示词"}
            </button>
          </div>
        </div>
      </div>
      {polishError ? (
        <p style={{ margin: 0, fontSize: 12.5, color: "var(--err)" }}>
          {polishError} ·{" "}
          <button
            className="btn btn-ghost btn-sm"
            disabled={polishing}
            onClick={() => void handlePolish()}
          >
            重试润色
          </button>
        </p>
      ) : error ? (
        <p style={{ margin: 0, fontSize: 12.5, color: "var(--err)" }}>
          {error}·
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => setReloadKey((k) => k + 1)}
          >
            重试
          </button>
        </p>
      ) : (
        <p style={{ margin: 0, fontSize: 12.5, color: "var(--muted)" }}>
          {hasOutline
            ? "两段式：先「AI 润色」成稿 → 过目编辑 → 生成。生成内容将追加到本章末尾。"
            : "本章尚未配置章纲，将仅依据设定生成。建议先去「大纲」补章纲（不强制）。"}
        </p>
      )}
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// 重写这一章（chapter-rewrite）：影响面确认（原型 m-ch-confirm 口径）
// ---------------------------------------------------------------------------

export function RewriteModal({
  open,
  onClose,
  chapterLabel,
  busy,
  onConfirm,
}: {
  open: boolean;
  onClose: () => void;
  chapterLabel: string;
  busy?: boolean;
  onConfirm: () => void;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="重写这一章"
      wbStyle
      locked={busy}
      footer={
        <>
          <button className="btn btn-secondary" onClick={onClose} disabled={busy}>
            取消
          </button>
          <button
            className="btn btn-primary"
            data-testid="rewrite-confirm"
            disabled={busy}
            onClick={onConfirm}
          >
            {busy ? "处理中…" : "打开写作窗口重写"}
          </button>
        </>
      }
    >
      <p className="rw-lead">{chapterLabel} · 重写只影响本章与之后的章节：</p>
      <ul className="rw-list">
        <li>
          <b>旧稿</b>
          <span>本章当前正文将转入旧稿支线，可随时点开查看。</span>
        </li>
        <li>
          <b>后续</b>
          <span>其后章节原样保留，但挂「基于旧设定」角标，提示上游设定已变。</span>
        </li>
        <li>
          <b>设定</b>
          <span>归档时确认本章变化；开书设定永不改写，之后累积的条目跟着重算。</span>
        </li>
      </ul>
    </Modal>
  );
}
