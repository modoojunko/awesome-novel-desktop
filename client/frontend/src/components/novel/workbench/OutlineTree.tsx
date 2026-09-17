// 大纲树（book.html 树列复刻）：树头统计 + 加卷弹窗 + 三态 dot + hover 操作
// + 行内加章 + 批量确认 + 默认全展开（ADJUSTMENTS #4）。
// 应用侧扩展（ADJUSTMENTS #6）：hover 操作补「铅笔」行内重命名（#164 名称即标题口径）。
// PR 5：删除走分级确认弹窗（空章无盘点；有内容 chips 盘点；卷带章数字数）。
import { useEffect, useRef, useState } from "react";
import { Ico, P } from "@/components/icons";
import Modal from "@/components/design/Modal";
import { DeleteConfirmModal } from "./modals";
import { api, request } from "@/lib/api";
import { toast } from "@/lib/toast";
import { cnNum, editName, nodeLabel } from "@/lib/nodeTitle";
import type { UseOutlineReturn } from "@/hooks/useOutline";
import type { UseWorkbenchReturn } from "@/hooks/useWorkbench";
import { chapterNoOf, volNoOf } from "@/lib/chapterRef";

interface OutlineTreeProps {
  wb: UseWorkbenchReturn;
  outline: UseOutlineReturn;
  projectId: string;
  /** 卷编辑态脏守卫（VolumePanel 上抛）：切节点前确认 */
  guardedLeave: () => boolean;
  /** 选中章实时字数（原型 askDelete 用 live 内容计数；树计数要等刷新） */
  liveWords: { ref: string; words: number } | null;
}

function volNo(name: string): number {
  const m = name.match(/^vol-(\d+)$/);
  return m ? parseInt(m[1], 10) : 0;
}

