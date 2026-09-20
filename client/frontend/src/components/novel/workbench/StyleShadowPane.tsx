/** 「文风」页签（chapter-style-shadow，拍板③记章节档案）：
 *  全书基线（style-quant 六行，只读）＋ 本章影子行（手工增/改/还原，免费可用）
 *  ＋ AI 建议结果区（右栏 AI 助手触发拉取，建议逐条采纳写入影子；
 *  2026-09-20 AI 入口收口右栏，页签内只留结果与采纳）。 */
import { useCallback, useEffect, useRef, useState } from "react";
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
  suggestSignal = 0,
}: {
  projectId: string;
  chapterRef: string;
  archived: boolean;
  /** 右栏「AI 建议本章调整」触发信号（计数器递增；0=初始不触发） */
  suggestSignal?: number;
}) {
  const [baseline, setBaseline] = useState<BaselineRow[]>([]);
  const [confidence, setConfidence] = useState(0);
  const [shadow, setShadow] = useState<Record<string, ShadowRow>>({});
  const [suggestions, setSuggestions] = useState<Suggestion[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const busyRef = useRef(false);
  const [error, setError] = useState<string | null>(null);
  // 手工添加覆盖行（免费可用的手工编辑面）
  const [newDim, setNewDim] = useState("");
  const [newValue, setNewValue] = useState("");
  const [newReason, setNewReason] = useState("");

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
    if (busyRef.current) return;
    busyRef.current = true;
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
      busyRef.current = false;
      setBusy(null);
    }
  }, [projectId, chapterRef]);

  // 右栏信号触发拉取（重复点击由 busyRef 挡住；重挂载信号未变不重拉）
  const mountedRef = useRef(false);
  useEffect(() => {
    if (!mountedRef.current) {
      mountedRef.current = true;
      return;
    }
    if (suggestSignal) void suggest();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [suggestSignal]);

  const adopt = useCallback(
    (s: Suggestion) => {
      const rows = { ...shadow, [s.row]: { row: s.row, value: s.value, reason: s.reason } };
      void saveShadow(rows);
      setSuggestions(null);
    },
    [shadow, saveShadow],
  );

  const locked = archived || busy === "save";
  const remainingDims = Object.keys(DIM_LABEL).filter((d) => !(d in shadow));

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

      <p className="ss-lead">本章影子（覆盖行 · 只影响本章）</p>
      {Object.keys(shadow).length === 0 && (
        <p className="ss-note">本章没有覆盖行——完全沿用全书基线。</p>
      )}
      {Object.entries(shadow).map(([dim, item]) => (
        <div className="ss-row" key={dim} data-od-id={`shadow-${dim}`}>
          <span className="k">{DIM_LABEL[dim] ?? dim}</span>
          <input
            className="input v"
            data-testid={`shadow-value-${dim}`}
            placeholder="本章取值"
            value={item.value}
            disabled={locked}
            onChange={(e) =>
              setShadow((s) => ({ ...s, [dim]: { ...item, value: e.target.value } }))
            }
            onBlur={(e) =>
              void saveShadow({ ...shadow, [dim]: { ...item, value: e.target.value } })
            }
          />
          <input
            className="input r"
            data-testid={`shadow-reason-${dim}`}
            placeholder="理由（可空）"
            value={item.reason}
            disabled={locked}
            onChange={(e) =>
              setShadow((s) => ({ ...s, [dim]: { ...item, reason: e.target.value } }))
            }
            onBlur={(e) =>
              void saveShadow({ ...shadow, [dim]: { ...item, reason: e.target.value } })
            }
          />
          <button
            className="btn btn-ghost btn-sm"
            disabled={locked}
            data-testid={`shadow-reset-${dim}`}
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

      {remainingDims.length > 0 && (
        <div className="ss-add" data-testid="shadow-add">
          <select
            className="input"
            value={newDim}
            disabled={locked}
            onChange={(e) => setNewDim(e.target.value)}
          >
            <option value="">选择参数行</option>
            {remainingDims.map((d) => (
              <option key={d} value={d}>
                {DIM_LABEL[d]}
              </option>
            ))}
          </select>
          <input
            className="input"
            data-testid="shadow-add-value"
            placeholder="本章取值"
            value={newValue}
            disabled={locked}
            onChange={(e) => setNewValue(e.target.value)}
          />
          <input
            className="input"
            data-testid="shadow-add-reason"
            placeholder="理由（可空）"
            value={newReason}
            disabled={locked}
            onChange={(e) => setNewReason(e.target.value)}
          />
          <button
            className="btn btn-secondary btn-sm"
            data-testid="shadow-add-btn"
            disabled={locked || !newDim || !newValue.trim()}
            onClick={() => {
              void saveShadow({
                ...shadow,
                [newDim]: { value: newValue.trim(), reason: newReason.trim() },
              });
              setNewDim("");
              setNewValue("");
              setNewReason("");
            }}
          >
            添加
          </button>
        </div>
      )}

      {/* AI 建议结果区：入口在右栏 AI 助手（PRO 门控在此），页签内逐项采纳 */}
      {(busy === "suggest" || suggestions !== null) && (
        <>
          <p className="ss-lead">AI 建议本章调整</p>
          {busy === "suggest" && <p className="ss-note">建议生成中……</p>}
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
        </>
      )}
      {error && <p className="ss-error">{error}</p>}
    </div>
  );
}
