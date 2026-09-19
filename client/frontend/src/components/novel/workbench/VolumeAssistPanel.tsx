/** 右栏「AI 辅助 · 卷」语境面板（storyline aiVolHTML 复刻）：随卷页签切换引导语＋统计卡。
 *  卷域 AI 动作另行立项——不渲染动作清单、无「规划中」占位（workbench delta 口径）。
 *  rels/hooks 统计按页签懒取，失败降级「—」（与章模式统计降级同口径）。 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { parseChapterRef } from "@/lib/chapterRef";
import type { VolumeRailData } from "./VolumeWorkspace";

export type { VolumeRailData };

const TAB_NAME = {
  outline: "卷纲",
  chapters: "本卷章节",
  rels: "角色关系",
  hooks: "伏笔",
} as const;

export function VolumeAssistPanel({
  projectId,
  data,
}: {
  projectId: string;
  data: VolumeRailData | null;
}) {
  if (!data || !data.detail) {
    return (
      <div>
        <p className="progress-head">AI 辅助 · 卷</p>
        <p className="ai-sec">
          在左侧目录里选中一卷，这里会给出对应页签的卷语境：卷纲、本卷章节、关系与伏笔的统计。
        </p>
      </div>
    );
  }
  // key 换卷/换页签即重挂：懒取统计随页签刷新
  return <PanelBody key={`${data.volume}-${data.tab}`} projectId={projectId} data={data} />;
}

function PanelBody({ projectId, data }: { projectId: string; data: VolumeRailData }) {
  const { tab, detail } = data;
  const lead =
    tab === "outline"
      ? "卷纲只定剧情走向——核心矛盾、目标、关键节点与伏笔；角色的具体言行交给角色设定推导。"
      : tab === "chapters"
        ? `本卷共 ${detail.chapters.length} 章；缺章纲的章节会直接影响 AI 生成的稳定性。`
        : tab === "rels"
          ? "关系图是本卷章节写完后向上回写的结果，卷纲本身不改动。"
          : "本卷该埋与该收的伏笔；跨卷悬置的会继续挂在全书台账上。";

  let stats: Array<[string, string]> = [];
  if (tab === "outline") {
    stats = [
      ["章数目标", detail.chapter_target != null ? `${detail.chapter_target} 章` : "不设"],
      ["已写章节", `${detail.chapters.length} 章`],
      ["关键节点", `${detail.plot_nodes.length} 个`],
      ["登场人物", `${detail.cast_members.length} 人`],
    ];
  } else if (tab === "chapters") {
    const archived = detail.chapters.filter((c) => c.archived).length;
    const draft = detail.chapters.filter((c) => c.has_prose && !c.archived).length;
    const planned = detail.chapters.filter((c) => !c.has_prose && !c.archived).length;
    const need = detail.chapters.filter((c) => c.outline_status !== "confirmed").length;
    stats = [
      ["章节总数", `${detail.chapters.length} 章`],
      ["已归档", `${archived} 章`],
      ["草稿 / 拟定", `${draft} / ${planned}`],
      ["缺章纲", `${need} 章`],
    ];
  }

  return (
    <div>
      <p className="progress-head">AI 辅助 · {TAB_NAME[tab]}</p>
      <div className="rail-assist">
        <p className="ai-sec">{lead}</p>
        {tab === "outline" || tab === "chapters" ? (
          <ul className="rail-stats" data-testid="volume-rail-stats">
            {stats.map(([k, v]) => (
              <li key={k}>
                <span className="k">{k}</span>
                <span className="v">{v}</span>
              </li>
            ))}
          </ul>
        ) : null}
        {tab === "rels" && <RelStats projectId={projectId} volume={data.volume} />}
        {tab === "hooks" && <HookStats projectId={projectId} volume={data.volume} />}
      </div>
    </div>
  );
}

function StatList({ rows }: { rows: Array<[string, string]> | null }) {
  return (
    <ul className="rail-stats" data-testid="volume-rail-stats">
      {(rows ?? []).map(([k, v]) => (
        <li key={k}>
          <span className="k">{k}</span>
          <span className="v">{v}</span>
        </li>
      ))}
    </ul>
  );
}

/** 角色关系页签统计：本卷关系边 / 涉及人物与势力 / 全书关系边（懒取，失败「—」）。 */
function RelStats({ projectId, volume }: { projectId: string; volume: number }) {
  const [rows, setRows] = useState<Array<[string, string]> | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const d = (await api.get(
          `/novels/${projectId}/characters/graph`,
        )) as {
          ok: boolean;
          data: {
            nodes: Array<{ name: string }>;
            edges: Array<{
              owner_name: string;
              other_name: string;
              origin_chapter: string;
            }>;
          };
        };
        const edges = d.data?.edges ?? [];
        const inVol = edges.filter((e) => {
          const p = parseChapterRef(e.origin_chapter || "");
          return p != null && p.vol === volume;
        });
        const names = new Set<string>();
        inVol.forEach((e) => {
          names.add(e.owner_name);
          names.add(e.other_name);
        });
        if (alive) {
          setRows([
            ["本卷关系边", `${inVol.length} 条`],
            ["涉及人物与势力", `${names.size} 个`],
            ["全书关系边", `${edges.length} 条`],
          ]);
        }
      } catch {
        if (alive) setFailed(true);
      }
    })();
    return () => {
      alive = false;
    };
  }, [projectId, volume]);

  if (failed) {
    return (
      <StatList
        rows={[
          ["本卷关系边", "—"],
          ["涉及人物与势力", "—"],
          ["全书关系边", "—"],
        ]}
      />
    );
  }
  return <StatList rows={rows} />;
}

