import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { parseChapterRef } from "@/lib/chapterRef";
import { api } from "@/lib/api";
import { toast } from "@/lib/toast";
import { useProject } from "@/hooks/useProject";
import type { TreeNode } from "@/components/novel/StructureTree";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

import { landingViewFor, stageFromChapters } from "@/lib/novelStage";

export type WorkspaceView =
  | "workbench"
  | "advanced-settings"
  | "archives";

/** 落点覆盖白名单（location state `landingView` 的合法值）。 */
const LANDING_VIEWS: WorkspaceView[] = ["workbench", "advanced-settings", "archives"];

export interface WorkbenchChapter {
  chapter: number;
  title: string;
  word_count: number;
  status: string;
  /** DB 章 id（foreshadow-settings-v2：伏笔选择器按 id 引用章；旧响应缺省时不读） */
  id?: string;
  /** 缺省时降级：word_count>0 或本地已载入 prose */
  has_prose?: boolean;
  archived?: boolean;
  /** chapter-rewrite：基于旧设定角标 */
  stale?: boolean;
  /** c-chapter-dossier：本章变化过期角标（上游重写置位、重归档清除） */
  dossier_stale?: boolean;

}

export interface WorkbenchVolume {
  /** vol-1 */
  name: string;
  title?: string;
  /** 章数目标（volume-plan-ai：右栏「卷的验证」一行展示） */
  chapter_target?: number | null;
  chapters: WorkbenchChapter[];
}

export interface WorkbenchNode {
  type: "volume" | "chapter";
  volume: string;
  chapter?: number;
  ref?: string;
}

export interface WorkbenchGhost {
  ref: string;
  chapter: number;
  title: string;
  word_count: number;
  ghost_of: string;
}

