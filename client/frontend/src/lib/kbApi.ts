// 写作知识库 API（c-knowledge-base）：账号级知识条目/库，信封 {ok, data} 同源。
import { request } from "./api";
import { getToken } from "./auth";
import { getApiBaseUrl } from "./env";

export interface KbEntry {
  id: string;
  genre: string;
  concept: string;
  concept_id: string;
  title: string;
  instruction: string;
  payload: Record<string, unknown>;
  example: string;
  negative_example: string;
  when: Record<string, string>;
  evidence: string;
  definition?: string;
  schema_json?: string;
  when_text?: string;
  version?: number;
  origin?: string;
  archived_at?: string | null;  /** 乐观并发版本号（PATCH 带 rev 不一致 409） */
  rev: number;
  src_kind: string;
  src_novel_name: string;
  created_at: string;
  updated_at: string;
  /** 层（c-kb-baseline 批B）：「官方精选」随层派生，不落 kb_entries */
  layer?: "user" | "baseline";
  /** 基线业务键（overlay join／官方新版比对用） */
  src_key?: string;
  /** merged 文本来自用户副本（写时复制） */
  overlaid?: boolean;
  /** 双哈希：副本基线落后于官方新版＝显示「官方有新版」 */
  official_update?: boolean;
  /** 角色设定条目是否有头像字节（有→出图，无→姓氏 SVG 占位） */
  has_avatar?: boolean;
  /** 被用户隐藏（只出现在「已隐藏」筛选，可恢复默认） */
  hidden?: boolean;
}

export interface KbLibrary {
  id: string;
  genre: string;
  concept: string;
  name: string;
  purpose: string;
  contract: string;
  enabled: boolean;
  /** 成员条目数（含场景条目） */
  entry_count?: number;
  /** 几本书启用（跨书计数） */
  bound_novels?: number;
  /** 本书是否已启用（带 novel_id 查询时返回） */
  bound_in_book?: number;
}

export interface KbBinding {
  id: string;
  novel_id: string;
  library_id: string;
  enabled: boolean;
  genre: string;
  concept: string;
  library_name: string;
  member_count: number;
  /** 场景条目数（不进快照，逐章挑） */
  scene_count: number;
  /** 库有更新：新增/移除条目数（显式同步前累积） */
  added: number;
  removed: number;
  library_missing: boolean;
  synced_at: string;
}

export interface KbBindResult {
  binding_id: string;
  library_id: string;
  genre: string;
  concept: string;
  library_name: string;
  member_count: number;
  /** 逐键落库计数（style.role / world.stage ...） */
  landed: Record<string, number>;
  /** 互斥替换掉的同格绑定数 */
  replaced_bindings: number;
}

export interface KbGenreCount {
  name: string;
  count: number;
  key?: string;
}

export interface KbConceptMeta {
  name: string;
  fields: { key: string; required: boolean; max_length: number | null }[];
  readonly: boolean;
}

// ── 知识整理（c-kb-organize 批D）──

export interface KbOrganizeStatus {
  genre: string;
  running: boolean;
  last_run: null | {
    id: string;
    status: string;
    started_at: string;
    finished_at: string;
    entries_scanned: number;
    relations_added: number;
    error: string;
  };
  pending_relations: number;
  proposed_findings: number;
}

export interface KbPendingRelation {
  id: string;
  rel_type: string;
  from_id: string;
  to_id: string;
  from_title: string;
  to_title: string;
  confidence: number;
  note: string;
  evidence: string;
}

export interface KbPendingFinding {
  id: string;
  kind: "merge" | "reclass" | "subconcept" | "quality";
  subject_id: string;
  subject2_id: string;
  subject_title: string;
  payload: Record<string, unknown>;
}

export interface KbGraphEntryNode {
  id: string;
  title: string;
  concept: string;
  instruction: string;
}

export interface KbGraphEntryEdge {
  rel_type: string;
  from_id: string;
  to_id: string;
  confidence: number;
  note: string;
  evidence: string;
}

