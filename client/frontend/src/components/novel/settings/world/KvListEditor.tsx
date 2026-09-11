import { Ico, P } from "@/components/icons";

/** 世界名目条目（铁律 / 更多世界细节共用行形状）。 */
export interface KvRow {
  key: string;
  value: string;
  origin?: string;
}

interface KvListEditorProps {
  rows: KvRow[];
  onChange: (rows: KvRow[]) => void;
  /** 常用名目建议：点一下即加一条（已用的自动隐藏）。 */
  suggests?: string[];
  keyPlaceholder?: string;
  valuePlaceholder?: string;
  addLabel?: string;
  maxItems?: number;
  /** 行内输入定位锚（e2e）：默认 kv-row。 */
  rowOdId?: string;
}

/**
 * 名目+内容 条目编辑器（world-setting-v2）。
 *
 * 受控组件：rows 由父级持有；建议名目点选即加一条，名目可改可自定义，
 * 随时增删——不锁死字段（06 更多世界细节 / 05 世界铁律 共用）。
 */
export default function KvListEditor({
  rows,
  onChange,
  suggests = [],
  keyPlaceholder = "名目",
  valuePlaceholder = "一句话写清",
  addLabel = "加一条",
  maxItems,
  rowOdId = "kv-row",
}: KvListEditorProps) {
  const used = new Set(rows.map((r) => r.key.trim()));
  const remaining = suggests.filter((s) => !used.has(s));
  const full = maxItems !== undefined && rows.length >= maxItems;

  const patchRow = (i: number, patch: Partial<KvRow>) => {
    const next = [...rows];
    next[i] = { ...next[i], ...patch };
    onChange(next);
  };

  return (
    <div data-od-id="kv-list-editor">
      {remaining.length > 0 && (
        <div className="cap-row" style={{ marginBottom: 6 }}>
          {remaining.map((s) => (
            <button
              key={s}
              type="button"
              className="cap"
              data-od-id={`kv-suggest-${s}`}
              onClick={() => onChange([...rows, { key: s, value: "" }])}
            >
              {s}
            </button>
          ))}
        </div>
      )}
      {rows.map((row, i) => (
        <div className="kv-row" key={i} data-od-id={`${rowOdId}-${i}`}>
          <input
            className="input kv-key"
            value={row.key}
            maxLength={20}
            placeholder={keyPlaceholder}
            onChange={(e) => patchRow(i, { key: e.target.value })}
          />
          <textarea
            className="textarea kv-val"
            rows={1}
            value={row.value}
            maxLength={200}
            placeholder={valuePlaceholder}
            onChange={(e) => patchRow(i, { value: e.target.value })}
          />
          <button
            className="icon-btn"
            type="button"
            title="删除本条"
            aria-label="删除本条"
            onClick={() => onChange(rows.filter((_, j) => j !== i))}
          >
            <Ico d={P.trash} sw={1.7} />
          </button>
        </div>
      ))}
      {!full && (
        <button
          className="text-btn"
          type="button"
          onClick={() => onChange([...rows, { key: "", value: "" }])}
        >
          <Ico d={P.plus} sw={2} size={13} /> {addLabel}
        </button>
      )}
    </div>
  );
}