interface HookRow {
  id: string;
  status: string;
  introduced_chapter_id: string | null;
  resolved_chapter_id: string | null;
}

/** 伏笔页签统计：本卷埋下 / 本卷悬置 / 本卷回收 / 全书悬置（懒取，失败「—」）。 */
function HookStats({ projectId, volume }: { projectId: string; volume: number }) {
  const [rows, setRows] = useState<Array<[string, string]> | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const d = (await api.get(`/novels/${projectId}/hooks`)) as {
          data?: { items?: HookRow[] };
          items?: HookRow[];
        };
        const hooks = d.data?.items ?? d.items ?? [];
        const tree = (await api.get(`/novels/${projectId}/volumes`)) as Array<{
          chapters?: Array<{ id?: string; ref?: string; chapter: number }>;
        }>;
        // 章 id → 卷号（伏笔只挂 id，卷归属经章解析）
        const volOf = new Map<string, number>();
        for (const v of tree ?? []) {
          for (const c of v.chapters ?? []) {
            const p = parseChapterRef(c.ref ?? "");
            if (c.id && p) volOf.set(c.id, p.vol);
          }
        }
        const volOfId = (id: string | null | undefined): number | null => {
          if (!id) return null;
          const v = volOf.get(id);
          return v == null ? null : v;
        };
        const plantedVol = (h: HookRow): number | null =>
          volOfId(h.introduced_chapter_id) ?? 0;
        const resolvedVol = (h: HookRow): number | null =>
          volOfId(h.resolved_chapter_id);
        const plantedHere = hooks.filter((h) => plantedVol(h) === volume).length;
        const openHere = hooks.filter(
          (h) => h.status === "active" && plantedVol(h) === volume,
        ).length;
        const resolvedHere = hooks.filter((h) => resolvedVol(h) === volume).length;
        const openAll = hooks.filter((h) => h.status === "active").length;
        if (alive) {
          setRows([
            ["本卷埋下", `${plantedHere} 条`],
            ["本卷悬置", `${openHere} 条`],
            ["本卷回收", `${resolvedHere} 条`],
            ["全书悬置", `${openAll} 条`],
          ]);
        }
      } catch {
        if (alive) setFailed(true);
      }
    })();
    return () => {
      alive = false;
    };
  }, [projectId, volume]);

  if (failed) {
    return (
      <StatList
        rows={[
          ["本卷埋下", "—"],
          ["本卷悬置", "—"],
          ["本卷回收", "—"],
          ["全书悬置", "—"],
        ]}
      />
    );
  }
  return <StatList rows={rows} />;
}