// request() 自带 /api 前缀，这里只给功能段（同 libraryApi 的 /character-library 口径）
const BASE = "/kb";

// ── 跨知识实例行（c-kb-instance-list）：row_kind 判别联合，归属链由后端拼好 ──

export interface KbChainSeg {
  id: string;
  title: string;
}

/** 行公共形状：material 行的 knowledge_id/knowledge_title/chain 为空值。 */
interface KbInstanceFlatRowBase {
  id: string;
  knowledge_id: string;
  knowledge_title: string;
  chain: KbChainSeg[];
  genre: string;
  concept: string;
  text: string;
  quote: string;
  source_novel: string;
  source_chapter: string;
  /** 后端归一为「拆书/手录」两个界面值 */
  src_kind: "拆书" | "手录";
  created_at: string;
}

export interface KbInstanceRow extends KbInstanceFlatRowBase {
  row_kind: "instance";
  /** 实例字段值（{字段名: 值} 的 JSON 串）——实例详情抽屉直接渲染，不重取 */
  fields_json: string;
  /** 实例名：角色实例＝角色名；其余概念空串（前端以正文兜底） */
  name: string;
}

export interface KbMaterialRow extends KbInstanceFlatRowBase {
  row_kind: "material";
}

export type KbInstanceFlatRow = KbInstanceRow | KbMaterialRow;

// 后端各端点统一 {ok: true, data: ...} 信封（同 libraryApi 口径）
async function unwrap<T>(p: Promise<unknown>): Promise<T> {
  const r = (await p) as { data?: T };
  if (!r || r.data === undefined) throw new Error("响应缺少 data");
  return r.data as T;
}

