/** 「文风」页签（chapter-style-shadow，拍板③记章节档案）：
 *  全书基线（style-quant 六行，只读）＋ 本章影子行（可增删改）＋
 *  「AI 建议本章调整」（建议逐条采纳写入影子）。 */
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

interface BaselineRow {
  row: string;
  label: string;
  value: string;
  tolerance?: number | null;
  locked?: boolean;
}
interface ShadowRow {
  value: string;
  reason: string;
}
interface Suggestion {
  row: string;
  value: string;
  reason: string;
}

const DIM_LABEL: Record<string, string> = {
  narrative: "镜头与人称",
  rhythm: "篇幅配比（五层）",
  syntax: "句子与段落",
  lexicon: "修饰密度",
  emotion: "情绪外化",
  dialogue_verb: "对话与动词质感",
};

export function StyleShadowPane({
  projectId,
  chapterRef,
  archived,
  isPro,
}: {
  projectId: string;
  chapterRef: string;
  archived: boolean;
  isPro: boolean;
}) {
  const [baseline, setBaseline] = useState<BaselineRow[]>([]);
  const [confidence, setConfidence] = useState(0);
  const [shadow, setShadow] = useState<Record<string, ShadowRow>>({});
  const [suggestions, setSuggestions] = useState<Suggestion[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = (await api.get(
        `/novels/${projectId}/chapters/${chapterRef}/style-shadow/baseline`,
      )) as {
        baseline: BaselineRow[];
        confidence: number;
        portrait: string;
        shadow: Record<string, ShadowRow>;
      };
      setBaseline(data.baseline ?? []);
      setShadow(data.shadow ?? {});
      setConfidence(data.confidence ?? 0);
      setError(null);
    } catch {
      setError("文风基线加载失败");
    }
  }, [projectId, chapterRef]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const saveShadow = useCallback(
    async (rows: Record<string, ShadowRow>) => {
      setShadow(rows);
      setBusy("save");
      try {
        await api.put(
          `/novels/${projectId}/chapters/${chapterRef}/style-shadow`,
          { rows },
        );
      } catch {
        setError("保存失败，请重试");
      } finally {
        setBusy(null);
      }
    },
    [projectId, chapterRef],
  );

  const suggest = useCallback(async () => {
    setBusy("suggest");
    setError(null);
    try {
      const data = (await api.post(
        `/novels/${projectId}/chapters/${chapterRef}/style-shadow/suggest`,
        {},
      )) as { suggestions: Suggestion[] };
      setSuggestions(data.suggestions ?? []);
    } catch (e) {
      setError((e as Error).message || "建议获取失败");
    } finally {
      setBusy(null);
    }
  }, [projectId, chapterRef]);

  const adopt = useCallback(
    (s: Suggestion) => {
      const rows = { ...shadow, [s.row]: { row: s.row, value: s.value, reason: s.reason } };
      void saveShadow(rows);
      setSuggestions(null);
    },
    [shadow, saveShadow],
  );

  if (!isPro) {
    return (
      <div className="style-shadow" data-od-id="style-shadow-free">
        <p className="ss-lead">本章文风影子</p>
        <p className="ss-note">PRO 可用 · 在全书基线上给本章单独定调</p>
      </div>
    );
  }

  return (
    <div className="style-shadow" data-od-id="style-shadow">
      <p className="ss-lead">全书文风基线（蒸馏产出 · 只读）</p>
      {confidence <= 0 ? (
        <p className="ss-note">
          本书还没有蒸馏基线。先到「设定 · 文风」里完成蒸馏，这里才有可偏离的基线。
        </p>
      ) : (
        <ul className="ss-baseline">
          {baseline.map((b) => (
            <li key={b.row}>
              <span className="k">{b.label}</span>
              <span className="v">{b.value}</span>
            </li>
          ))}
        </ul>
      )}

      <p className="ss-lead">本章影子（覆盖行）</p>
      {Object.keys(shadow).length === 0 && (
        <p className="ss-note">本章没有覆盖行——完全沿用全书基线。</p>
      )}
      {Object.entries(shadow).map(([dim, item]) => (
        <div className="ss-row" key={dim} data-od-id={`shadow-${dim}`}>
          <span className="k">{DIM_LABEL[dim] ?? dim}</span>
          <span className="v">{item.value}</span>
          {item.reason && <span className="r">{item.reason}</span>}
          <button
            className="btn btn-ghost btn-sm"
            disabled={busy === "save"}
            onClick={() => {
              const rows = { ...shadow };
              delete rows[dim];
              void saveShadow(rows);
            }}
          >
            还原
          </button>
        </div>
      ))}

      <p className="ss-lead">AI 建议本章调整</p>
      <button
        className="btn btn-secondary btn-sm"
        data-od-id="style-suggest-btn"
        disabled={busy === "suggest" || archived}
        onClick={() => void suggest()}
      >
        {busy === "suggest" ? "生成中……" : "AI 建议本章调整"}
      </button>
      {suggestions && suggestions.length === 0 && (
        <p className="ss-note">按本章章纲，基线不需要偏离。</p>
      )}
      {suggestions?.map((sg) => (
        <div className="ss-suggestion" key={sg.row} data-od-id={`suggest-${sg.row}`}>
          <span className="k">{DIM_LABEL[sg.row] ?? sg.row}</span>
          <span className="v">{sg.value}</span>
          <span className="r">{sg.reason}</span>
          <button
            className="btn btn-primary btn-sm"
            onClick={() => {
              const rows = {
                ...shadow,
                [sg.row]: { value: sg.value, reason: sg.reason },
              };
              void saveShadow(rows);
            }}
          >
            采纳
          </button>
        </div>
      ))}
      {error && <p className="ss-error">{error}</p>}
    </div>
  );
}
