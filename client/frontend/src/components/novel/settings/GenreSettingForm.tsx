// ── GenreSettingForm ──────────────────────────────────────────────────────
// 题材设定面板（genre-signup-redesign tasks 4.1 / D18·D19 新契约）：
//   六格 = 01 口味胶囊（预置联动，不落库/不计入判据）+ 02 主要看什么
//   + 03 绝对禁止 + 04 吃苦指数 + 05 主线战场 + 06 剧情轨道。
//   每格 = 编号 + 怎么填（m-why）+ 成书视角去处（m-use）。
//
// 存储契约（对外五字段 JSON，后端关系化落 4 张表）：
//   02 → core_promise(≤60) + promise_note(≤200，AI 补充、不单独成行)
//   03 → forbidden_list[{tagId|text}]   04 → cost_ratio(1-10)
//   05 → battlefield[]（tagId 或自定义文本）  06 → track(≤300)
// 空值统一："" / 空白 / [] / null 等价未填（后端 Pydantic + CHECK 同口径）。
// AI 反馈落各格下方 .ai-sink（tasks 4.2），采纳才写回控件。

import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "@/lib/toast";
import { useDirtyState } from "@/hooks/useDirtyState";
import { genreAi, aiBlockReason, type GenreAiField } from "@/lib/ai";
import AiSink from "./AiSink";
import { type SettingSaveHandle } from "./FormField";
import {
  GENRE_FLAVORS,
  GENRE_LIMITS,
  GENRE_VOCAB,
  costSentence,
  vocabLabel,
  type VocabKind,
} from "@/lib/genreVocab";

// ── Props / Handle ───────────────────────────────────────────────────────

interface GenreSettingFormProps {
  projectId: string;
  settingKey: string;
  onDirtyChange?: (dirty: boolean) => void;
  /** 本书书名——题材 AI 入参 title 的来源。 */
  novelName?: string;
}

/** 题材面板句柄：save 落库；runAi 由右栏 AI 卡片调用（tasks 4.2）。 */
export type GenreHandle = SettingSaveHandle & {
  /** 运行某格 AI，结果落该格下方 .ai-sink。 */
  runAi: (field: GenreAiField) => Promise<void>;
};

export type { GenreAiField };

export const GENRE_AI_FIELDS: GenreAiField[] = [
  "core_promise",
  "forbidden_list",
  "cost_ratio",
  "battlefield",
  "track",
];

/** 五行 AI 的字段 → 结果区标题（原型 ZONE_LABEL 同文案）。 */
const AI_LABEL: Record<GenreAiField, string> = {
  core_promise: "AI 填 · 主要看什么",
  forbidden_list: "AI 填 · 绝对禁止",
  cost_ratio: "AI 填 · 吃苦指数",
  battlefield: "AI 填 · 主线战场",
  track: "AI 填 · 剧情轨道",
};

// ── 契约数据形态 ─────────────────────────────────────────────────────────

interface ForbiddenItem {
  tagId?: string;
  text?: string;
}

interface GenrePayload {
  core_promise: string;
  promise_note: string;
  forbidden_list: ForbiddenItem[];
  cost_ratio: number | null;
  battlefield: string[];
  track: string;
}

const EMPTY: GenrePayload = {
  core_promise: "",
  promise_note: "",
  forbidden_list: [],
  cost_ratio: null,
  battlefield: [],
  track: "",
};

function normalize(raw: unknown): GenrePayload {
  const d = (raw ?? {}) as Partial<GenrePayload>;
  const cost = d.cost_ratio;
  return {
    core_promise: (d.core_promise ?? "").toString(),
    promise_note: (d.promise_note ?? "").toString(),
    forbidden_list: Array.isArray(d.forbidden_list)
      ? d.forbidden_list.filter((x): x is ForbiddenItem => !!x && typeof x === "object")
      : [],
    cost_ratio: typeof cost === "number" && cost >= 1 && cost <= 10 ? cost : null,
    battlefield: Array.isArray(d.battlefield) ? d.battlefield.filter(Boolean).map(String) : [],
    track: (d.track ?? "").toString(),
  };
}

