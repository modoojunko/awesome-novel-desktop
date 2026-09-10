// ── GenreSettingForm ──────────────────────────────────────────────────────
// 题材设定面板（genre-signup-redesign tasks 4.1 / D18·D19 新契约）：
//   六格 = 01 题材目录（大类必选 + 子类可选，落 story.yaml）+ 02 主要看什么
//   + 03 绝对禁止 + 04 吃苦指数 + 05 主线战场 + 06 剧情轨道。
//   每格 = 编号 + 怎么填（m-why）+ 成书视角去处（m-use）。
//
// 存储契约（对外七字段 JSON；01 落 story.yaml，其余关系化落 4 张表）：
//   01 → theme + sub_genre（题材目录，见 lib/themeCatalog.ts；后端按目录校验，未知 400）
//   02 → core_promise(≤60) + promise_note(≤200，AI 补充、不单独成行)
//   03 → forbidden_list[{tagId|text}]   04 → cost_ratio(1-10)
//   05 → battlefield[]（tagId 或自定义文本）  06 → track(≤300)
// 空值统一："" / 空白 / [] / null 等价未填（后端 Pydantic + CHECK 同口径）。
// AI 反馈落各格下方 .ai-sink（tasks 4.2），采纳才写回控件。

import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "@/lib/toast";
import { Ico, P } from "@/components/icons";
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
import { THEMES, subThemeEntry, themeEntry, type SubTheme } from "@/lib/themeCatalog";

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

/** 01 选择器的一行：大类（＝只归大类）或「大类 + 子类」。 */
type ThemeRow =
  | { kind: "theme"; theme: string; sub?: undefined }
  | { kind: "sub"; theme: string; sub: SubTheme };

interface GenrePayload {
  /** 01 题材目录（大类/子类）——落 story.yaml，与简介同族。 */
  theme: string;
  sub_genre: string;
  core_promise: string;
  promise_note: string;
  forbidden_list: ForbiddenItem[];
  cost_ratio: number | null;
  battlefield: string[];
  track: string;
}

