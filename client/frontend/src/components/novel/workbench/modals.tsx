// 书工作台弹窗群（book.html 遮罩弹窗的 React 化，PR 5）：
//   DeleteConfirmModal  删除确认（章=内容盘点 chips / 卷=带章数字数文案）
//   ArchiveModal        归档本章
//   HistoryModal        版本历史（wide · ver-rows + 恢复；产品扩展=行内对比）
//   RegenConfirmModal   重新生成确认（c-prose-regen-replace：有正文章再生成＝清空重写）
//   AiModal             AI 生成正文（tall · 提示词预览可编辑；生成＝替换本章正文）
// 文案与结构与原型 modalDelete/modalArchive/modalHistory/modalAi 逐字对齐
// （modalUnlock 随「解除只读」解锁链退役，c-archived-readonly）；
// 产品化差异（升级跳 S端 等）见 docs/design-c/prototypes/ADJUSTMENTS.md。
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Modal from "@/components/design/Modal";
import VersionDiff from "@/components/novel/VersionDiff";
import { Ico, P } from "@/components/icons";
import { api, request } from "@/lib/api";
import { cnNum } from "@/lib/nodeTitle";
import { toast } from "@/lib/toast";
import { useModelStatus } from "@/hooks/useModelStatus";
import { placePanel, type PanelPlacement } from "@/lib/panelAnchor";
import type { FlatModelOption, ModelSelection } from "@/types/api-config";

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
// 归档本章
// ---------------------------------------------------------------------------

export function ArchiveModal({
  open,
  onClose,
  onConfirm,
  isPro,
  rearchiveMode,
  rearchive,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  /** 收尾计划预览：PRO 列伏笔/世界要素两件（c-chapter-dossier 三件迁本章变化） */
  isPro?: boolean;
  /** 重归档变体（c-ops-tab-progress-only）：已归档章重提变化——收尾计划区不出现 */
  rearchiveMode?: boolean;
  /** 重归档覆盖警示（c-chapter-dossier）：{rows, accepted} 有值则警示清空重提 */
  rearchive?: { rows: number; accepted: number } | null;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={rearchiveMode ? "重新归档" : "归档本章"}
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
            {rearchiveMode ? "重新归档" : "归档本章"}
          </button>
        </>
      }
    >
      <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.7 }}>
        {rearchiveMode ? (
          <>
            重新归档将以当前正文重提本章变化（设定 / 关系 / 物品 / 角色认知）；
            <b>你已确认的条目保留不动</b>，新结果以待确认提案出现。提取期间本章<b>锁定</b>。
          </>
        ) : (
          <>
            点归档后先 <b>AI 提取本章变化</b>（设定 / 关系 / 物品 / 角色认知，用你配置的模型），
            提取成功本章才正式归档；提取期间本章<b>锁定</b>。
          </>
        )}
      </p>
      {rearchiveMode ? (
        <p style={{ margin: "8px 0 0", fontSize: 12.5, color: "var(--muted)" }}>
          重提只替换本章未确认的变化行；伏笔登记 / 世界要素提案不重跑（可在右栏「登记新伏笔」单独触发）。
        </p>
      ) : (
        <p style={{ margin: "8px 0 0", fontSize: 12.5, color: "var(--muted)" }}>
          变化在「设定」「角色关系」页签逐条确认后，喂给下一章提示词；未配置模型则归档即刻生效（无变化记录，可后补）。仍可在版本历史中查看与恢复。
        </p>
      )}
      {rearchive && rearchive.rows > 0 && (
        <p
          style={{
            margin: "10px 0 0", padding: "8px 10px", borderRadius: 6,
            background: "color-mix(in oklch, var(--fg) 4%, transparent)", fontSize: 12.5,
          }}
          data-testid="archive-rewarn"
        >
          已确认 {rearchive.accepted} 条将保留；其余 {rearchive.rows - rearchive.accepted} 条由重提替换。
        </p>
      )}
      {/* 收尾计划预览（c-chapter-dossier 后：三件迁本章变化，收尾只剩两件 PRO 提案）；
          重归档不重跑收尾（c-ops-tab-progress-only），该区不出现 */}
      {!rearchiveMode && (
        <div className="arch-plan" data-od-id="archive-plan" data-testid="archive-plan">
          <p className="ap-h">归档收尾提案</p>
          <p className="ap-lead">
            归档成功后 AI 在后台接着跑下面 2 件事；产出是待确认的提案，点过确认才写进全书设定。
          </p>
          <ul className="ap-list">
            <li>登记伏笔（埋下 / 收束）——产出在「伏笔」页签确认</li>
            <li>识别世界要素——产出在「设定」页签确认</li>
          </ul>
          <p className="ap-lead">
            设定变化 / 角色关系 / 物品 / 角色认知随归档自动提取，全档可用。
          </p>
        </div>
      )}
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
// 生成模型选择位（c-prose-model-select）：跨配置/供应商按次选模型，仅本次生成生效。
// 控件＝.mp-* 组合框＋弹层（先例 ApiConfigForm：portal 到 body + fixed 定位——弹窗
// 滚动区不裁剪浮层；Esc 只收弹层）；选项只在「≠ 本书模型」时随请求下发。
// ---------------------------------------------------------------------------