export default function OutlineTree({
  wb,
  outline,
  projectId,
  guardedLeave,
  liveWords,
}: OutlineTreeProps) {
  const { volumes, selectedId, expandedIds, onToggle } = wb;
  const [addVolOpen, setAddVolOpen] = useState(false);
  // 行内加章：目标卷
  const [inlineAddVol, setInlineAddVol] = useState<string | null>(null);
  // 行内重命名：{ kind, id, no, value }
  const [renaming, setRenaming] = useState<{
    kind: "卷" | "章";
    id: string;
    no: number;
    value: string;
  } | null>(null);
  const inlineInputRef = useRef<HTMLInputElement>(null);
  const renameInputRef = useRef<HTMLInputElement>(null);
  // Enter 提交后卸载输入框仍可能触发一次 blur：会话级幂等防重复建章
  const inlineDoneRef = useRef(false);

  // 默认全展开：树首载入后逐卷展开一次（用户随后可自由折叠）
  const initExpandRef = useRef(false);
  useEffect(() => {
    if (initExpandRef.current || volumes.length === 0) return;
    initExpandRef.current = true;
    volumes.forEach((v) => {
      if (!expandedIds.has(v.name)) onToggle(v.name);
    });
  }, [volumes, expandedIds, onToggle]);

  useEffect(() => {
    if (inlineAddVol) inlineInputRef.current?.focus();
  }, [inlineAddVol]);
  useEffect(() => {
    if (renaming) renameInputRef.current?.focus();
  }, [renaming]);

  const chTotal = volumes.reduce((a, v) => a + v.chapters.length, 0);

  const selectChapter = (ref: string) => {
    if (ref !== selectedId && !guardedLeave()) return;
    wb.focusNode(ref); // 点章 → 选中 + 展开所属卷 + 落工作台（chTab 复位由 ChapterWorkspace effect）
  };
  const selectVolume = (name: string) => {
    if (name !== selectedId && !guardedLeave()) return;
    wb.onSelectNode({ id: name, label: "", data: { type: "volume", volume: name } });
  };

  // 删除分级确认（#modalDelete 口径）：章盘点 chips / 卷带章数字数
  const [delTarget, setDelTarget] = useState<{
    kind: "chapter" | "volume";
    ref: string;
    title: string;
    chips: string[];
    chapterCount: number;
    totalWords: number;
  } | null>(null);

  const askDeleteChapter = async (
    vol: (typeof volumes)[number],
    c: (typeof vol.chapters)[number],
  ) => {
    const ref = `${vol.name}-ch-${c.chapter}`;
    const st = outline.chapterStatuses.get(ref) ?? "unfilled";
    const chips: string[] = [];
    if (st === "confirmed") chips.push("章纲已确认");
    else if (st === "in_progress") chips.push("章纲草稿");
    // 自定义提示词探测（免费态 403 静默，不计入盘点）
    try {
      const files: unknown = await request(
        `/novels/${projectId}/chapters/${ref}/prompts`,
        { quiet: true },
      );
      if (Array.isArray(files) && files.length > 0) chips.push("自定义提示词");
    } catch {
      /* 无提示词能力 = 未自定义 */
    }
    // 正文盘点：选中章用 store 实时字数（刚写完未刷新也能如实盘点）
    const live = liveWords?.ref === ref ? liveWords.words : c.word_count;
    if (live > 0) chips.push(`正文 ${live.toLocaleString("zh-CN")} 字`);
    setDelTarget({
      kind: "chapter",
      ref,
      title: nodeLabel("章", c.chapter, c.title),
      chips,
      chapterCount: 0,
      totalWords: 0,
    });
  };
  const askDeleteVolume = (v: (typeof volumes)[number]) => {
    setDelTarget({
      kind: "volume",
      ref: v.name,
      title: nodeLabel("卷", volNo(v.name), v.title),
      chips: [],
      chapterCount: v.chapters.length,
      // 含选中章时以实时字数替换（同章盘点口径）
      totalWords: v.chapters.reduce(
        (a, c) =>
          a +
          (liveWords?.ref === `${v.name}-ch-${c.chapter}`
            ? liveWords.words
            : c.word_count),
        0,
      ),
    });
  };

  const commitInlineAdd = async (volName: string, raw: string) => {
    if (inlineDoneRef.current) return;
    inlineDoneRef.current = true;
    setInlineAddVol(null);
    const vol = volumes.find((v) => v.name === volName);
    const next = (vol?.chapters.length ?? 0) + 1;
    // 默认标题用纯序号形态（isDefaultTitle 命中 → 树上只显示序号，改名预填空）
    const title = raw.trim() || `第${cnNum(next)}章`;
    const ref = await wb.createChapter(title, volName);
    if (ref) toast.success(`已添加《${title}》`);
  };

  const commitRename = async () => {
    if (!renaming) return;
    const { kind, id, value } = renaming;
    setRenaming(null);
    const next = value.trim();
    if (!next) return; // 名称即标题且必填：留空视为取消
    const current = findCurrentTitle(wb, kind, id);
    if (next === current) return;
    await wb.renameNode(id, next);
  };

  const handleBatchConfirm = async () => {
    let n = 0;
    for (const v of outline.volumes) {
      for (const c of v.chapters) {
        if (c.status === "confirmed" || c.archived) continue;
        try {
          await request(`/novels/${projectId}/chapters/${c.ref}/confirm`, {
            method: "POST",
            quiet: true,
          });
          n++;
        } catch {
          // 必填字段未完成（400）→ 跳过
        }
      }
    }
    await Promise.allSettled([outline.refetchTree(), wb.refresh()]);
    toast.success(
      n ? `已确认 ${n} 章章纲` : "没有可确认的章节（必填字段未完成的章节已跳过）",
    );
  };

  return (
    <>
      <div className="tree-head">
        <span className="t">
          大纲 · 卷 <b>{volumes.length}</b> · 章 <b>{chTotal}</b>
        </span>
        <button
          className="icon-btn"
          title="添加卷"
          onClick={() => setAddVolOpen(true)}
        >
          <Ico d={P.plus} sw={1.8} />
        </button>
      </div>

      <div className="tree">
        {volumes.map((v) => {
          const no = volNo(v.name);
          const open = expandedIds.has(v.name);
          return (
            <div className="vol" key={v.name}>
              <div
                className={"vol-head" + (selectedId === v.name ? " sel" : "")}
                onClick={(e) => {
                  if ((e.target as HTMLElement).closest(".acts")) return;
                  if ((e.target as HTMLElement).closest(".chev")) {
                    onToggle(v.name);
                    return;
                  }
                  selectVolume(v.name);
                }}
              >
                <Ico d={P.chevronRight} className={"chev" + (open ? " open" : "")} />
                {renaming?.kind === "卷" && renaming.id === v.name ? (
                  <input
                    ref={renameInputRef}
                    className="input"
                    style={{ height: 24, fontSize: 13, padding: "0 8px" }}
                    value={renaming.value}
                    onChange={(e) => setRenaming({ ...renaming, value: e.target.value })}
                    onClick={(e) => e.stopPropagation()}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") void commitRename();
                      if (e.key === "Escape") setRenaming(null);
                    }}
                    onBlur={() => void commitRename()}
                  />
                ) : (
                  <span className="vt">{nodeLabel("卷", no, v.title)}</span>
                )}
                <span className="acts">
                  <button
                    className="icon-btn"
                    title="重命名卷"
                    onClick={(e) => {
                      e.stopPropagation();
                      setRenaming({
                        kind: "卷",
                        id: v.name,
                        no,
                        value: editName("卷", no, v.title),
                      });
                    }}
                  >
                    <Ico d={P.pencil} />
                  </button>
                  <button
                    className="icon-btn"
                    title="添加章节"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (!open) onToggle(v.name);
                      inlineDoneRef.current = false;
                      setInlineAddVol(v.name);
                    }}
                  >
                    <Ico d={P.plus} />
                  </button>
                  <button
                    className="icon-btn"
                    title="删除卷"
                    onClick={(e) => {
                      e.stopPropagation();
                      askDeleteVolume(v);
                    }}
                  >
                    <Ico d={P.trash} />
                  </button>
                </span>
              </div>
              <div className="ch-list" style={{ display: open ? "" : "none" }}>
                {v.chapters.map((c) => {
                  const ref = `${v.name}-ch-${c.chapter}`;
                  const st = outline.chapterStatuses.get(ref) ?? "unfilled";
                  return (
                    <div
                      key={ref}
                      className={"ch" + (selectedId === ref ? " sel" : "")}
                      onClick={() => selectChapter(ref)}
                    >
                      <span className={st === "confirmed" ? "dot-ok" : st === "in_progress" ? "dot-warn" : "dot-empty"} />
                      {renaming?.kind === "章" && renaming.id === ref ? (
                        <input
                          ref={renameInputRef}
                          className="input"
                          style={{ height: 22, fontSize: 12.5, padding: "0 8px", flex: 1, minWidth: 0 }}
                          value={renaming.value}
                          onChange={(e) => setRenaming({ ...renaming, value: e.target.value })}
                          onClick={(e) => e.stopPropagation()}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") void commitRename();
                            if (e.key === "Escape") setRenaming(null);
                          }}
                          onBlur={() => void commitRename()}
                        />
                      ) : (
                        <span className="ct">{nodeLabel("章", c.chapter, c.title)}</span>
                      )}
                      {c.archived && <span className="arch-tag">已归档</span>}
                      {c.stale && (
                        <span className="tag-stale" data-testid="ch-stale">
                          基于旧设定
                        </span>
                      )}
                      <span className="acts">
                        <button
                          className="icon-btn"
                          title="重命名章节"
                          onClick={(e) => {
                            e.stopPropagation();
                            setRenaming({
                              kind: "章",
                              id: ref,
                              no: c.chapter,
                              value: editName("章", c.chapter, c.title),
                            });
                          }}
                        >
                          <Ico d={P.pencil} />
                        </button>
                        <button
                          className="icon-btn"
                          title="删除章节"
                          onClick={(e) => {
                            e.stopPropagation();
                            void askDeleteChapter(v, c);
                          }}
                        >
                          <Ico d={P.trash} />
                        </button>
                      </span>
                    </div>
                  );
                })}
                {inlineAddVol === v.name && (
                  <div className="inline-add">
                    <input
                      ref={inlineInputRef}
                      placeholder="章节名，如：第五章 · 启程"
                      onKeyDown={(e) => {
                        if (e.key === "Enter") void commitInlineAdd(v.name, e.currentTarget.value);
                        if (e.key === "Escape") setInlineAddVol(null);
                      }}
                      onBlur={(e) => void commitInlineAdd(v.name, e.currentTarget.value)}
                    />
                  </div>
                )}
              </div>
            </div>
          );
        })}
        {volumes.length === 0 && (
          <div className="empty-tree">还没有卷与章节。点击左上「＋」添加第一卷。</div>
        )}
      </div>  {wb.ghosts.length > 0 && (
    <div className="ghost-group" data-od-id="ghost-group">
      <p className="gg-head">旧稿支线（只读）</p>
      {wb.ghosts.map((g) => (
        <button
          key={g.ref}
          className="ghost-row"
          title="旧稿支线 · 只读"
          onClick={() => wb.focusNode(g.ref)}
        >
          <span className="t">
            第{g.chapter}章 · {g.title || "未命名"}
          </span>
          <span className="w">{g.word_count} 字</span>
        </button>
      ))}
    </div>
  )}


      <div className="tree-foot">
        <button className="btn btn-ghost btn-sm batch" onClick={() => void handleBatchConfirm()}>
          确认全部已填章节
        </button>
      </div>

      <AddVolumeModal
        open={addVolOpen}
        onClose={() => setAddVolOpen(false)}
        projectId={projectId}
        createVolume={wb.createVolume}
        createChapter={wb.createChapter}
        onCreated={() => void outline.refetchTree()}
      />

      <DeleteConfirmModal
        open={!!delTarget}
        onClose={() => setDelTarget(null)}
        kind={delTarget?.kind ?? "chapter"}
        title={delTarget?.title ?? ""}
        chips={delTarget?.chips ?? []}
        chapterCount={delTarget?.chapterCount ?? 0}
        totalWords={delTarget?.totalWords ?? 0}
        onConfirm={() => {
          if (delTarget) void wb.deleteNode(delTarget.ref);
        }}
      />
    </>
  );
}