/** 候选源（接口失败时回退本地镜像，保证胶囊可用）。 */
function useCandidates() {
  const [promise, setPromise] = useState(() =>
    GENRE_VOCAB.filter((e) => e.kind === "promise"),
  );
  const [forbidden, setForbidden] = useState(() =>
    GENRE_VOCAB.filter((e) => e.kind === "forbidden"),
  );
  const [battlefield, setBattlefield] = useState(() =>
    GENRE_VOCAB.filter((e) => e.kind === "battlefield"),
  );
  useEffect(() => {
    let cancelled = false;
    api
      .get("/genres/candidates")
      .then((d: Record<string, Array<{ id: string; label: string }>> | null) => {
        if (cancelled || !d) return;
        const pick = (kind: VocabKind) =>
          (d[kind] ?? []).map((e, i) => ({ id: e.id, kind, label: e.label, sort: i * 10 }));
        if (d.promise?.length) setPromise(pick("promise"));
        if (d.forbidden?.length) setForbidden(pick("forbidden"));
        if (d.battlefield?.length) setBattlefield(pick("battlefield"));
      })
      .catch(() => {
        /* 回退本地镜像，不阻断填写 */
      });
    return () => {
      cancelled = true;
    };
  }, []);
  return { promise, forbidden, battlefield };
}

// ── 一格的外壳（编号 + 名称 + 怎么填 + 成书去处 + 内容）───────────────────

function Mod({
  no,
  name,
  why,
  use,
  children,
}: {
  no: string;
  name: string;
  why: string;
  use: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="mod">
      <div className="mod-head">
        <span className="m-no">{no}</span>
        <span className="m-name">{name}</span>
        <span className="m-why">{why}</span>
        <span className="m-use">{use}</span>
      </div>
      {children}
    </div>
  );
}

// ── Main ─────────────────────────────────────────────────────────────────