function ModelPicker({
  options,
  value,
  bookValue,
  onPick,
}: {
  options: FlatModelOption[];
  /** 当前选择键 `${api_config_id}::${model}` */
  value: string;
  /** 本书模型键（弹层内标「本书模型」；标记恒随绑定，不随选择移动） */
  bookValue: string;
  onPick: (key: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [cursor, setCursor] = useState(0);
  const [pos, setPos] = useState<PanelPlacement | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);

  // 分组：以配置为组（组头＝配置名 + 供应商）——跨供应商可辨（沿 ModelSettingForm 分组语义）
  const groups = useMemo(() => {
    const byConfig = new Map<string, FlatModelOption[]>();
    for (const o of options) {
      const list = byConfig.get(o.api_config_id) ?? [];
      list.push(o);
      byConfig.set(o.api_config_id, list);
    }
    return [...byConfig.entries()].map(([cid, opts]) => ({
      cid,
      name: opts[0].config_name,
      vendor: opts[0].vendor,
      opts,
    }));
  }, [options]);
  const flat = useMemo(
    () =>
      groups.flatMap((g) =>
        g.opts.map((o) => ({ ...o, key: `${o.api_config_id}::${o.model}` })),
      ),
    [groups],
  );
  const current = flat.find((o) => o.key === value) ?? flat[0];

  // 弹层定位：portal 出 .mcard 滚动容器后用 fixed 锚触发位矩形，随滚动/resize 重锚；
  // 换算（zoom 折算＋放不下翻转/限高）统一走 placePanel——见 lib/panelAnchor.ts
  useEffect(() => {
    if (!open) return;
    const anchor = () => {
      const el = wrapRef.current?.querySelector("button");
      if (!el) return;
      const r = el.getBoundingClientRect();
      setPos(
        placePanel(
          { top: r.top, bottom: r.bottom, left: r.left, width: r.width },
          window.innerHeight,
        ),
      );
    };
    anchor();
    window.addEventListener("scroll", anchor, true);
    window.addEventListener("resize", anchor);
    return () => {
      window.removeEventListener("scroll", anchor, true);
      window.removeEventListener("resize", anchor);
    };
  }, [open]);

  // 外点关闭：pointerdown 落在触发位与弹层之外即收起（同先例）
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      const t = e.target as Node;
      if (wrapRef.current?.contains(t)) return;
      if (panelRef.current?.contains(t)) return;
      setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  const openAt = () => {
    const i = flat.findIndex((o) => o.key === value);
    setCursor(i >= 0 ? i : 0);
    setOpen(true);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!open) {
        openAt();
      } else {
        setCursor((c) =>
          Math.min(Math.max(c + (e.key === "ArrowDown" ? 1 : -1), 0), flat.length - 1),
        );
      }
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (!open) {
        openAt();
      } else {
        const pick = flat[cursor];
        if (pick) {
          onPick(pick.key);
          setOpen(false);
        }
      }
    } else if (e.key === "Escape" && open) {
      // 只收弹层：吞掉冒泡（Modal 在 window 上听 Esc——先例 ApiConfigForm 评审 P1）
      e.stopPropagation();
      setOpen(false);
    }
  };

  return (
    <div className="mp-wrap" ref={wrapRef} data-testid="ai-model-picker">
      <button
        type="button"
        className="input mp-trigger"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls="ai-model-panel"
        aria-activedescendant={open && flat[cursor] ? `ai-model-opt-${cursor}` : undefined}
        aria-label="生成模型"
        data-testid="ai-model-select"
        onClick={() => (open ? setOpen(false) : openAt())}
        onKeyDown={onKeyDown}
      >
        <span className="mt-name" data-testid="ai-model-name">
          {current ? `${current.config_name} · ${current.model}` : ""}
        </span>
        <Ico d={P.chevronDown} />
      </button>
      {open &&
        pos &&
        createPortal(
          <div
            className="mp-panel"
            id="ai-model-panel"
            role="listbox"
            aria-label="生成模型"
            data-testid="ai-model-panel"
            ref={panelRef}
            style={{
              position: "fixed",
              top: pos.top,
              bottom: pos.bottom,
              left: pos.left,
              width: pos.width,
              maxHeight: pos.maxHeight,
              zIndex: 70,
            }}
            onMouseDown={(e) => e.preventDefault()} // 点选不抢焦点：键盘现场留在触发位（同先例）
          >
            {groups.map((g) => (
              <div key={g.cid}>
                <div className="mp-group">
                  {g.name} <span className="mg-vendor">{g.vendor}</span>
                </div>
                <ul className="mp-list">
                  {g.opts.map((o) => {
                    const key = `${o.api_config_id}::${o.model}`;
                    const i = flat.findIndex((f) => f.key === key);
                    const on = key === value;
                    return (
                      <li key={key}>
                        <button
                          type="button"
                          role="option"
                          id={`ai-model-opt-${i}`}
                          aria-selected={on}
                          tabIndex={-1}
                          className={
                            "mp-item" + (i === cursor ? " cur" : "") + (on ? " on" : "")
                          }
                          data-model={key}
                          onMouseEnter={() => setCursor(i)}
                          onClick={() => {
                            onPick(key);
                            setOpen(false);
                          }}
                        >
                          {o.model}
                          {key === bookValue ? (
                            <span className="mp-flag">本书模型</span>
                          ) : null}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>,
          document.body,
        )}
    </div>
  );
}

/** 「生成模型」字段（挂载即取数——只在弹窗打开时挂载，不占章工作台常驻请求预算）：
 *  `ai_state !== ready` 或可选项 < 2 时整行不渲染（单模型用户零变化）。 */
function ModelField({
  projectId,
  modelSel,
  onChange,
}: {
  projectId: string;
  modelSel: ModelSelection | null;
  onChange: (sel: ModelSelection | null) => void;
}) {
  const { modelOptions, currentConfigId, currentModel, aiState } = useModelStatus(projectId);
  const bookKey =
    currentConfigId && currentModel ? `${currentConfigId}::${currentModel}` : "";
  const key = modelSel ? `${modelSel.api_config_id}::${modelSel.model}` : bookKey;
  if (aiState !== "ready" || modelOptions.length < 2) return null;
  return (
    <div className="field">
      <label>
        生成模型{" "}
        <span className="opt">仅本次生成生效，不改本书模型</span>
      </label>
      <ModelPicker
        options={modelOptions}
        value={key}
        bookValue={bookKey}
        onPick={(k) => {
          const o = modelOptions.find((m) => `${m.api_config_id}::${m.model}` === k);
          if (!o) return;
          onChange(k === bookKey ? null : { api_config_id: o.api_config_id, model: o.model });
        }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// 重新生成确认（c-prose-regen-replace）：已有正文章再点「生成正文」→ 先确认
// 「重复生成将清空当前正文」，找回只有版本历史；确认后才进 AiModal 提示词预览。
// ---------------------------------------------------------------------------
export function RegenConfirmModal({
  open,
  onClose,
  onConfirm,
  words,
}: {
  open: boolean;
  onClose: () => void;
  /** 确认后进 AiModal 提示词预览（本弹窗自身零副作用，不触发生成） */
  onConfirm: () => void;
  /** 当前正文字数（提示语带数量；0＝不显字数） */
  words: number;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="重新生成正文"
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
            data-testid="regen-confirm"
            onClick={() => {
              onClose();
              onConfirm();
            }}
          >
            继续生成
          </button>
        </>
      }
    >
      <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.7 }}>
        本章已有正文{words > 0 ? <>（{fmt(words)} 字）</> : null}，重新生成将
        <b>清空当前正文</b>后写入新内容。
      </p>
      <p style={{ margin: "8px 0 0", fontSize: 12.5, color: "var(--muted)" }}>
        被清空的正文无法在编辑器撤销找回，只能通过页签行右端「版本历史」恢复。
      </p>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// AI 生成正文（tall）：打开展示存量/本次组装稿 → 作家过目/编辑 →「生成正文」
// 流式写入。c-prompt-tab-retire：提示词页签退役后本弹窗兼任「查看/编辑/存稿」
// 入口——「存为本章提示词」把编辑稿落库（PUT prompts/write），此后每次生成本弹窗
// 打开即显示这一版；只查看不生成＝打开后取消（零副作用）。
// 「刷新提示词」＝GET ?fresh=1 忽略存量行按当前素材重新组装（只换预览稿，
// 不动存量行）；章纲/设定改过之后用它拿到新组装稿。
// c-retire-prompt-polish：原「AI 润色」两段式第二段退役（组装稿直接可编辑用），
// 弹窗内不再有润色入口。
// c-prose-regen-replace：写入语义由「追加到本章末尾」改「清空并替换本章正文」；
// 已有正文章的再生成在入口层先过 RegenConfirmModal（「去刷新提示词」软提示
// 出口除外——只看/刷新意图不拦，生成后果由弹窗内提示行告知）。
// ---------------------------------------------------------------------------

export function AiModal({
  open,
  onClose,
  projectId,
  chapterRef,
  hasProse,
  onConfirm,
  onPromptSaved,
}: {
  open: boolean;
  onClose: () => void;
  projectId: string;
  chapterRef: string;
  /** 本章已有正文（c-prose-regen-replace）：提示行按「替换」口径出文案 */
  hasProse?: boolean;
  /** 携带编辑后的提示词启动生成；modelSelection＝按次模型对（c-prose-model-select：
   *  未换模型/与本书模型相同＝undefined，走本书模型路径） */
  onConfirm: (prompt: string, modelSelection?: ModelSelection) => void;
  /** 提示词落库成功（「存为本章提示词」）→ 右栏状态行刷新 */
  onPromptSaved?: () => void;
}) {
  const [prompt, setPrompt] = useState("");
  const [hasOutline, setHasOutline] = useState(true);
  // polished：true = 存量提示词（作家编辑落库）；false = 程序本次组装稿
  const [polished, setPolished] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  // 旧版整包分型（c-write-prompt-layering）：raw=粗组存稿旧行（建议刷新）、
  // polished=润色旧行（只信息性，不引导覆盖）；"" = 新分层口径
  const [legacyKind, setLegacyKind] = useState("");
  const [lintWarnings, setLintWarnings] = useState<string[]>([]);
  // 按次模型对（c-prose-model-select）：每次打开回到本书模型（按次语义，不记忆）
  const [modelSel, setModelSel] = useState<ModelSelection | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setModelSel(null);
    request(`/novels/${projectId}/chapters/${chapterRef}/write/prompt`, {
      quiet: true,
    })
      .then(
        (d: {
          prompt?: string;
          has_outline?: boolean;
          polished?: boolean;
          legacy_kind?: string;
          warnings?: string[];
        }) => {
          if (cancelled) return;
          setPrompt(d?.prompt ?? "");
          setHasOutline(!!d?.has_outline);
          setPolished(!!d?.polished);
          setLegacyKind(d?.legacy_kind ?? "");
          setLintWarnings(
            Array.isArray(d?.warnings) ? d.warnings.filter(Boolean) : [],
          );
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
      setLegacyKind("");
      setLintWarnings(Array.isArray(d?.warnings) ? d.warnings.filter(Boolean) : []);
      setError(null);
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
          <button
            className="btn btn-primary"
            data-testid="ai-confirm"
            disabled={loading || !!error || refreshing}
            onClick={() => {
              onClose();
              onConfirm(prompt, modelSel ?? undefined);
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
              本次组装
            </span>
          ) : polished === true ? (
            <span className="badge ok" data-testid="ai-polished-tag">
              本章已存稿
            </span>
          ) : null}{" "}
          <span className="opt">由「设定 + 章纲」组装，可直接编辑</span>
        </label>
        <textarea
          className="ai-prompt"
          value={prompt}
          disabled={loading || refreshing}
          placeholder={loading ? "组装中…" : ""}
          onChange={(e) => setPrompt(e.target.value)}
          data-testid="ai-prompt"
        />
        {legacyKind ? (
          legacyKind === "polished" ? (
            <p
              style={{ margin: "8px 0 0", fontSize: 12, color: "var(--muted)" }}
              data-testid="ai-legacy-note"
            >
              恒定设定（题材/文风/世界观/铁律）已由系统按本书设定注入，与本稿并存；可继续编辑。
            </p>
          ) : (
            <p
              style={{ margin: "8px 0 0", fontSize: 12, color: "var(--warn)" }}
              data-testid="ai-legacy-note"
            >
              旧版整包稿：恒定设定已由系统注入，点「刷新提示词」可按新分层重组为本章素材。
            </p>
          )
        ) : null}
        {lintWarnings.length > 0 ? (
          <p
            style={{ margin: "8px 0 0", fontSize: 12, color: "var(--warn)" }}
            data-testid="ai-lint-warnings"
          >
            {lintWarnings.join("；")}
          </p>
        ) : null}
        {/* 刷新＋存稿行：刷新＝fresh 组装稿仅换预览（不动存量行）；生成＝本次所用稿落库；
            存稿＝不生成只落库 */}
        <div className="ai-prompt-save">
          <span>
            「刷新提示词」按最新章纲重新组装章级素材（恒定设定由系统按本书设定注入，不动已存稿）；点「生成正文」＝本次用的这一版同时记为本章提示词，只想先存不生成用「存为本章提示词」。
          </span>
          <div style={{ display: "flex", gap: 8, flex: "none" }}>
            <button
              className="btn btn-ghost btn-sm"
              data-testid="ai-prompt-refresh"
              title="按最新章纲重新组装章级素材；不改动已存稿，可再编辑"
              disabled={loading || refreshing}
              onClick={() => void handleRefresh()}
            >
              {refreshing ? "刷新中…" : "刷新提示词"}
            </button>
            <button
              className="btn btn-ghost btn-sm"
              data-testid="ai-prompt-save"
              disabled={loading || refreshing || saving || !!error || !prompt.trim()}
              onClick={() => void handleSavePrompt()}
            >
              {saving ? "保存中…" : "存为本章提示词"}
            </button>
          </div>
        </div>
      </div>
      {/* 生成模型（c-prose-model-select）：仅弹窗打开时挂载取数；单选/未就绪不渲染 */}
      {open && (
        <ModelField projectId={projectId} modelSel={modelSel} onChange={setModelSel} />
      )}
      {error ? (
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
            ? hasProse
              ? "过目／编辑后点「生成正文」；本次生成将清空并替换本章现有正文，旧正文可从版本历史找回。"
              : "过目／编辑后点「生成正文」；生成内容将写入本章。"
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
