/** 「章档」页签（c-chapter-dossier）：本章四域档案——提取进度/失败逃生阀/未提取态、
 *  待确认清单（逐条＋批量采纳）、已采纳分组（可删）、「截至本章」累计预览。
 *  只取已采纳行进下一章提示词；伏笔/世界要素提案仍在「操作」页签（PRO）。 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  dossierApi,
  DOSSIER_DOMAINS,
  type DossierDomain,
  type DossierPreview,
  type DossierRow,
  type DossierState,
} from "@/lib/dossierApi";

const EXTRACT_STEPS = ["受理", "AI 提取", "写入章档", "置为已归档"];

function rowText(r: DossierRow): string {
  switch (r.domain) {
    case "settings":
      return `${r.area ? `${r.area}：` : ""}${r.content ?? ""}`;
    case "relations":
      return `${r.owner ?? "?"} → ${r.other ?? "?"}：${r.rel_type ?? ""}${
        r.change_note ? `（${r.change_note}）` : ""
      }`;
    case "items":
      return `${r.name ?? "?"}：${r.change_type ?? ""}${
        r.holder ? `，现在在 ${r.holder} 手中` : ""
      }`;
    default:
      return `${r.character ?? "?"} ${r.learned ? "已得知" : "仍不知道"}「${r.fact ?? ""}」${
        r.learned ? "" : `（${r.character ?? "?"}不知）`
      }`;
  }
}

export function DossierPane({
  projectId,
  chapterRef,
}: {
  projectId: string;
  chapterRef: string;
}) {
  const [data, setData] = useState<DossierState | null>(null);
  const [preview, setPreview] = useState<DossierPreview | null>(null);
  const [openRows, setOpenRows] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState(false);

  const load = useCallback(async () => {
    try {
      const d = await dossierApi.get(projectId, chapterRef);
      setData(d);
      setLoadError(false);
    } catch {
      setLoadError(true);
    }
  }, [projectId, chapterRef]);

  useEffect(() => {
    setData(null);
    setPreview(null);
    void load();
  }, [load]);

  // 提取中：3s 轮询（页签可见才轮询——条件挂载）
  useEffect(() => {
    if (data?.extraction?.state !== "extracting") return;
    const t = setTimeout(() => void load(), 3000);
    return () => clearTimeout(t);
  }, [data, load]);

  // 提取终态（跨页签完成）→ 补拉一次＋累计预览刷新
  const prevExtractRef = useRef<string | null>(null);
  useEffect(() => {
    const st = data?.extraction?.state ?? null;
    if (prevExtractRef.current === "extracting" && st && st !== "extracting") {
      void load();
    }
    prevExtractRef.current = st;
  }, [data?.extraction?.state, load]);

  const loadPreview = useCallback(async () => {
    try {
      setPreview(await dossierApi.preview(projectId, chapterRef));
    } catch {
      /* 预览失败不阻塞清单 */
    }
  }, [projectId, chapterRef]);

  // 有已采纳行时拉累计预览（与下一章提示词同源）
  useEffect(() => {
    if (data && data.progress.accepted > 0 && !preview) void loadPreview();
  }, [data, preview, loadPreview]);

  const refreshAll = useCallback(async () => {
    await load();
    setPreview(null);
  }, [load]);

  const act = useCallback(
    async (fn: () => Promise<unknown>) => {
      setBusy(true);
      try {
        await fn();
      } finally {
        setBusy(false);
        await refreshAll();
      }
    },
    [refreshAll],
  );

  if (loadError && !data) {
    return (
      <div className="dossier-pane" data-od-id="dossier-pane">
        <p className="ds-note">章档加载失败，稍后重试。</p>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="dossier-pane" data-od-id="dossier-pane">
        <p className="ds-note">章档载入中…</p>
      </div>
    );
  }

  const pending = data.progress.pending;
  const extractState = data.extraction?.state ?? null;

  return (
    <div className="dossier-pane" data-od-id="dossier-pane" data-testid="dossier-pane">
      <div className="ds-head">
        <h3>章档 · 本章设定档案</h3>
        <span className="ds-sub">确认后喂给下一章提示词；不确认不喂</span>
      </div>

      {data.stale && (
        <div className="ds-banner warn" data-testid="dossier-stale-banner">
          本章重写过，章档基于旧设定 ·{" "}
          <button
            className="btn btn-ghost btn-sm"
            disabled={busy || extractState === "extracting"}
            onClick={() =>
              void act(() => dossierApi.extract(projectId, chapterRef))
            }
          >
            重新提取
          </button>
        </div>
      )}

      {extractState === "extracting" && (
        <>
          <div className="ds-banner warn" data-testid="dossier-extracting">
            AI 提取中 · 本章已锁定（约 1-3 分钟），完成后自动归档并出四域待确认
          </div>
          <div className="ds-steps" data-testid="dossier-steps">
            {EXTRACT_STEPS.map((t, i) => (
              <span key={t} className={`ds-step ${i < 2 ? "done" : i === 2 ? "cur" : ""}`}>
                <b>{i + 1}</b>
                {t}
              </span>
            )).flatMap((el, i, arr) => (i < arr.length - 1 ? [el, <span key={`l${i}`} className="ds-step-line" />] : [el]))}
          </div>
        </>
      )}

      {extractState === "failed" && (
        <>
          <div className="ds-banner warn" data-testid="dossier-failed">
            提取失败：{data.extraction?.error || "模型输出不可解析（可重试）"}。本章尚未归档，正文已解锁。
          </div>
          <div className="ds-fail-actions">
            <button
              className="btn btn-primary btn-sm"
              data-testid="dossier-retry"
              disabled={busy}
              onClick={() => void act(() => dossierApi.extract(projectId, chapterRef))}
            >
              重试提取
            </button>
            <button
              className="btn btn-secondary btn-sm"
              data-testid="dossier-skip"
              disabled={busy}
              onClick={() => {
                if (
                  window.confirm(
                    "跳过提取后本章直接归档，但本章的设定/关系/物品/认知状态不会进入下一章前情（之后可在本页签补提取）。确定跳过？",
                  )
                )
                  void act(() => dossierApi.skip(projectId, chapterRef));
              }}
            >
              跳过提取，仍要归档
            </button>
          </div>
        </>
      )}

      {data.not_extracted && extractState !== "extracting" && (
        <div className="ds-banner warn" data-testid="dossier-not-extracted">
          本章已归档但未提取章档（归档时未配置模型 / 跳过提取）。
          <button
            className="btn btn-ghost btn-sm"
            disabled={busy}
            onClick={() => void act(() => dossierApi.extract(projectId, chapterRef))}
          >
            补提取章档
          </button>
          {/* 免费档配 key 引导（c-chapter-dossier D8）：提取全档可用，模型就绪即可 */}
          <a href="#/config">去「模型配置」</a>
        </div>
      )}

      {data.archived && !data.not_extracted && extractState !== "extracting" && extractState !== "failed" && data.rows.length === 0 && (
        <p className="ds-note">本章提取无产出（四域全空）——本章没有需要登记的变化。</p>
      )}

      {data.rows.length > 0 && (
        <>
          <div className="ds-batch">
            <button
              className="btn btn-primary btn-sm"
              data-testid="dossier-accept-all"
              disabled={busy || pending === 0}
              onClick={() => void act(() => dossierApi.batch(projectId, chapterRef, "accept"))}
            >
              全部采纳（{pending}）
            </button>
            <button
              className="btn btn-secondary btn-sm"
              disabled={busy || pending === 0}
              onClick={() => void act(() => dossierApi.batch(projectId, chapterRef, "reject"))}
            >
              全部驳回
            </button>
          </div>
          {DOSSIER_DOMAINS.map(({ key, label }) => {
            const rows = data.rows.filter((r) => r.domain === key);
            if (rows.length === 0) return null;
            const p = rows.filter((r) => r.status === "pending").length;
            return (
              <div key={key} className="ds-domain" data-testid={`dossier-domain-${key}`}>
                <div className="ds-domain-head">
                  <b>{label}</b>
                  <span className="cnt">{p ? `${p} 待确认` : "已处理"}</span>
                  {p > 0 && (
                    <button
                      className="btn btn-ghost btn-sm"
                      disabled={busy}
                      onClick={() =>
                        void act(() =>
                          dossierApi.batch(projectId, chapterRef, "accept", key as DossierDomain),
                        )
                      }
                    >
                      本域全采纳
                    </button>
                  )}
                </div>
                {rows.map((r) => {
                  const open = openRows.has(r.id);
                  return (
                    <div
                      key={r.id}
                      className={`ds-row${open ? " open" : ""}`}
                      data-testid="dossier-row"
                      onClick={() =>
                        setOpenRows((s) => {
                          const n = new Set(s);
                          if (n.has(r.id)) n.delete(r.id);
                          else n.add(r.id);
                          return n;
                        })
                      }
                    >
                      <div>
                        {rowText(r)}
                        {r.flags.includes("evidence_unverified") && (
                          <span className="ds-flag">证据待核</span>
                        )}
                        {r.flags.includes("unregistered") && <span className="ds-flag">未登记</span>}
                      </div>
                      <div className="ds-ev">证据：「{r.evidence || "（无）"}」（点击行收起）</div>
                      {r.status === "pending" ? (
                        <div className="ds-actions" onClick={(e) => e.stopPropagation()}>
                          <button
                            className="btn btn-primary btn-sm"
                            disabled={busy}
                            onClick={() =>
                              void act(() =>
                                dossierApi.rowAction(projectId, chapterRef, r.id, "accept"),
                              )
                            }
                          >
                            采纳
                          </button>
                          <button
                            className="btn btn-ghost btn-sm"
                            disabled={busy}
                            onClick={() =>
                              void act(() =>
                                dossierApi.rowAction(projectId, chapterRef, r.id, "reject"),
                              )
                            }
                          >
                            驳回
                          </button>
                        </div>
                      ) : r.status === "accepted" ? (
                        <div className="ds-actions" onClick={(e) => e.stopPropagation()}>
                          <span className="cnt ok">已采纳</span>
                          <button
                            className="btn btn-ghost btn-sm"
                            disabled={busy}
                            onClick={() => {
                              if (window.confirm("删除这条已采纳记录？它将退出下一章提示词。"))
                                void act(() =>
                                  dossierApi.rowDelete(projectId, chapterRef, r.id),
                                );
                            }}
                          >
                            删除
                          </button>
                        </div>
                      ) : (
                        <div className="ds-actions" onClick={(e) => e.stopPropagation()}>
                          <span className="cnt">已驳回</span>
                          <button
                            className="btn btn-ghost btn-sm"
                            disabled={busy}
                            onClick={() =>
                              void act(() =>
                                dossierApi.rowAction(projectId, chapterRef, r.id, "restore"),
                              )
                            }
                          >
                            恢复待确认
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </>
      )}

      {preview?.counts && (
        <div className="ds-preview" data-testid="dossier-preview">
          <b>截至本章 · 累计状态</b>（下一章提示词实际注入的内容）
          <br />
          设定 {preview.counts.settings ?? 0} 条 · 关系 {preview.counts.relations ?? 0} 条 ·
          物品 {preview.counts.items ?? 0} 条 · 认知 {preview.counts.knowledge ?? 0} 条
          {(preview.skipped_stale_refs ?? []).length > 0 && (
            <>
              {" "}
              （第 {(preview.skipped_stale_refs ?? []).slice(0, 3).join("、")}{" "}
              章的章档基于旧设定，仅供参考）
            </>
          )}
        </div>
      )}

      <div className="ds-note">
        伏笔 / 世界要素提案在「操作」页签（PRO）→ · 文风影子见「文风」页签 ·
        章档只记本章变化，不改你的初始设定
      </div>
    </div>
  );
}