const EMPTY: GenrePayload = {
  theme: "",
  sub_genre: "",
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
    theme: (d.theme ?? "").toString(),
    sub_genre: (d.sub_genre ?? "").toString(),
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

  // ── 01 题材选择器（Cascader 式）：展开态 / 搜索词 / 正在浏览的大类 / 键盘游标 ──
  const [themeOpen, setThemeOpen] = useState(false);
  const [themeQuery, setThemeQuery] = useState("");
  const [activeTheme, setActiveTheme] = useState("");
  const [cursor, setCursor] = useState(0);
  const themeBoxRef = useRef<HTMLDivElement | null>(null);
  const themeSearchRef = useRef<HTMLInputElement | null>(null);

  const closeThemePanel = useCallback(() => {
    setThemeOpen(false);
    setThemeQuery("");
  }, []);

  const toggleThemePanel = useCallback(() => {
    setThemeOpen((open) => {
      if (open) {
        setThemeQuery("");
        return false;
      }
      // 展开时把浏览列定位到已选大类（未选则给第一个），游标归零
      setThemeQuery("");
      setActiveTheme((cur) => (cur || THEMES[0].name));
      setCursor(0);
      return true;
    });
  }, []);

  useEffect(() => {
    if (themeOpen) themeSearchRef.current?.focus();
  }, [themeOpen]);

  // 点面板外收起（TDesign popup 同语义；本页是就地展开，故监听整个文档）。
  // Esc 也挂文档级：点过大类后焦点在按钮上，只挂搜索框会收不起来。
  useEffect(() => {
    if (!themeOpen) return;
    const onDown = (e: MouseEvent) => {
      if (themeBoxRef.current && !themeBoxRef.current.contains(e.target as Node)) {
        closeThemePanel();
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeThemePanel();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [themeOpen, closeThemePanel]);

  // 展开时若已选题材，浏览列跟随；首次展开定位到已选/首个
  useEffect(() => {
    if (themeOpen) setActiveTheme((cur) => cur || data.theme || THEMES[0].name);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [themeOpen]);

  /** 当前可选项列表：搜索态＝全目录命中（拍平成「大类 / 子类」路径）；否则＝浏览列的
   *  「只归到大类」+ 该大类子类。键盘 ↑↓/Enter 与渲染共用这一份，避免两套取舍。 */
  const searching = themeQuery.trim().length > 0;
  const themeRows = useMemo<ThemeRow[]>(() => {
    if (!searching) {
      const t = themeEntry(activeTheme);
      return [
        { kind: "theme", theme: activeTheme },
        ...(t?.subTypes ?? []).map((sub) => ({
          kind: "sub" as const,
          theme: activeTheme,
          sub,
        })),
      ];
    }
    const q = themeQuery.trim().toLowerCase();
    const hit = (s: string) => s.toLowerCase().includes(q);
    const out: ThemeRow[] = [];
    for (const t of THEMES) {
      if (hit(t.name) || hit(t.desc)) out.push({ kind: "theme", theme: t.name });
      for (const sub of t.subTypes) {
        if (hit(sub.name) || hit(sub.desc) || hit(sub.example)) {
          out.push({ kind: "sub", theme: t.name, sub });
        }
      }
    }
    return out;
  }, [searching, themeQuery, activeTheme]);

  /** 点大类＝选中它并浏览其子类（checkStrictly：父级也可单独选）；再次点同一大类不清空
   *  （清空走字段右侧 ×，与 TDesign `clearable` 一致）。 */
  const browseTheme = useCallback((name: string) => {
    setActiveTheme(name);
    setCursor(0);
    setData((prev) => ({
      ...prev,
      theme: name,
      sub_genre: prev.theme === name ? prev.sub_genre : "",
    }));
  }, []);

  const pickRow = useCallback(
    (row: ThemeRow, close: boolean) => {
      if (row.kind === "theme") browseTheme(row.theme);
      else
        setData((prev) => ({ ...prev, theme: row.theme, sub_genre: row.sub!.name }));
      if (close) closeThemePanel();
    },
    [browseTheme, closeThemePanel],
  );

  const clearTheme = useCallback(() => {
    setData((prev) => ({ ...prev, theme: "", sub_genre: "" }));
  }, []);

  const onThemeKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Escape") {
        e.preventDefault();
        closeThemePanel();
        return;
      }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        setCursor((c) => {
          const n = themeRows.length;
          if (n === 0) return 0;
          return e.key === "ArrowDown" ? (c + 1) % n : (c - 1 + n) % n;
        });
        return;
      }
      if (e.key === "Enter") {
        e.preventDefault();
        const row = themeRows[cursor];
        // 未搜索时 Enter 作用在浏览列：子类＝选完收起；「只归到大类」＝选中并收起
        if (row) pickRow(row, true);
      }
    },
    [themeRows, cursor, pickRow, closeThemePanel],
  );

  // ── 02 常见口味快捷填充：预填 02/03/04/05（不写 promise_note/track）───
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

  // ── AI 结果区（tasks 4.2 / D14 + 生成历史）：每格保留**最近 5 次**结果，
  //    可切回任意一次再采纳（避免无限抽卡 / 反悔）；采纳＝覆盖该格控件。────
  const SINK_MAX = 5;
  const [sinks, setSinks] = useState<
    Partial<
      Record<
        GenreAiField,
        { list: Array<{ label: string; node: React.ReactNode; adopt: () => void }>; idx: number }
      >
    >
  >({});
  const [running, setRunning] = useState<GenreAiField | null>(null);
  /** 面板级在途锁（ref 同步判定）：同时在飞的只有一个题材 AI 请求。 */
  const aiBusyRef = useRef(false);

  const runAi = useCallback(
    async (field: GenreAiField) => {
      if (aiBusyRef.current) return; // 已有在途请求：忽略重复触发
      aiBusyRef.current = true;
      setRunning(field);
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
          setSinks((prev) => {
            const list = [...(prev[field]?.list ?? []), { label: AI_LABEL[field], node, adopt }].slice(
              -SINK_MAX,
            );
            return { ...prev, [field]: { list, idx: list.length - 1 } };
          });
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
        .finally(() => {
          aiBusyRef.current = false;
          setRunning(null);
        });
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
  // 01 解读区：选了子类说子类（更具体），只选大类说大类；都没选则不占位
  const subEntry = subThemeEntry(data.theme, data.sub_genre);
  const themeNote = subEntry
    ? { name: data.sub_genre, desc: subEntry.desc, example: subEntry.example }
    : themeEntry(data.theme) && {
        name: data.theme,
        desc: themeEntry(data.theme)!.desc,
        example: "",
      };

  return (
    <div data-od-id="genre-panel">
      {/* 01 题材目录 —— 字段 + 就地展开的两级选择（2026-09-10 用户要求「参考 tdesign、页面简洁」）。
          形态对标 TDesign Cascader：`checkStrictly`（父级＝大类可单独选）、`filterable`（搜索，
          命中项拍平成「大类 / 子类」路径）、`clearable`（字段右 × 清空）。**就地展开而非浮层**：
          设定面板列自身 overflow-y:auto，浮层会被裁切/随滚动漂移；浮层方案需 portal + 滚动跟随，
          与本页「简洁」相悖（用户 2026-09-10 反馈）。 */}
      <Mod
        no="01"
        name="题材"
        why="这本书写的是什么题材"
        use={
          <>
            "填好后："
            <b>全书按这个题材的类型规则走</b>
            "，随时可换"
          </>
        }
      >
        <div className="sel" ref={themeBoxRef} data-od-id="theme-select">
          <button
            type="button"
            className={`sel-field${themeOpen ? " on" : ""}`}
            data-od-id="theme-trigger"
            aria-haspopup="listbox"
            aria-expanded={themeOpen}
            onClick={toggleThemePanel}
          >
            <span className={data.theme ? "v" : "ph"}>
              {data.theme
                ? data.sub_genre
                  ? `${data.theme} / ${data.sub_genre}`
                  : data.theme
                : "选择题材"}
            </span>
            {data.theme && (
              <span
                className="sel-clear"
                role="button"
                aria-label="清除题材"
                data-od-id="theme-clear"
                onClick={(e) => {
                  e.stopPropagation();
                  clearTheme();
                }}
              >
                ×
              </span>
            )}
            {/* 展开态靠字段边框变 accent 表达，箭头保持向下（图标集无 chevronUp） */}
            <Ico d={P.chevronDown} className={themeOpen ? "open" : undefined} />
          </button>

          {themeOpen && (
            <div className="sel-panel" data-od-id="theme-panel">
              <input
                ref={themeSearchRef}
                className="sel-search"
                data-od-id="theme-search"
                placeholder="搜索题材（名 / 解读 / 案例）"
                value={themeQuery}
                spellCheck={false}
                onChange={(e) => {
                  setThemeQuery(e.target.value);
                  setCursor(0);
                }}
                onKeyDown={onThemeKeyDown}
              />
              {searching ? (
                <ul className="sel-list" role="listbox" data-od-id="theme-results">
                  {themeRows.map((r, i) => (
                    <li key={`${r.theme}/${r.sub?.name ?? ""}`}>
                      <button
                        type="button"
                        role="option"
                        aria-selected={i === cursor}
                        className={`sel-item${i === cursor ? " cur" : ""}`}
                        data-g={r.sub ? `sub:${r.sub.name}` : `theme:${r.theme}`}
                        onMouseEnter={() => setCursor(i)}
                        onClick={() => pickRow(r, true)}
                      >
                        <span className="si-name">
                          {r.sub ? (
                            <>
                              <em>{r.theme} / </em>
                              {r.sub.name}
                            </>
                          ) : (
                            <>
                              {r.theme}
                              <em>　只归到大类</em>
                            </>
                          )}
                        </span>
                        <span className="si-desc">
                          {r.sub ? r.sub.desc : themeEntry(r.theme)?.desc}
                        </span>
                      </button>
                    </li>
                  ))}
                  {themeRows.length === 0 && (
                    <li className="sel-empty">没有匹配的题材，换个词试试</li>
                  )}
                </ul>
              ) : (
                <div className="sel-cols">
                  <ul
                    className="sel-col themes"
                    role="listbox"
                    aria-label="题材大类"
                    data-od-id="theme-row"
                  >
                    {THEMES.map((t) => (
                      <li key={t.name}>
                        <button
                          type="button"
                          role="option"
                          aria-selected={data.theme === t.name}
                          className={`sel-item${activeTheme === t.name ? " cur" : ""}${
                            data.theme === t.name ? " on" : ""
                          }`}
                          data-g={`theme:${t.name}`}
                          title={t.desc}
                          onClick={() => browseTheme(t.name)}
                        >
                          <span className="si-name">{t.name}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                  <ul
                    className="sel-col subs"
                    role="listbox"
                    aria-label="题材子类"
                    data-od-id="sub-genre-row"
                  >
                    {themeRows.map((r, i) => (
                      <li key={r.sub?.name ?? "only"}>
                        <button
                          type="button"
                          role="option"
                          aria-selected={
                            r.sub ? data.sub_genre === r.sub.name : !data.sub_genre
                          }
                          className={`sel-item${i === cursor ? " cur" : ""}${
                            (r.sub ? data.sub_genre === r.sub.name : data.sub_genre === "")
                              ? " on"
                              : ""
                          }${r.sub ? "" : " only"}`}
                          data-g={r.sub ? `sub:${r.sub.name}` : `theme:${r.theme}`}
                          title={
                            r.sub
                              ? `${r.sub.desc}　案例：${r.sub.example}`
                              : `只标大类「${r.theme}」，不分子类`
                          }
                          onMouseEnter={() => setCursor(i)}
                          onClick={() => pickRow(r, true)}
                        >
                          <span className="si-name">
                            {r.sub ? r.sub.name : `只归到大类（${r.theme}）`}
                          </span>
                          <span className="si-desc">
                            {r.sub ? r.sub.desc : "不分小类也行，随时能回来补"}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
        {/* 解读 + 案例：选中什么就说什么（只选大类则说大类），光有标签作者不知道指什么 */}
        {themeNote && (
          <p className="cap-note" data-od-id="theme-note">
            <b>{themeNote.name}</b>
            {"："}
            {themeNote.desc}
            {themeNote.example && (
              <span className="eg">
                案例：{themeNote.example}
              </span>
            )}
          </p>
        )}
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
        {/* 常见口味快捷填充：一次性预填 02/03/04/05（纯起点，各格可改） */}
        <div className="cap-row flavors">
          <span className="cap-label inline">常见口味</span>
          {GENRE_FLAVORS.map((f) => (
            <button
              key={f.key}
              className={`cap${flavorKey === f.key ? " on" : ""}`}
              type="button"
              data-g={f.key}
              title="一次预填主要看什么 / 绝对禁止 / 吃苦指数 / 主线战场"
              onClick={() => applyFlavor(f.key)}
            >
              {f.label}
            </button>
          ))}
        </div>
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
{(() => {
          const st = sinks.core_promise;
          if (!st) return null;
          const { list, idx: active } = st;
          const entry = list[active];
          if (!entry) return null;
          return (
            <AiSink
              label={entry.label}
              history={{
                total: list.length,
                active,
                max: SINK_MAX,
                onSelect: (i) =>
                  setSinks((prev) => {
                    const cur = prev.core_promise;
                    return cur ? { ...prev, core_promise: { ...cur, idx: i } } : prev;
                  }),
              }}
              adoptText="采纳 · 覆盖"
              onAdopt={() => {
                entry.adopt();
                toast.success("已采纳，落回对应格，随时可改");
              }}
              onRetry={() => runAi("core_promise")}
              data-od-id={`genre-ai-sink-core_promise`}
            >
              {entry.node}
            </AiSink>
          );
        })()}
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
{(() => {
          const st = sinks.forbidden_list;
          if (!st) return null;
          const { list, idx: active } = st;
          const entry = list[active];
          if (!entry) return null;
          return (
            <AiSink
              label={entry.label}
              history={{
                total: list.length,
                active,
                max: SINK_MAX,
                onSelect: (i) =>
                  setSinks((prev) => {
                    const cur = prev.forbidden_list;
                    return cur ? { ...prev, forbidden_list: { ...cur, idx: i } } : prev;
                  }),
              }}
              adoptText="采纳 · 覆盖"
              onAdopt={() => {
                entry.adopt();
                toast.success("已采纳，落回对应格，随时可改");
              }}
              onRetry={() => runAi("forbidden_list")}
              data-od-id={`genre-ai-sink-forbidden_list`}
            >
              {entry.node}
            </AiSink>
          );
        })()}
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
{(() => {
          const st = sinks.cost_ratio;
          if (!st) return null;
          const { list, idx: active } = st;
          const entry = list[active];
          if (!entry) return null;
          return (
            <AiSink
              label={entry.label}
              history={{
                total: list.length,
                active,
                max: SINK_MAX,
                onSelect: (i) =>
                  setSinks((prev) => {
                    const cur = prev.cost_ratio;
                    return cur ? { ...prev, cost_ratio: { ...cur, idx: i } } : prev;
                  }),
              }}
              adoptText="采纳 · 覆盖"
              onAdopt={() => {
                entry.adopt();
                toast.success("已采纳，落回对应格，随时可改");
              }}
              onRetry={() => runAi("cost_ratio")}
              data-od-id={`genre-ai-sink-cost_ratio`}
            >
              {entry.node}
            </AiSink>
          );
        })()}
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
{(() => {
          const st = sinks.battlefield;
          if (!st) return null;
          const { list, idx: active } = st;
          const entry = list[active];
          if (!entry) return null;
          return (
            <AiSink
              label={entry.label}
              history={{
                total: list.length,
                active,
                max: SINK_MAX,
                onSelect: (i) =>
                  setSinks((prev) => {
                    const cur = prev.battlefield;
                    return cur ? { ...prev, battlefield: { ...cur, idx: i } } : prev;
                  }),
              }}
              adoptText="采纳 · 覆盖"
              onAdopt={() => {
                entry.adopt();
                toast.success("已采纳，落回对应格，随时可改");
              }}
              onRetry={() => runAi("battlefield")}
              data-od-id={`genre-ai-sink-battlefield`}
            >
              {entry.node}
            </AiSink>
          );
        })()}
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
{(() => {
          const st = sinks.track;
          if (!st) return null;
          const { list, idx: active } = st;
          const entry = list[active];
          if (!entry) return null;
          return (
            <AiSink
              label={entry.label}
              history={{
                total: list.length,
                active,
                max: SINK_MAX,
                onSelect: (i) =>
                  setSinks((prev) => {
                    const cur = prev.track;
                    return cur ? { ...prev, track: { ...cur, idx: i } } : prev;
                  }),
              }}
              adoptText="采纳 · 覆盖"
              onAdopt={() => {
                entry.adopt();
                toast.success("已采纳，落回对应格，随时可改");
              }}
              onRetry={() => runAi("track")}
              data-od-id={`genre-ai-sink-track`}
            >
              {entry.node}
            </AiSink>
          );
        })()}
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
