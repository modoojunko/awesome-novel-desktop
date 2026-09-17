// 提示词面板（book.html renderPromptPane 复刻）：panel-head 徽标 + 说明。
// 原型为单 textarea（自动组装/自定义切换）；应用侧真实模型是分段提示词
// 文件（PromptManagementPage 按章过滤渲染）——过渡期原样内嵌（轻重皮），
// PR 5 按设计语言重绘其内部。
// 四期尾：挂「组装来源」六处只读展示（storyline.html src-chips 口径）——
// 数据来自 GET prompt-sources（与写作侧同一套组装链的投影）。
import { useEffect, useState } from "react";
import PromptManagementPage from "../PromptManagementPage";
import { fetchPromptSources, type PromptSourcesResult } from "@/lib/promptSources";

interface PromptPaneProps {
  projectId: string;
  chapterRef: string;
  title: string;
  /** 是否已有自定义提示词文件（能力探测，403/404/空都算无） */
  hasPrompts: boolean | null;
}

const fmt = (n: number) => n.toLocaleString("zh-CN");

export default function PromptPane({
  projectId,
  chapterRef,
  title,
  hasPrompts,
}: PromptPaneProps) {
  const custom = !!hasPrompts;
  const [sources, setSources] = useState<PromptSourcesResult | null>(null);

  useEffect(() => {
    let cancelled = false;
    setSources(null);
    fetchPromptSources(projectId, chapterRef)
      .then((d) => {
        if (!cancelled) setSources(d);
      })
      .catch(() => {
        /* 展示型数据：失败静默缺省（不打断提示词编辑主流程） */
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, chapterRef]);

  return (
    <div className="prompt-pane">
      <div className="panel">
        <div className="panel-head">
          <h2>提示词 · {title}</h2>
          {custom ? (
            <span className="badge warn">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
                <circle cx="12" cy="12" r="5" fill="currentColor" stroke="none" />
              </svg>
              已自定义
            </span>
          ) : (
            <span className="badge ok">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
                <path d="M5 13l4 4L19 7" />
              </svg>
              自动组装
            </span>
          )}
        </div>
        <p className="desc">
          AI 生成正文时使用的提示词，由「设定 + 章纲」自动组装。编辑后保存，本章将以自定义提示词为准。
        </p>

        {sources && (
          <div className="psrc" data-od-id="prompt-sources" data-testid="prompt-sources">
            <ul className="psrc-stats">
              <li>
                <span className="k">组装来源</span>
                <span className="v num">{sources.sources.length} 处</span>
              </li>
              <li>
                <span className="k">来源字数</span>
                <span className="v num">{fmt(sources.total_chars)} 字</span>
              </li>
              <li>
                <span className="k">涉及角色</span>
                <span className="v num">{sources.cast_count} 人</span>
              </li>
            </ul>
            <div className="src-chips">
              <em>组装来源</em>
              {sources.sources.map((s) => (
                <span className="chip" key={s.key} title={s.preview || "（未填）"}>
                  {s.label}
                  {s.empty ? " · 未填" : ""}
                </span>
              ))}
            </div>
            <ul className="psrc-list">
              {sources.sources.map((s) => (
                <li key={s.key} className={s.empty ? "empty" : ""}>
                  <span className="k">{s.label}</span>
                  <span className="v">
                    {s.empty ? "（未填 · 不参与组装）" : s.preview}
                  </span>
                  <span className="n num">{s.chars ? `${fmt(s.chars)} 字` : ""}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="prompt-body">
          <PromptManagementPage projectId={projectId} chapterRef={chapterRef} />
        </div>
      </div>
    </div>
  );
}