export const kbApi = {
  genres: () =>
    unwrap<KbGenreCount[]>(request(`${BASE}/genres`)),

  // ── 跨知识实例行列表（c-kb-instance-list）──

  instancesFlat: (params: { genre?: string; concept?: string; q?: string }) => {
    const sp = new URLSearchParams();
    if (params.genre) sp.set("genre", params.genre);
    if (params.concept) sp.set("concept", params.concept);
    if (params.q) sp.set("q", params.q);
    return unwrap<{ ok: boolean; rows: KbInstanceFlatRow[] }>(request(`${BASE}/instances?${sp}`));
  },

  entries: (params: { genre?: string; concept?: string; src?: string; q?: string; cursor?: string }) => {
    const sp = new URLSearchParams();
    if (params.genre) sp.set("genre", params.genre);
    if (params.concept) sp.set("concept", params.concept);
    if (params.src) sp.set("src", params.src);
    if (params.q) sp.set("q", params.q);
    if (params.cursor) sp.set("cursor", params.cursor);
    return unwrap<{ entries: KbEntry[]; next_cursor: string }>(request(`${BASE}/entries?${sp}`));
  },

  entry: (id: string) =>
    unwrap<KbEntry>(request(`${BASE}/entries/${id}`)),

  libraries: (genre?: string, novelId?: string) => {
    const sp = new URLSearchParams();
    if (genre) sp.set("genre", genre);
    if (novelId) sp.set("novel_id", novelId);
    const qs = sp.toString();
    return unwrap<KbLibrary[]>(request(`${BASE}/libraries${qs ? `?${qs}` : ""}`));
  },

  concepts: () =>
    unwrap<{ concepts: KbConceptMeta[]; themes: string[] }>(request(`${BASE}/concepts`)),

  // ── 书内绑定（c-kb-snapshot：启用落设定）──

  bind: (novelId: string, libraryId: string) =>
    unwrap<KbBindResult>(request(`${BASE}/bindings`, {
      method: "POST",
      body: JSON.stringify({ novel_id: novelId, library_id: libraryId }),
    })),

  bindings: (novelId: string) =>
    unwrap<KbBinding[]>(request(`${BASE}/bindings?novel_id=${encodeURIComponent(novelId)}`)),

  syncBinding: (bindingId: string) =>
    unwrap<{ member_count: number; landed: Record<string, number> }>(
      request(`${BASE}/bindings/${bindingId}/sync`, { method: "POST" }),
    ),

  unbind: (bindingId: string, novelId: string) =>
    unwrap<{ unbound: string }>(
      request(`${BASE}/bindings/${bindingId}?novel_id=${encodeURIComponent(novelId)}`, { method: "DELETE" }),
    ),

  createEntry: (body: {
    genre: string;
    concept: string;
    concept_id?: string;
    title?: string;
    payload?: Record<string, unknown>;
    instruction?: string;
    example?: string;
    negative_example?: string;
    when_json?: Record<string, string>;
  }) =>
    unwrap<KbEntry>(request(`${BASE}/entries`, {
      method: "POST",
      body: JSON.stringify(body),
    })),

  /** 编辑条目（c-kb-character-migration 刀2a）：闸门复用＋rev 乐观并发 */
  updateEntry: (
    entryId: string,
    body: {
      rev?: number;
      title?: string;
      instruction?: string;
      payload?: Record<string, unknown>;
      example?: string;
      negative_example?: string;
      when_json?: Record<string, string>;
    },
  ) =>
    unwrap<KbEntry>(request(`${BASE}/entries/${entryId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    })),

  /** 归档（写 archived_at，可恢复） */
  archiveEntry: (entryId: string) =>
    unwrap<{ ok: boolean; entry_id: string }>(
      request(`${BASE}/entries/${entryId}/archive`, { method: "POST" }),
    ),
  /** 恢复归档知识 */
  restoreEntry: (entryId: string) =>
    unwrap<{ ok: boolean; entry_id: string }>(
      request(`${BASE}/entries/${entryId}/restore`, { method: "POST" }),
    ),
  /** 实例列表 */
  listInstances: (entryId: string) =>
    unwrap<{ ok: boolean; instances: { id: string; text: string; source_kind: string; source_novel: string; source_chapter: string; quote: string; fields_json: string; sort: number }[] }>(
      request(`${BASE}/entries/${entryId}/instances`),
    ),
  /** 添加实例 */
  addInstance: (entryId: string, body: { text?: string; source_kind?: string; source_novel?: string; source_chapter?: string; quote?: string; sort?: number }) =>
    unwrap<{ ok: boolean; instance: { id: string; text: string } }>(
      request(`${BASE}/entries/${entryId}/instances`, { method: "POST", body: JSON.stringify(body), headers: { "Content-Type": "application/json" } }),
    ),
  /** 删条目＝软删（archived；列表/快照/全局图只出 active） */
  deleteEntry: (entryId: string) =>
    unwrap<{ deleted: string }>(request(`${BASE}/entries/${entryId}`, { method: "DELETE" })),

  /** 用作原型计数回写（c-kb-character）：KbPref.adopt_count 累加 */
  usePrototype: (entryId: string) =>
    unwrap<{ entry_id: string; adopt_count: number }>(
      request(`${BASE}/entries/${entryId}/prototype-use`, { method: "POST" }),
    ),

  // ── 全局图（c-kb-organize 批7：聚合＋下钻；关系边随 AI 整理二阶段）──

  graphAggregate: () =>
    unwrap<{
      nodes: { id: string; kind: "genre" | "cell"; genre: string; concept: string; count: number }[];
      links: { source: string; target: string }[];
    }>(request(`${BASE}/graph/aggregate`)),

  graphCell: (genre: string, concept: string) => {
    const sp = new URLSearchParams({ genre, concept });
    return unwrap<{
      nodes: { id: string; kind: "entry"; genre: string; concept: string; title: string; scope: string }[];
    }>(request(`${BASE}/graph/cell?${sp}`));
  },

  // ── 知识整理（c-kb-organize 批D）：方法挂 kbApi.organize 命名空间 ──

  organize: {
    run: (genre: string, full = false) =>
      unwrap<{ skipped?: boolean; message?: string; status?: string; relations_added?: number }>(
        request(`${BASE}/organize/run`, {
          method: "POST",
          body: JSON.stringify({ genre, full }),
        }),
      ),

    status: (genre: string) =>
      unwrap<KbOrganizeStatus>(request(`${BASE}/organize/status?genre=${encodeURIComponent(genre)}`)),

    findings: (genre: string) =>
      unwrap<{ relations: KbPendingRelation[]; findings: KbPendingFinding[]; counts: { relations: number; findings: number } }>(
        request(`${BASE}/organize/findings?genre=${encodeURIComponent(genre)}`),
      ),

    adoptFinding: (findingId: string) =>
      unwrap<{ message: string }>(
        request(`${BASE}/organize/findings/${findingId}/adopt`, { method: "POST" }),
      ),

    ignoreFinding: (findingId: string) =>
      unwrap<{ message: string }>(
        request(`${BASE}/organize/findings/${findingId}/ignore`, { method: "POST" }),
      ),

    adoptRelation: (relationId: string) =>
      unwrap<{ message: string }>(
        request(`${BASE}/relations/${relationId}/adopt`, { method: "POST" }),
      ),

    rejectRelation: (relationId: string) =>
      unwrap<{ message: string }>(
        request(`${BASE}/relations/${relationId}/reject`, { method: "POST" }),
      ),

    relationFeedback: (relationId: string) =>
      unwrap<{ message: string }>(
        request(`${BASE}/relations/${relationId}/feedback`, { method: "POST" }),
      ),

    graphEntries: (genre: string) =>
      unwrap<{ genre: string; nodes: KbGraphEntryNode[]; edges: KbGraphEntryEdge[]; edge_count: number; edge_truncated: number }>(
        request(`${BASE}/graph/entries?genre=${encodeURIComponent(genre)}`),
      ),

    entryRelations: (entryId: string, opts?: { status?: "all" | "active" }) =>
      unwrap<{ relations: { id: string; rel_type: string; status: string; direction: string; other_id: string; other_title: string; confidence: number; note: string; evidence: string }[]; merged_into: null | { surviving_id: string; title: string } }>(
        request(`${BASE}/entries/${entryId}/relations${opts?.status ? `?status=${opts.status}` : ""}`),
      ),
  },
  summarize: {
    run: (genre: string) =>
      unwrap<{ collected: number; knowledge: number; genre: string; skipped?: boolean; message?: string }>(
        request(`${BASE}/summarize/run`, { method: "POST", body: JSON.stringify({ genre }), headers: { "Content-Type": "application/json" } }),
      ),
    status: () =>
      unwrap<{ materials_by_genre: Record<string, number>; threshold: number }>(
        request(`${BASE}/summarize/status`),
      ),
  },
  graphTree: (genre: string) =>
    unwrap<{ roots: { id: string; kind: string; genre: string; concept: string; children: unknown[] }[]; rel_edges: { source: string; target: string; rel_type: string }[] }>(
      request(`${BASE}/graph/tree?genre=${encodeURIComponent(genre)}`),
    ),
  /** 有用/没用回写（c-kb-write-block 批D）：账号级权重，可重复调用＝可改口 */
  pref: (entryId: string, useful: boolean) =>
    unwrap<{ entry_id: string; adopt_count: number; drop_count: number; useful_rate: number }>(
      request(`${BASE}/entries/${encodeURIComponent(entryId)}/pref`, {
        method: "POST",
        body: JSON.stringify({ useful }),
      }),
    ),

  // ── 官方精选覆盖（c-kb-baseline 批B）：写时复制，只写用户层 ──

  /** 隐藏／存副本（edit 需要 instruction；隐藏传空即可） */
  baselineOverride: (entryId: string, action: "hide" | "edit", instruction = "") =>
    unwrap<{ entry_id: string; action: string }>(
      request(`${BASE}/entries/${encodeURIComponent(entryId)}/baseline-override`, {
        method: "PUT",
        body: JSON.stringify({ action, instruction }),
      }),
    ),

  // ── 官方精选同步（c-kb-baseline）：启动补偿失败后的重试面 ──

  baselineStatus: () =>
    unwrap<{ version: number; entries: number }>(request(`${BASE}/baseline/status`)),

  baselineSync: () =>
    unwrap<{ status: string; version?: number; reason?: string }>(
      request(`${BASE}/baseline/sync`, { method: "POST" }),
    ),

  /** 恢复默认／恢复官方版：删覆盖记录，原件重新透出 */
  clearBaselineOverride: (entryId: string) =>
    unwrap<{ entry_id: string; restored: boolean }>(
      request(`${BASE}/entries/${encodeURIComponent(entryId)}/baseline-override`, {
        method: "DELETE",
      }),
    ),
  /** 书级知识副本（c-kb-book-scope）：存量书补平＋「库有 N 条新增」差异计数 */
  bookScopeImport: (novelId: string) =>
    unwrap<{ imported: number; skipped: number }>(
      request(`${BASE}/book-scope/import`, {
        method: "POST",
        body: JSON.stringify({ novel_id: novelId }),
      }),
    ),
  bookScopeDiff: (novelId: string) =>
    unwrap<{ new_count: number; declined: boolean }>(
      request(`${BASE}/book-scope/diff?novel_id=${encodeURIComponent(novelId)}`),
    ),

  /** 「我自己设定」：落 declined 标记，设定页不再自动弹导入弹窗（可再改口） */
  bookScopeDecline: (novelId: string, declined = true) =>
    unwrap<{ declined: boolean }>(
      request(`${BASE}/book-scope/decline`, {
        method: "POST",
        body: JSON.stringify({ novel_id: novelId, declined }),
      }),
    ),

  /** 题材知识导入进度流（弹窗二选一）：逐概念组 SSE 进度，返回 AbortController。 */
  bookScopeImportStream: (
    novelId: string,
    onEvent: (ev: BookScopeProgressEvent) => void,
  ): AbortController => {
    const controller = new AbortController();
    const token = getToken();
    fetch(`${getApiBaseUrl()}/api${BASE}/book-scope/import/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ novel_id: novelId }),
      signal: controller.signal,
    })
      .then(async (res) => {
        if (!res.ok) {
          const err = await res.json().catch(() => null);
          onEvent({
            type: "error",
            message:
              (typeof err?.detail === "string" && err.detail) ||
              `导入失败（HTTP ${res.status}）`,
          });
          return;
        }
        const reader = res.body?.getReader();
        if (!reader) {
          onEvent({ type: "error", message: "无法读取响应流" });
          return;
        }
        const decoder = new TextDecoder();
        let buffer = "";
        // 终态事件（done/error）是否出现过：流干净结束却未见终态＝服务端异常中止
        // （同 ai.ts sawTerminal 口径，c-prose-stream-silent-hang）——必须按失败收尾，
        // 否则弹窗停在最后的进度上，作家只能自己点取消
        let sawTerminal = false;
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";
          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            try {
              const ev = JSON.parse(line.slice(6)) as BookScopeProgressEvent;
              if (ev.type === "done" || ev.type === "error") sawTerminal = true;
              onEvent(ev);
            } catch {
              // 跳过坏行（同 ai.ts 流解析口径）
            }
          }
        }
        if (!sawTerminal) {
          onEvent({
            type: "error",
            message: "导入中断：未收到完成信号（可能被中断或服务异常），请重试",
          });
        }
      })
      .catch((e) => {
        if ((e as Error)?.name === "AbortError") return;
        onEvent({ type: "error", message: (e as Error)?.message || "网络错误" });
      });
    return controller;
  },
};

/** 题材知识导入进度事件（c-kb-book-scope 弹窗进度条）。 */
export interface BookScopeProgressEvent {
  type: "phase" | "done" | "error";
  /** copy=逐概念组复制；baseline=落基线设定 */
  phase?: string;
  concept?: string;
  done?: number;
  total?: number;
  imported?: number;
  skipped?: number;
  message?: string;
}