export interface UseWorkbenchReturn {
  project: Record<string, any> | null;
  volumes: WorkbenchVolume[];
  ghosts: WorkbenchGhost[];
  selectedId: string | null;
  selectedRef: string | null;
  view: WorkspaceView;
  setView: (view: WorkspaceView, payload?: Record<string, any>) => void;
  viewPayload: Record<string, any> | null;
  expandedIds: Set<string>;
  onToggle: (id: string) => void;
  onSelectNode: (node: TreeNode) => void;
  createVolume: (title: string) => Promise<string | null>;
  createChapter: (title: string, volName?: string) => Promise<string | null>;
  /** 建卷/建章请求在途（CTA 置忙禁用——双发闸，c-silent-data-guards） */
  creating: boolean;
  renameNode: (nodeId: string, newTitle: string) => Promise<void>;
  deleteNode: (nodeId: string) => Promise<void>;
  refresh: () => Promise<void>;
  focusNode: (ref: string) => void;
  /** 清选中（volume-plan-ai：采纳保存后落写作默认页） */
  clearSelection: () => void;
  /** 直选一卷（volume-plan-ai「卷的验证」点行） */
  selectVolume: (name: string) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function parseRef(ref: string): { vol: number; ch: number } | null {
  // ref 语法单源（chapterRef）：主线与旧稿 `-r{8hex}` 双形制统一解析，
  // 旧稿不再静默落 null（点旧稿无响应是 chapter-rewrite 评审 P0）
  const p = parseChapterRef(ref);
  return p ? { vol: p.vol, ch: p.ch } : null;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useWorkbench(): UseWorkbenchReturn {
  const { project } = useProject();
  const projectId = project?.id ?? "";
  // 书架「回看」一次性落点覆盖的载体（c-works-finish-flow）
  const location = useLocation();
  const navigate = useNavigate();

  const [volumes, setVolumes] = useState<WorkbenchVolume[]>([]);
  const [ghosts, setGhosts] = useState<
    Array<{ ref: string; chapter: number; title: string; word_count: number; ghost_of: string }>
  >([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedRef, setSelectedRef] = useState<string | null>(null);
  const [view, setViewState] = useState<WorkspaceView>("workbench");
  const [viewPayload, setViewPayload] = useState<Record<string, any> | null>(null);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const selectedRefRef = useRef<string | null>(null);
  /** 首次树加载是否已完成（默认落点要等它才有判据）。 */
  const loadedRef = useRef(false);
  /** 用户/深链是否已主动决定视图（主动意图优先于默认落点）。 */
  const navigatedRef = useRef(false);
  /** 默认落点是否已应用（只应用一次，后续刷新不回跳）。 */
  const landingAppliedRef = useRef(false);
  const viewPayloadRef = useRef<Record<string, any> | null>(null);
  selectedRefRef.current = selectedRef;
  // 删卷后清选中用：卷选中时 selectedRef 为空，需对照 selectedId
  const selectedIdRef = useRef<string | null>(null);
  selectedIdRef.current = selectedId;
  // 建卷→建章链路（「＋ 新增一章」先垫卷再排章）里闭包 volumes 是 refresh 前的旧值，
  // 会把刚建的卷当不存在（「请先创建卷」误报）。创建类操作一律读 ref 拿最新树。
  const volumesRef = useRef<WorkbenchVolume[]>([]);
  volumesRef.current = volumes;
  // 创建 in-flight 闸（c-silent-data-guards）：双击/慢响应重试不得产生第二次创建请求
  // （后端 MAX+1+upsert 会把裸重放当「作者想再排一章」→ 静默多建）
  const creatingRef = useRef(false);
  const [creating, setCreating] = useState(false);

  // -----------------------------------------------------------------------
  // Load volumes（DB 全量树：GET /volumes 一次返回卷+章元数据，change 006）
  // -----------------------------------------------------------------------

  const refresh = useCallback(async () => {
    if (!projectId) return;
    try {
      const vols: Array<{
        ref: string;
        title?: string;
        chapter_target?: number | null;
        chapters?: Array<{
          id?: string;
          chapter: number;
          title: string;
          word_count: number;
          status: string;
          has_prose?: boolean;
          archived?: boolean;
          stale?: boolean;
          dossier_stale?: boolean;
        }>;
      }> = await api.get(`/novels/${projectId}/volumes`);
      // 旧稿支线（revert-ghost）：与主线卷章分流的只读章
      try {
        const ghostRows: Array<{
          id?: string;
          ref: string;
          chapter: number;
          title: string;
          word_count: number;
          ghost_of: string;
        }> = await api.get(`/novels/${projectId}/ghosts`);
        setGhosts(
          ghostRows.map((g) => ({
            ref: g.ref,
            chapter: g.chapter,
            title: g.title,
            word_count: g.word_count,
            ghost_of: g.ghost_of,
          })),
        );
      } catch {
        setGhosts([]);
      }
      const mapped = vols.map((v) => ({
        name: v.ref,
        title: v.title,
        // 章数目标（volume-plan-ai：右栏「卷的验证」一行展示）
        chapter_target: v.chapter_target ?? null,
        chapters: (v.chapters || []).map((c) => {
          const hasProse = c.has_prose ?? c.word_count > 0;
          return {
            id: c.id,
            chapter: c.chapter,
            title: c.title,
            word_count: c.word_count || 0,
            status: c.status || "outline",
            has_prose: hasProse,
            archived: c.archived ?? c.status === "archived",
            // chapter-rewrite：基于旧设定角标（后端 /volumes 直出）
            stale: c.stale ?? false,
            // c-chapter-dossier：本章变化过期角标（后端 /volumes 直出）
            dossier_stale: c.dossier_stale ?? false,
          };
        }),
      }));
      // ref 即时同步：建卷→建章链路在 React 重渲染 flush 之前就要读最新树
      volumesRef.current = mapped;
      setVolumes(mapped);
    } catch {
      // volumes might not be available yet
    } finally {
      loadedRef.current = true;
    }
  }, [projectId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // 归档后树 📦 即时同步（useChapterData 归档成功 dispatch "chapter:archived"）
  useEffect(() => {
    const onArchived = () => void refresh();
    window.addEventListener("chapter:archived", onArchived);
    return () => window.removeEventListener("chapter:archived", onArchived);
  }, [refresh]);

  // -----------------------------------------------------------------------
  // Selection
  // -----------------------------------------------------------------------

  const onSelectNode = useCallback((node: TreeNode) => {
    const data = node.data as WorkbenchNode | undefined;
    if (!data) return;
    if (data.type === "volume") {
      setSelectedId(data.volume);
      setSelectedRef(null);
      setViewState("workbench");
    } else if (data.type === "chapter") {
      const ref = data.ref ?? node.id;
      setSelectedId(ref);
      setSelectedRef(ref);
      setViewState("workbench");
    }
  }, []);

  const focusNode = useCallback((ref: string) => {
    // 注意：**不**在此标记「已主动导航」——首次加载的「自动聚焦第一章」也走这里，
    // 标了会让默认落点被误判成「用户已决定视图」而永不生效。显式导航只认 setView
    // （modnav / 去写作 / 跳转）；且落点只在首次加载后应用一次，之后用户点击不受影响。
    const parsed = parseRef(ref);
    if (!parsed) return;
    const volName = `vol-${parsed.vol}`;
    setExpandedIds((prev) => {
      const next = new Set(prev);
      next.add(volName);
      return next;
    });
    setSelectedId(ref);
    setSelectedRef(ref);
    setViewState("workbench");
    setViewPayload(null);
  }, []);

  /** 清选中（volume-plan-ai：采纳保存后落写作默认页） */
  const clearSelection = useCallback(() => {
    setSelectedId(null);
    setSelectedRef(null);
  }, []);

  /** 直选一卷（卷 ref 不经章 ref 解析；volume-plan-ai「卷的验证」点行用） */
  const selectVolume = useCallback((name: string) => {
    setSelectedId(name);
    setSelectedRef(null);
    setViewState("workbench");
    setViewPayload(null);
    setExpandedIds((prev) => {
      const next = new Set(prev);
      next.add(name);
      return next;
    });
  }, []);

  // 初次进入：书里有章但未选中 → 自动聚焦第一章（book.html 默认 selCh=c1）。
  // 仅首次生效（ref 消费后不再触发），删除章节清空选中不回跳。
  // 守卫须同时看 selectedId（卷选中）：否则选卷查看时任何树刷新（如卷保存
  // 触发的 refresh）都会把选中重置回首章。
  const didInitSelectRef = useRef(false);
  useEffect(() => {
    if (didInitSelectRef.current || selectedRefRef.current || selectedIdRef.current) return;
    const first = volumes.find((v) => v.chapters.length > 0);
    if (!first) return;
    didInitSelectRef.current = true;
    focusNode(`${first.name}-ch-${first.chapters[0].chapter}`);
  }, [volumes, focusNode]);

  // -----------------------------------------------------------------------
  // 首次打开书的默认落点（用户 2026-09-10 拍板；c-works-finish-flow 四态）：
  //   无章节 → 设定页；待完本（全归档未完结）→ 写作；已完结 → 预览；否则 → 写作。
  // 只在首次树加载后应用一次；用户/深链已主动决定视图时不覆盖。
  // 落点覆盖：书架「回看」携带一次性 location state（landingView）——认领即视为
  // 显式选择，并立即清 state（replace 导航），防刷新重放。
  // 声明在「自动聚焦第一章」之后 —— 聚焦只负责选中，视图仍由落点决定。
  // -----------------------------------------------------------------------
  useEffect(() => {
    if (landingAppliedRef.current || !loadedRef.current) return;
    landingAppliedRef.current = true;
    const override = location.state?.landingView;
    if (typeof override === "string" && LANDING_VIEWS.includes(override as WorkspaceView)) {
      navigate(location.pathname, { replace: true }); // 认领即清，刷新不重放
      if (override !== "workbench") setViewState(override as WorkspaceView);
      return;
    }
    if (navigatedRef.current || viewPayloadRef.current) return;
    const total = volumes.reduce((n, v) => n + v.chapters.length, 0);
    const archived = volumes.reduce(
      (n, v) => n + v.chapters.filter((c) => c.archived).length,
      0,
    );
    const target = landingViewFor(
      stageFromChapters(total, archived, project?.finished_at ?? null),
    );
    if (target !== "workbench") setViewState(target);
  }, [volumes, location.state, location.pathname, navigate, project?.finished_at]);

  const onToggle = useCallback((id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const setView = useCallback(
    (next: WorkspaceView, payload?: Record<string, any>) => {
      navigatedRef.current = true;
      setViewState(next);
      setViewPayload(payload ?? null);
      viewPayloadRef.current = payload ?? null;
      // 切到 workbench 时若无选中，保留现状；focusNode 由调用方显式触发
    },
    [],
  );

  // -----------------------------------------------------------------------
  // Create volume（序号程序排定；名称必填，即卷标题）
  // -----------------------------------------------------------------------

  const createVolume = useCallback(
    async (title: string): Promise<string | null> => {
      if (!projectId || creatingRef.current) return null;
      creatingRef.current = true;
      setCreating(true);
      const volNum = volumesRef.current.length + 1;
      try {
        const result = await api.post(`/novels/${projectId}/volumes`, { title });
        await refresh();
        const name = result.ref || `vol-${volNum}`;
        setSelectedId(name);
        setSelectedRef(null);
        setExpandedIds((prev) => {
          const next = new Set(prev);
          next.add(name);
          return next;
        });
        return name;
      } catch {
        toast.error("创建卷失败");
        return null;
      } finally {
        creatingRef.current = false;
        setCreating(false);
      }
    },
    [projectId, refresh],
  );

  // -----------------------------------------------------------------------
  // Create chapter（目标卷由调用方指定；选中卷优先，缺省第一卷；新章即达编辑器 N1）
  // -----------------------------------------------------------------------

  const createChapter = useCallback(
    async (title: string, volName?: string): Promise<string | null> => {
      if (!projectId || creatingRef.current) return null;
      creatingRef.current = true;
      setCreating(true);
      // 指定卷 > 选中卷 > 第一卷；无卷由调用方（Workbench）先走建卷弹窗
      // （读 volumesRef/selectedIdRef：建卷弹窗连续建章时闭包 state 尚未更新）
      const vols = volumesRef.current;
      const targetVol =
        (volName && vols.find((v) => v.name === volName)) ||
        vols.find((v) => v.name === selectedIdRef.current) ||
        vols[0];
      if (!targetVol) {
        toast.error("请先创建卷");
        return null;
      }
      const volRef = targetVol.name;
      const nextCh = targetVol.chapters.length + 1;
      try {
        const result = await api.post(
          `/novels/${projectId}/volumes/${volRef}/chapters`,
          { title },
        );
        await refresh();
        // 「本书排过章」持久信号（volume-plan-ai 落点卡判据：删空后仍回选章引导）
        localStorage.setItem(`pref.book.${projectId}.ever_planned`, "1");
        const ref = (result.chapter_ref as string) || `${volRef}-ch-${nextCh}`;
        focusNode(ref);
        return ref;
      } catch {
        toast.error("创建章失败");
        return null;
      } finally {
        creatingRef.current = false;
        setCreating(false);
      }
    },
    [projectId, refresh, focusNode],
  );

  // -----------------------------------------------------------------------
  // Rename node
  // -----------------------------------------------------------------------

  const renameNode = useCallback(
    async (nodeId: string, newTitle: string) => {
      if (!projectId) return;
      const parsed = parseRef(nodeId);
      try {
        if (parsed) {
          const data = await api.get(`/novels/${projectId}/chapters/${nodeId}`);
          await api.put(`/novels/${projectId}/chapters/${nodeId}`, {
            ...data,
            title: newTitle,
          });
        } else {
          const volData = await api.get(
            `/novels/${projectId}/volumes/${nodeId}`,
          );
          await api.put(`/novels/${projectId}/volumes/${nodeId}`, {
            ...volData,
            title: newTitle,
          });
        }
        await refresh();
      } catch {
        toast.error("重命名失败");
      }
    },
    [projectId, refresh],
  );

  // -----------------------------------------------------------------------
  // Delete node
  // -----------------------------------------------------------------------

  const deleteNode = useCallback(
    async (nodeId: string) => {
      if (!projectId) return;
      const parsed = parseRef(nodeId);
      try {
        if (parsed) {
          await api.delete(`/novels/${projectId}/chapters/${nodeId}`);
          if (selectedRefRef.current === nodeId) {
            setSelectedId(null);
            setSelectedRef(null);
          }
        } else {
          await api.delete(`/novels/${projectId}/volumes/${nodeId}`);
          if (
            selectedRefRef.current?.startsWith(nodeId) ||
            selectedIdRef.current === nodeId
          ) {
            setSelectedId(null);
            setSelectedRef(null);
          }
        }
        await refresh();
      } catch (e) {
        // 删除失败：透出服务端原因（c-chapter-plan-ai 删章守卫 409 给出口引导——
        // 「只允许删本卷最后一章」「已有正文请走重写/归档」；静默失败＝无引导）
        toast.error((e as Error)?.message || "删除失败，请重试");
      }
    },
    [projectId, refresh],
  );

  return {
    ghosts,
    project,
    volumes,
    selectedId,
    selectedRef,
    view,
    setView,
    viewPayload,
    expandedIds,
    onToggle,
    onSelectNode,
    createVolume,
    createChapter,
    creating,
    renameNode,
    deleteNode,
    refresh,
    focusNode,
    clearSelection,
    selectVolume,
  };
}

export default useWorkbench;