function findCurrentTitle(
  wb: UseWorkbenchReturn,
  kind: "卷" | "章",
  id: string,
): string | null {
  if (kind === "卷") {
    return wb.volumes.find((v) => v.name === id)?.title ?? null;
  }
  const volName = `vol-${volNoOf(id)}`;
  const chNo = chapterNoOf(id);
  if (!chNo) return null;
  const vol = wb.volumes.find((v) => v.name === volName);
  return vol?.chapters.find((c) => c.chapter === chNo)?.title ?? null;
}

// ---------------------------------------------------------------------------
// 添加卷弹窗（design/Modal）：卷名* + 卷摘要 + 初始章数 → loop 建章「第N章 · 未命名」
// ---------------------------------------------------------------------------

function AddVolumeModal({
  open,
  onClose,
  projectId,
  createVolume,
  createChapter,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  projectId: string;
  createVolume: UseWorkbenchReturn["createVolume"];
  createChapter: UseWorkbenchReturn["createChapter"];
  onCreated: () => void;
}) {
  const [title, setTitle] = useState("");
  const [summary, setSummary] = useState("");
  const [chapters, setChapters] = useState("0");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      setTitle("");
      setSummary("");
      setChapters("0");
      setSubmitting(false);
    }
  }, [open]);

  const handleConfirm = async () => {
    const t = title.trim();
    if (!t) {
      toast.error("请填写卷名");
      return;
    }
    setSubmitting(true);
    const volRef = await createVolume(t);
    if (!volRef) {
      setSubmitting(false); // 失败：toast 已提示，弹窗保持可重试
      return;
    }
    // 卷摘要：建卷后补写（createVolume 只提交卷名）
    if (summary.trim()) {
      try {
        const detail = await api.get(`/novels/${projectId}/volumes/${volRef}`);
        await api.put(`/novels/${projectId}/volumes/${volRef}`, {
          ...detail,
          summary: summary.trim(),
        });
      } catch {
        // 摘要补写失败不阻断建卷
      }
    }
    const n = Math.min(20, Math.max(0, parseInt(chapters || "0", 10) || 0));
    for (let i = 1; i <= n; i++) {
      await createChapter(`第${cnNum(i)}章`, volRef);
    }
    setSubmitting(false);
    onClose();
    onCreated();
    toast.success(`已创建《${t}》`);
  };

  return (
    <Modal
      open={open}
      onClose={() => !submitting && onClose()}
      title="添加卷"
      locked={submitting}
      wbStyle
      footer={
        <>
          <button className="btn btn-secondary" onClick={onClose} disabled={submitting}>
            取消
          </button>
          <button className="btn btn-primary" onClick={() => void handleConfirm()} disabled={submitting}>
            创建卷
          </button>
        </>
      }
    >
      <div className="field">
        <label htmlFor="add-vol-title">卷名</label>
        <input
          id="add-vol-title"
          className="input"
          placeholder="如：第一卷 · 风起"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor="add-vol-summary">
          卷摘要 <span className="opt">选填</span>
        </label>
        <textarea
          id="add-vol-summary"
          className="textarea"
          placeholder="这一卷讲什么？一句话即可"
          value={summary}
          onChange={(e) => setSummary(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor="add-vol-chapters">
          初始章数 <span className="opt">可在树中随时增删</span>
        </label>
        <input
          id="add-vol-chapters"
          className="input num"
          type="number"
          min={0}
          max={20}
          value={chapters}
          onChange={(e) => setChapters(e.target.value)}
        />
      </div>
    </Modal>
  );
}