const GenreSettingForm = forwardRef<GenreHandle, GenreSettingFormProps>(function GenreSettingForm(
  { projectId, settingKey, onDirtyChange, novelName },
  ref,
) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [data, setData] = useState<GenrePayload>(EMPTY);
  /** 01 口味胶囊＝纯 UI 联动，不落库、不计入判据。 */
  const [flavorKey, setFlavorKey] = useState<string | null>(null);
  const [customForbidden, setCustomForbidden] = useState("");
  const loadedRef = useRef(false);
  const { snapshotLoaded, markSaved, markDirty } = useDirtyState(data, onDirtyChange);
  const cand = useCandidates();

  // ── 加载 ──────────────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .get(`/novels/${projectId}/settings/${settingKey}`)
      .then((d: unknown) => {
        if (cancelled) return;
        const norm = normalize(d);
        setData(norm);
        snapshotLoaded(norm);
      })
      .catch(() => {
        if (!cancelled) setError("加载失败");
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
          loadedRef.current = true;
        }
      });
    return () => {
      cancelled = true;
    };
    // snapshotLoaded 引用稳定；仅项目/键切换重拉
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, settingKey]);

  const patch = useCallback((p: Partial<GenrePayload>) => {
    setData((prev) => ({ ...prev, ...p }));
  }, []);

  // ── 01 口味联动：预填 02/03/04/05（不写 promise_note/track）──────────
  const applyFlavor = useCallback(
    (key: string) => {
      const f = GENRE_FLAVORS.find((x) => x.key === key);
      if (!f) return;
      setFlavorKey(key);
      setData((prev) => ({
        ...prev,
        core_promise: f.corePromise,
        forbidden_list: f.forbidden.map((tagId) => ({ tagId })),
        cost_ratio: f.costRatio,
        battlefield: [...f.battlefield],
      }));
      toast.success(`已按「${f.label}」给出口味建议，各格可改`);
    },
    [],
  );

  // ── 03 绝对禁止：勾选 / 自定义 ─────────────────────────────────────
  const forbidSelected = useMemo(
    () => new Set(data.forbidden_list.map((f) => f.tagId).filter(Boolean) as string[]),
    [data.forbidden_list],
  );
  const toggleForbidden = useCallback(
    (tagId: string) => {
      setData((prev) => {
        const has = prev.forbidden_list.some((f) => f.tagId === tagId);
        return {
          ...prev,
          forbidden_list: has
            ? prev.forbidden_list.filter((f) => f.tagId !== tagId)
            : [...prev.forbidden_list, { tagId }],
        };
      });
    },
    [],
  );
  const addCustomForbidden = useCallback(() => {
    const text = customForbidden.trim();
    if (!text) return;
    if (data.forbidden_list.length >= GENRE_LIMITS.forbiddenMax) {
      toast.info(`最多 ${GENRE_LIMITS.forbiddenMax} 条禁区`);
      return;
    }
    setData((prev) => ({ ...prev, forbidden_list: [...prev.forbidden_list, { text }] }));
    setCustomForbidden("");
  }, [customForbidden, data.forbidden_list.length]);

  // ── 05 主线战场：勾选 / 移除（自定义项由 AI 采纳写入，可 × 移除）────
  const toggleBattlefield = useCallback((val: string) => {
    setData((prev) => {
      const has = prev.battlefield.includes(val);
      if (!has && prev.battlefield.length >= GENRE_LIMITS.battlefieldMax) {
        toast.info(`最多 ${GENRE_LIMITS.battlefieldMax} 个战场`);
        return prev;
      }
      return {
        ...prev,
        battlefield: has
          ? prev.battlefield.filter((x) => x !== val)
          : [...prev.battlefield, val],
      };
    });
  }, []);

  // ── AI 结果区（tasks 4.2 / D14）：每格一个 sink，采纳才写回 ─────────
  const [sinks, setSinks] = useState<
    Partial<Record<GenreAiField, { label: string; node: React.ReactNode; adopt: () => void }>>
  >({});
  const [running, setRunning] = useState<GenreAiField | null>(null);

  const runAi = useCallback(
    async (field: GenreAiField) => {
      setRunning(field);
      setSinks((prev) => ({ ...prev, [field]: undefined }));
      const context: Record<string, unknown> = {
        current:
          field === "core_promise"
            ? data.core_promise
            : field === "forbidden_list"
              ? data.forbidden_list
              : field === "cost_ratio"
                ? data.cost_ratio
                : field === "battlefield"
                  ? data.battlefield
                  : data.track,
        core_promise: data.core_promise,
        forbidden_list: data.forbidden_list,
        cost_ratio: data.cost_ratio,
        battlefield: data.battlefield,
      };
      await genreAi(field, { title: novelName ?? "", context }, projectId)
        .then((r) => {
          const v = r.value;
          let node: React.ReactNode;
          let adopt: () => void;
          if (field === "core_promise") {
            const { value, note } = v as { value: string; note: string };
            node = (
              <>
                <p style={{ margin: "4px 0" }}>
                  <b>{value}</b>
                </p>
                {note && <p style={{ margin: "4px 0", color: "var(--muted)" }}>{note}</p>}
              </>
            );
            adopt = () => patch({ core_promise: value, promise_note: note });
          } else if (field === "forbidden_list") {
            const list = (v as Array<{ tagId?: string; text?: string }>) ?? [];
            node = (
              <p style={{ margin: 0 }}>
                {list.map((x) => x.tagId ?? x.text).join(" · ") || "（没有建议）"}
              </p>
            );
            adopt = () => patch({ forbidden_list: list });
          } else if (field === "cost_ratio") {
            const n = v as number;
            node = <p style={{ margin: 0 }}>建议 {n} 分 —— {costSentence(n).split("→ ")[1]}</p>;
            adopt = () => patch({ cost_ratio: n });
          } else if (field === "battlefield") {
            const list = (v as Array<{ tagId?: string; text?: string }>) ?? [];
            const vals = list.map((x) => x.tagId ?? x.text ?? "").filter(Boolean);
            node = <p style={{ margin: 0 }}>{vals.map(vocabLabel).join(" · ") || "（没有建议）"}</p>;
            adopt = () => patch({ battlefield: vals });
          } else {
            const text = v as string;
            node = <p style={{ margin: 0 }}>{text}</p>;
            adopt = () => patch({ track: text });
          }
          setSinks((prev) => ({
            ...prev,
            [field]: { label: AI_LABEL[field], node, adopt },
          }));
        })
        .catch((e: unknown) => {
          const reason = aiBlockReason(e);
          if (reason === "member_required") {
            toast.info("AI 是会员功能，升级 PRO 后解锁");
          } else if (reason === "no_key") {
            toast.info("先去「模型配置」添加 API Key");
          } else if (reason === "missing_model" || reason === "invalid") {
            toast.info("先在本书选择模型");
          } else {
            toast.error((e as Error).message || "AI 暂不可用，请重试");
          }
        })
        .finally(() => setRunning(null));
    },
    [data, novelName, projectId, patch],
  );

  // ── 保存 ──────────────────────────────────────────────────────────
  const save = useCallback(async (): Promise<boolean> => {
    if (saving) return false;
    setSaving(true);
    setError("");
    try {
      await api.put(`/novels/${projectId}/settings/${settingKey}`, data);
      markSaved();
      return true;
    } catch (e) {
      setError((e as Error).message || "保存失败");
      return false;
    } finally {
      setSaving(false);
    }
  }, [projectId, settingKey, data, saving, markSaved]);

  useImperativeHandle(
    ref,
    () => ({ save, runAi, markDirty, clearAi: () => setSinks({}) }),
    [save, runAi, markDirty],
  );

  if (loading) return <p className="opt">加载中…</p>;

  const forbidCustom = data.forbidden_list.filter((f) => f.text);
  const unknownBattlefield = data.battlefield.filter(
    (b) => !cand.battlefield.some((c) => c.id === b),
  );

  return (
    <div data-od-id="genre-panel">
      {/* 01 口味胶囊 —— 预置联动 */}
      <Mod
        no="01"
        name="题材"
        why="选个口味起点，下面各格跟着给建议"
        use={
          <>
            "填好后："
            <b>全书都按这套口味给建议</b>
            "，随时可换"
          </>
        }
      >
        <div className="cap-row">
          {GENRE_FLAVORS.map((f) => (
            <button
              key={f.key}
              className={`cap${flavorKey === f.key ? " on" : ""}`}
              type="button"
              data-g={f.key}
              onClick={() => applyFlavor(f.key)}
            >
              {f.label}
            </button>
          ))}
        </div>
      </Mod>

      {/* 02 主要看什么 → core_promise + promise_note */}
      <Mod
        no="02"
        name="主要看什么"
        why="读者翻开这本书，主要看的是什么"
        use={
          <>
            "填好后："
            <b>全书都围绕它写</b>
            "，章节不跑题"
          </>
        }
      >
        <textarea
          className="textarea"
          rows={2}
          maxLength={GENRE_LIMITS.corePromise}
          data-od-id="m1-input"
          placeholder="例：主要看以弱破强的痛快——境界压着他，他专挑别人修为里的漏洞打"
          value={data.core_promise}
          onChange={(e) => patch({ core_promise: e.target.value })}
        />
        {data.promise_note && (
          <p className="opt" style={{ margin: "6px 0 0", fontSize: 11.5 }}>
            AI 补充读者预期：{data.promise_note}
          </p>
        )}
        {running === "core_promise" && (
          <p className="opt" style={{ margin: "8px 0 0", fontSize: 11.5 }}>AI 生成中…</p>
        )}
        {sinks.core_promise && (
          <AiSink
            label={sinks.core_promise!.label}
            adoptText="采纳 · 覆盖"
            onAdopt={() => {
              sinks.core_promise!.adopt();
              toast.success("已采纳，落回对应格，随时可改");
            }}
            onRetry={() => runAi("core_promise")}
            data-od-id={`genre-ai-sink-core_promise`}
          >
            {sinks.core_promise!.node}
          </AiSink>
        )}
      </Mod>

      {/* 03 绝对禁止 → forbidden_list */}
      <Mod
        no="03"
        name="绝对禁止"
        why="勾了就不写；取消勾选＝明知风险偏要写"
        use={
          <>
            "填好后："
            <b>这些雷全书不会出现</b>
            "，AI 也不写"
          </>
        }
      >
        <div className="cap-row" style={{ marginBottom: 8 }}>
          {cand.forbidden.map((c) => (
            <button
              key={c.id}
              className={`cap${forbidSelected.has(c.id) ? " on" : ""}`}
              type="button"
              data-forbid={c.id}
              onClick={() => toggleForbidden(c.id)}
            >
              {c.label}
            </button>
          ))}
          {forbidCustom.map((f) => (
            <button
              key={f.text}
              className="cap on"
              type="button"
              title="点击移除"
              onClick={() =>
                setData((prev) => ({
                  ...prev,
                  forbidden_list: prev.forbidden_list.filter((x) => x !== f),
                }))
              }
            >
              {f.text} ×
            </button>
          ))}
        </div>
        <div className="cap-add">
          <input
            data-od-id="forbid-input"
            placeholder="写你自己的禁区，回车添加"
            value={customForbidden}
            maxLength={100}
            onChange={(e) => setCustomForbidden(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addCustomForbidden();
              }
            }}
          />
        </div>
        {running === "forbidden_list" && (
          <p className="opt" style={{ margin: "8px 0 0", fontSize: 11.5 }}>AI 生成中…</p>
        )}
        {sinks.forbidden_list && (
          <AiSink
            label={sinks.forbidden_list!.label}
            adoptText="采纳 · 覆盖"
            onAdopt={() => {
              sinks.forbidden_list!.adopt();
              toast.success("已采纳，落回对应格，随时可改");
            }}
            onRetry={() => runAi("forbidden_list")}
            data-od-id={`genre-ai-sink-forbidden_list`}
          >
            {sinks.forbidden_list!.node}
          </AiSink>
        )}
      </Mod>

      {/* 04 吃苦指数 → cost_ratio */}
      <Mod
        no="04"
        name="吃苦指数"
        why="主角得到好处要付多大代价：1 最轻（流汗破财）～ 10 最重（折寿献祭）"
        use={
          <>
            "填好后："
            <b>变强有代价，不白拿</b>
            "，爽感才立得住"
          </>
        }
      >
        <div className="cost-row">
          <input
            type="range"
            min={1}
            max={10}
            step={1}
            data-od-id="cost-slider"
            value={data.cost_ratio ?? 5}
            onChange={(e) => patch({ cost_ratio: Number(e.target.value) })}
          />
          <span className="cost-val num">{data.cost_ratio ?? "—"}</span>
        </div>
        {data.cost_ratio !== null && (
          <span className="cost-sent" data-od-id="cost-sentence">
            {costSentence(data.cost_ratio)}
          </span>
        )}
        <div className="cost-scale">
          <span>1 流汗破财</span>
          <span>5 断骨毁名</span>
          <span>10 命抵江山</span>
        </div>
        {running === "cost_ratio" && (
          <p className="opt" style={{ margin: "8px 0 0", fontSize: 11.5 }}>AI 生成中…</p>
        )}
        {sinks.cost_ratio && (
          <AiSink
            label={sinks.cost_ratio!.label}
            adoptText="采纳 · 覆盖"
            onAdopt={() => {
              sinks.cost_ratio!.adopt();
              toast.success("已采纳，落回对应格，随时可改");
            }}
            onRetry={() => runAi("cost_ratio")}
            data-od-id={`genre-ai-sink-cost_ratio`}
          >
            {sinks.cost_ratio!.node}
          </AiSink>
        )}
      </Mod>

      {/* 05 主线战场 → battlefield */}
      <Mod
        no="05"
        name="主线战场"
        why="整本书主要斗什么（建议 1-2 个）"
        use={
          <>
            "填好后："
            <b>每卷冲突围绕战场</b>
            "，不打野架"
          </>
        }
      >
        <div className="cap-row" style={{ marginBottom: 6 }}>
          {cand.battlefield.map((c) => (
            <button
              key={c.id}
              className={`cap${data.battlefield.includes(c.id) ? " on" : ""}`}
              type="button"
              data-bf={c.id}
              onClick={() => toggleBattlefield(c.id)}
            >
              {c.label}
            </button>
          ))}
          {unknownBattlefield.map((b) => (
            <button
              key={b}
              className="cap on"
              type="button"
              title="点击移除"
              onClick={() => toggleBattlefield(b)}
            >
              {vocabLabel(b)} ×
            </button>
          ))}
        </div>
        {data.battlefield.length >= 3 && (
          <p className="soft-note" data-od-id="bf-note">
            战场越多，主线越难聚焦，建议 1-2 个。
          </p>
        )}
        {running === "battlefield" && (
          <p className="opt" style={{ margin: "8px 0 0", fontSize: 11.5 }}>AI 生成中…</p>
        )}
        {sinks.battlefield && (
          <AiSink
            label={sinks.battlefield!.label}
            adoptText="采纳 · 覆盖"
            onAdopt={() => {
              sinks.battlefield!.adopt();
              toast.success("已采纳，落回对应格，随时可改");
            }}
            onRetry={() => runAi("battlefield")}
            data-od-id={`genre-ai-sink-battlefield`}
          >
            {sinks.battlefield!.node}
          </AiSink>
        )}
      </Mod>

      {/* 06 剧情轨道 → track */}
      <Mod
        no="06"
        name="剧情轨道"
        why="整本书怎么走（可不填）"
        use={
          <>
            "填好后："
            <b>百万字沿它走</b>
            "，写作台常驻可查"
          </>
        }
      >
        <textarea
          className="textarea"
          rows={2}
          maxLength={GENRE_LIMITS.track}
          data-od-id="track-input"
          placeholder="凡人流——从练气一步步爬，每卷突破一个大境界、了结一桩恩怨"
          value={data.track}
          onChange={(e) => patch({ track: e.target.value })}
        />
        {running === "track" && (
          <p className="opt" style={{ margin: "8px 0 0", fontSize: 11.5 }}>AI 生成中…</p>
        )}
        {sinks.track && (
          <AiSink
            label={sinks.track!.label}
            adoptText="采纳 · 覆盖"
            onAdopt={() => {
              sinks.track!.adopt();
              toast.success("已采纳，落回对应格，随时可改");
            }}
            onRetry={() => runAi("track")}
            data-od-id={`genre-ai-sink-track`}
          >
            {sinks.track!.node}
          </AiSink>
        )}
      </Mod>

      {error && (
        <p className="opt" style={{ color: "var(--err)" }}>
          {error}
        </p>
      )}
    </div>
  );
});

export default GenreSettingForm;
