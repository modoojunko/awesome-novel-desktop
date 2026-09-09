// ── GenrePickerModal ──────────────────────────────────────────────────────
// 题材选择弹窗（book.html #modalGenre v2 结构）：
//   mcard-head（选择题材 + 新建题材 text-btn + x）/ 搜索 / 6 分组堆叠
//   g-grid 双列 g-item / mcard-foot（注记 + 取消 + 应用题材）。
// 打开时从后端拉全量题材（含自定义），内存搜索；预置只读，自定义悬浮可编辑/删除
// （g-acts 为产品扩展，原型未建模）。分类导航退役——按原型全分组堆叠。

import { useCallback, useEffect, useMemo, useState } from "react";
import { Ico, P } from "@/components/icons";
import Modal from "@/components/design/Modal";
import {
  GENRE_CATEGORIES,
  fetchGenres,
  deleteGenre,
  type GenreDefinition,
} from "@/data/genres";
import GenreEditModal from "./GenreEditModal";
import DeleteConfirmModal from "../DeleteConfirmModal";

// ── Props ────────────────────────────────────────────────────────────────

interface GenrePickerModalProps {
  open: boolean;
  /** Currently selected genre id */
  currentGenreId?: string;
  /** Called when user confirms a genre selection */
  onConfirm: (genreId: string) => void;
  /** Called when modal is dismissed without saving */
  onClose: () => void;
}

interface DeleteError {
  message: string;
  novels?: string[];
}

// ── Component ────────────────────────────────────────────────────────────

export default function GenrePickerModal({
  open,
  currentGenreId,
  onConfirm,
  onClose,
}: GenrePickerModalProps) {
  const [genres, setGenres] = useState<GenreDefinition[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | undefined>(currentGenreId);

  // CRUD sessions
  const [editSession, setEditSession] = useState<
    { mode: "create" } | { mode: "edit"; genre: GenreDefinition } | null
  >(null);
  const [deleteTarget, setDeleteTarget] = useState<GenreDefinition | null>(null);
  const [deleteError, setDeleteError] = useState<DeleteError | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      setGenres(await fetchGenres());
    } catch (e: any) {
      setLoadError(e.message || "加载题材失败");
    } finally {
      setLoading(false);
    }
  }, []);

  // Reset on open
  useEffect(() => {
    if (open) {
      setSelectedId(currentGenreId);
      setSearchQuery("");
      setDeleteError(null);
      refresh();
    }
  }, [open, currentGenreId, refresh]);

  // 按分类分组（原型口径：全分组堆叠；搜索按名称/描述过滤，分组无命中即隐藏）
  const groups = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    const match = (g: GenreDefinition) =>
      !q ||
      g.name.toLowerCase().includes(q) ||
      g.description.toLowerCase().includes(q);
    return GENRE_CATEGORIES.map((cat) => ({
      ...cat,
      items: genres.filter((g) => g.category === cat.id && match(g)),
    })).filter((grp) => grp.items.length > 0);
  }, [genres, searchQuery]);

  const handleConfirm = () => {
    if (selectedId) {
      onConfirm(selectedId);
    }
    onClose();
  };

  // ── Create / edit ────────────────────────────────────────────────
  const handleSaved = async (saved: GenreDefinition) => {
    setEditSession(null);
    setSelectedId(saved.id);
    await refresh();
  };

  // ── Delete ───────────────────────────────────────────────────────
  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    setDeleteError(null);
    try {
      await deleteGenre(deleteTarget.id);
      setGenres((gs) => gs.filter((g) => g.id !== deleteTarget.id));
      setSelectedId((s) => (s === deleteTarget.id ? undefined : s));
      setDeleteTarget(null);
    } catch (e: any) {
      // 409 时 e.novels 已由 request() 透传
      setDeleteTarget(null);
      setDeleteError({ message: e.message || "删除失败", novels: e?.novels });
    }
  };

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title="选择题材"
        wbStyle
        headExtra={
          <button
            className="text-btn"
            type="button"
            onClick={() => setEditSession({ mode: "create" })}
          >
            <Ico d={P.plus} sw={2} size={14} />
            新建题材
          </button>
        }
        footer={
          <>
            <span className="note">切换题材仅替换模板，已填内容保留</span>
            <button className="btn btn-secondary" type="button" onClick={onClose}>
              取消
            </button>
            <button
              className="btn btn-primary"
              type="button"
              onClick={handleConfirm}
              disabled={!selectedId}
            >
              应用题材
            </button>
          </>
        }
      >
        <div className="search-wrap">
          <Ico d={P.search} sw={1.8} />
          <input
            className="search"
            placeholder="搜索题材…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        {deleteError && (
          <p className="opt" style={{ color: "var(--err)", margin: "10px 0 0" }}>
            {deleteError.message}
            {deleteError.novels && deleteError.novels.length > 0 && (
              <>　使用该题材的作品：{deleteError.novels.join("、")}</>
            )}
          </p>
        )}

        {loading ? (
          <p className="opt" style={{ padding: "24px 0", textAlign: "center" }}>查询中…</p>
        ) : loadError ? (
          <p className="opt" style={{ color: "var(--err)", padding: "24px 0", textAlign: "center" }}>
            {loadError}
          </p>
        ) : (
          <>
            {groups.map((grp) => (
              <div className="g-group" key={grp.id}>
                <div className="gt">{grp.label}</div>
                <div className="g-grid">
                  {grp.items.map((genre) => (
                    <div
                      key={genre.id}
                      className={`g-item${selectedId === genre.id ? " on" : ""}`}
                      onClick={() => setSelectedId(genre.id)}
                    >
                      <span>{genre.name}</span>
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 6, minWidth: 0 }}>
                        {!genre.isPreset && (
                          <span
                            className="g-acts"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <button
                              className="icon-btn"
                              type="button"
                              title="编辑题材"
                              onClick={() => setEditSession({ mode: "edit", genre })}
                            >
                              <Ico d={P.pencil} sw={1.7} />
                            </button>
                            <button
                              className="icon-btn"
                              type="button"
                              title="删除题材"
                              onClick={() => setDeleteTarget(genre)}
                            >
                              <Ico d={P.trash} sw={1.7} />
                            </button>
                          </span>
                        )}
                        <span className="gp">{genre.description}</span>
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
            {groups.length === 0 && (
              <div className="empty-search">没有匹配的题材，可稍后在「其他」中自建。</div>
            )}
          </>
        )}
      </Modal>

      {/* ── Create / edit modal ─────────────────────────────────── */}
      {editSession && (
        <GenreEditModal
          genre={editSession.mode === "edit" ? editSession.genre : null}
          onClose={() => setEditSession(null)}
          onSaved={handleSaved}
        />
      )}

      {/* ── Delete confirm modal ────────────────────────────────── */}
      {deleteTarget && (
        <DeleteConfirmModal
          wbStyle
          title="题材"
          confirmText={deleteTarget.name}
          description="该题材定义将被永久删除。正在使用它的作品会进入「定义缺失」降级态（覆盖项仍可保存），但无法再获得该题材的完整设定。"
          onConfirm={handleDeleteConfirm}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </>
  );
}
