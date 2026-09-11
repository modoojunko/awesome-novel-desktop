import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { Ico, P } from "@/components/icons";
import { api } from "@/lib/api";
import {
  aiBlockReason,
  worldDraftTopic,
  worldConsistencyCheck,
  worldLoreApply,
  type WorldAiField,
  type WorldCheckItem,
  type WorldCheckResult,
  type WorldDraftShape,
  type WorldFaction,
} from "@/lib/ai";
import { toast } from "@/lib/toast";
import { useDirtyState } from "@/hooks/useDirtyState";
import { SettingSaveHandle } from "../FormField";
import { useChangeReceipt, type ChangeReceiptState } from "../ChangeReceipt";
import KvListEditor, { type KvRow } from "./KvListEditor";
import {
  getLoreSuggestions,
  dropLoreSuggestion,
  type PendingLore,
} from "@/lib/loreSuggestions";

/** 契约 v2 形状（与后端 settings/world_model.py 逐字对应）。 */
export interface WorldData {
  no_power: boolean;
  stage: string;
  power: string;
  cost: string;
  history: KvRow[];
  factions: Array<{ name: string; note: string }>;
  constraints: KvRow[];
  extra: KvRow[];
}

const EMPTY: WorldData = {
  no_power: false,
  stage: "",
  power: "",
  cost: "",
  history: [],
  factions: [],
  constraints: [],
  extra: [],
};

const LOCK_SUGGESTS = [
  "能力上限",
  "不可推翻的事",
  "世人不知道的事",
  "世界何时毁灭",
  "感情底线",
  "真相唯一",
];
const EXTRA_SUGGESTS = [
  "族群与物种",
  "物品与信物",
  "能力与功法",
  "资源与货币",
  "社会与信仰",
  "地理与风物",
  "当前时间与局势",
  "语言与文字",
  "律法与刑罚",
  "节庆与民俗",
];
const HIST_SUGGESTS = ["大战与灾变", "旧仇恨", "未还的契约", "上古诅咒", "兴起与覆灭"];

function normalizeWorld(data: unknown): WorldData {
  const d = (data ?? {}) as Record<string, unknown>;
  const entries = (v: unknown): KvRow[] =>
    Array.isArray(v)
      ? v.map((e) => ({
          key: String((e as KvRow)?.key ?? ""),
          value: String((e as KvRow)?.value ?? ""),
        }))
      : [];
  const factions = (v: unknown): Array<{ name: string; note: string }> =>
    Array.isArray(v)
      ? v.map((f) => ({
          name: String((f as WorldFaction)?.name ?? ""),
          note: String((f as WorldFaction)?.note ?? ""),
        }))
      : [];
  return {
    no_power: Boolean(d.no_power),
    stage: String(d.stage ?? ""),
    power: String(d.power ?? ""),
    cost: String(d.cost ?? ""),
    history: entries(d.history),
    factions: factions(d.factions),
    constraints: entries(d.constraints),
    extra: entries(d.extra),
  };
}

const AI_CELL: Record<"stage" | "power" | "cost", string> = {
  stage: "世界舞台",
  power: "力量体系",
  cost: "力量的代价",
};

export interface WorldPanelProps {
  projectId: string;
  onDirtyChange?: (dirty: boolean) => void;
  onReceiptChange?: (r: ChangeReceiptState | null) => void;
}

export interface WorldPanelHandle extends SettingSaveHandle {
  runAi: (key: WorldAiField | "check") => Promise<void>;
  clearAi: () => void;
}

const WorldSettingPanel = forwardRef<WorldPanelHandle, WorldPanelProps>(function WorldSettingPanel({ projectId, onDirtyChange, onReceiptChange }, ref) {
  const [world, setWorld] = useState<WorldData>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [theme, setTheme] = useState<{ theme: string; sub: string } | null>(null);
  const { snapshotLoaded, markSaved, markDirty } = useDirtyState(world, onDirtyChange);
  const { record } = useChangeReceipt(onReceiptChange);

  interface SinkEntry {
    txt: string;
    value: string | Array<{ name: string; note: string }> | Array<{ key: string; value: string }>;
  }
  const [sinks, setSinks] = useState<Record<string, { list: SinkEntry[]; idx: number }>>({});
  const [check, setCheck] = useState<WorldCheckResult | null>(null);
  const [pendingLore, setPendingLore] = useState<PendingLore[]>([]);
  const [runningKey, setRunningKey] = useState<string | null>(null);
  const busyRef = useRef(false);
  const dataRef = useRef(world);
  dataRef.current = world;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .get(`/novels/${projectId}/settings/world`)
      .then((d) => {
        if (!cancelled) {
          const v = normalizeWorld(d);
          setWorld(v);
          snapshotLoaded(v);
        }
      })
      .catch(() => setLoading(false))
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    api
      .get(`/novels/${projectId}/settings/genre`)
      .then((g) => {
        if (!cancelled) setTheme({ theme: String(g?.theme ?? ""), sub: String(g?.sub_genre ?? "") });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const patch = (p: Partial<WorldData>) => {
    setWorld((prev) => ({ ...prev, ...p }));
    markDirty();
  };

  // ── 保存（gap3：确认前先落库；存草稿同一入口） ──────────────────────────
  const save = useCallback(async (): Promise<boolean> => {
    try {
      await api.put(`/novels/${projectId}/settings/world`, {
        ...dataRef.current,
        history: dataRef.current.history.filter((e) => e.key.trim() || e.value.trim()),
        factions: dataRef.current.factions.filter((f) => f.name.trim() || f.note.trim()),
        constraints: dataRef.current.constraints.filter((e) => e.key.trim() || e.value.trim()),
        extra: dataRef.current.extra.filter((e) => e.key.trim() || e.value.trim()),
      });
      markSaved();
      return true;
    } catch (e) {
      toast.error((e as Error).message || "保存失败");
      return false;
    }
  }, [projectId, markSaved]);

  // ── AI：生成/体检（右栏与格头快捷钮共用入口） ─────────────────────────
  /** 落格形状：铁律走 kv 条目、势力走 faction 行，其余一段话 */
  const SINK_SHAPE: Record<WorldSinkKey, WorldDraftShape> = {
    stage: "text", power: "text", cost: "text",
    factions: "faction", constraints: "kv",
  };
  const runAi = async (key: WorldAiField | "check"): Promise<void> => {
    if (busyRef.current) return;
    busyRef.current = true;
    setRunningKey(key);
    try {
      if (key === "check") {
        const r = await worldConsistencyCheck(projectId);
        setCheck(r);
      } else {
        const shape = SINK_SHAPE[key as WorldSinkKey] ?? "text";
        const res = await worldDraftTopic(key, projectId, shape);
        const raw = res.value;
        const rows = Array.isArray(raw) ? raw : null;
        const txt = rows
          ? rows
              .map((r) =>
                "name" in r
                  ? `${r.name}${r.note ? `：${r.note}` : ""}`
                  : `${r.key}：${r.value}`,
              )
              .join("\n")
          : String(raw);
        setSinks((prev) => {
          const h = prev[key] ?? { list: [], idx: -1 };
          const list = [...h.list, { txt, value: rows ?? txt }].slice(-5);
          return { ...prev, [key]: { list, idx: list.length - 1 } };
        });
      }
    } catch (e) {
      const reason = aiBlockReason(e);
      if (reason === "member_required") toast.info("AI 是会员功能，升级 PRO 后解锁");
      else if (reason === "no_key") toast.info("先去「模型配置」添加 API Key");
      else if (reason === "missing_model" || reason === "invalid") toast.info("先在本书选择模型");
      else toast.error((e as Error).message || "暂不可用，请重试");
    } finally {
      busyRef.current = false;
      setRunningKey(null);
    }
  };

  const adopt = (key: "stage" | "power" | "cost" | "factions" | "constraints") => {
    const h = sinks[key];
    if (!h) return;
    const entry = h.list[h.idx];
    const before = dataRef.current;
    if (key === "factions") {
      const next = entry.value as unknown as WorldFaction[];
      record(
        `已采纳「势力」（势力 ${before.factions.length} 行 → ${next.length} 行）`,
        () => setWorld((w) => ({ ...w, factions: next })),
        () => setWorld((w) => ({ ...w, factions: before.factions })),
      );
    } else if (key === "constraints") {
      const rows = entry.value as Array<{ key: string; value: string }>;
      const existing = new Set(before.constraints.map((r) => r.key));
      const add = rows.filter((r) => !existing.has(r.key));
      const next = [...before.constraints, ...add].slice(0, 10);
      record(
        `已采纳「世界铁律」${add.length} 条（${before.constraints.length} 条 → ${next.length} 条）`,
        () => setWorld((w) => ({ ...w, constraints: next })),
        () => setWorld((w) => ({ ...w, constraints: before.constraints })),
      );
    } else {
      const next = entry.value as string;
      const beforeText = before[key];
      record(
        beforeText
          ? `已采纳「${AI_CELL[key]}」，覆盖原内容（${beforeText.length} 字 → ${next.length} 字）`
          : `已采纳「${AI_CELL[key]}」（写入 ${next.length} 字）`,
        () => setWorld((w) => ({ ...w, [key]: next })),
        () => setWorld((w) => ({ ...w, [key]: beforeText })),
      );
    }
    toast.success("已采纳，落回对应格，可撤销或继续改");
  };

  useImperativeHandle(
    ref,
    () => ({
      save,
      markDirty,
      clearAi: () => {
        setSinks({});
        setCheck(null);
      },
      runAi: (key) => runAi(key),
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [save, runAi],
  );

  const noPower = world.no_power;

  if (loading) return <p className="opt">加载中…</p>;

  type WorldSinkKey = "stage" | "power" | "cost" | "factions" | "constraints";
  /** 体检项 → 补充目标格（项名与后端 CHECK_ITEMS_* 逐字对应）：告诉用户去哪个格子补内容 */
  const checkFixTarget = (name: string): string => {
    const map: Record<string, string> = {
      "简介 × 世界": "01 世界舞台",
      "题材 × 世界": "01 世界舞台",
      "力量与上限": "02 力量体系",
      "代价与边界": "03 力量的代价",
      "铁律 × 简介": "05 世界铁律",
      "势力立场": "04 势力",
      "历史自洽": "06 · 历史与旧账",
      "现实规则完备": "06 · 更多世界细节",
    };
    return map[name] || name;
  };

  /** 体检项 → AI 补：调用对应生成端点，结果落到对应格；账本类两项手动补 */
  const checkFixAi = (name: string) => {
    const map: Record<string, () => Promise<void>> = {
      "简介 × 世界": () => runAi("stage"),
      "题材 × 世界": () => runAi("stage"),
      "力量与上限": () => runAi("power"),
      "代价与边界": () => runAi("cost"),
      "铁律 × 简介": () => runAi("constraints"),
      "势力立场": () => runAi("factions"),
    };
    const fn = map[name];
    if (fn) void fn();
    else toast.info("该项需要你手动补充");
  };

  const sinkZone = (key: WorldSinkKey, label: string) => {
    const h = sinks[key];
    if (!h) return null;
    const entry = h.list[h.idx];
    return (
      <div className="ai-sink" data-ans-zone={key} aria-busy={runningKey === key}>
        <div className="aiz-head">AI 填 · {label}</div>
        {h.list.length > 1 && (
          <div className="aiz-hist" data-od-id="ai-sink-history">
            <span className="ah-t">最近 {h.list.length} 次</span>
            {h.list.map((_, i) => (
              <button
                key={i}
                type="button"
                className={`ah-chip${i === h.idx ? " on" : ""}`}
                data-hist={i}
                onClick={() => setSinks((prev) => prev[key] ? { ...prev, [key]: { ...prev[key], idx: i } } : prev)}
              >
                第 {i + 1} 次
              </button>
            ))}
            {h.list.length >= 5 && <span className="ah-t">（只保留最近 5 次）</span>}
          </div>
        )}
        <p style={{ margin: "4px 0" }}>{entry.txt}</p>
        <div className="ans-act">
          <button className="primary" type="button" onClick={() => adopt(key)}>
            采纳 · 覆盖
          </button>
          <button type="button" onClick={() => void runAi(key)}>重试</button>
        </div>
      </div>
    );
  };

  return (
    <div>
      {/* 01 世界舞台 */}
      <div className="mod" data-od-id="mod-base">
        <div className="mod-head">
          <span className="m-no">01</span>
          <span className="m-name">世界舞台</span>
          <span className="m-why">这是什么世界：定时代、选形态、圈出主要地点</span>
        </div>
        <div className="inherit-line" data-od-id="theme-inherit">
          {theme && (theme.theme || theme.sub) ? (
            <>
              <span className="badge ok">题材已确认</span>
              <span>
                舞台底色＝<b>{theme.theme}{theme.sub ? ` · ${theme.sub}` : ""}</b>
                （跟题材走，这里不再重复问；要换去左树「题材」）
              </span>
            </>
          ) : (
            <>
              <span className="badge warn">题材未确认</span>
              <span>先去题材页选底色，也可以先写世界</span>
            </>
          )}
        </div>
        <div className="field">
          <label>
            你的世界长什么样？
            <span className="hint">名称、时代、形态、主要地点，一段话立住</span>
          </label>
          <textarea
            className="textarea"
            rows={3}
            data-od-id="stage-input"
            value={world.stage}
            maxLength={300}
            placeholder="例：云梁界，古典王朝的修仙世界——故事集中在南境：青梧宗、柳安坊市、闭生死关的落霞谷；北境只闻其名，暂不出场"
            onChange={(e) => patch({ stage: e.target.value })}
          />
        </div>
        {sinkZone("stage", "世界舞台")}
      </div>

      {/* 02 力量体系 */}
      <div className="mod" data-od-id="mod-power">
        <div className="mod-head">
          <span className="m-no">02</span>
          <span className="m-name">力量体系</span>
          <span className="m-why">力量叫什么、分几级、怎么获得——上限要写死</span>
        </div>
        <div className="pwr-switch" data-od-id="no-power-switch">
          <button
            className="switch-btn"
            type="button"
            role="switch"
            aria-checked={noPower}
            data-od-id="no-power-btn"
            onClick={() => {
              const next = !noPower;
              const apply = () => patch({ no_power: next });
              record(
                next ? "已切到现实向：力量两格收起" : "已恢复超自然力量两格",
                apply,
                () => patch({ no_power: !next }),
              );
            }}
          >
            <span className="sw-track"><span className="sw-knob" /></span>
            <span className="sw-label">本书没有超自然力量（现实向）</span>
          </button>
          <span className="opt">开了之后力量两格收起，物理与法律规则在「更多世界细节」里补</span>
        </div>
        {!noPower && (
          <div className="field">
            <label>
              力量从哪来、分几级、上限在哪？
              <span className="hint">每级写边界，最强者尤其要写</span>
            </label>
            <textarea
              className="textarea"
              rows={3}
              data-od-id="power-text"
              value={world.power}
              maxLength={300}
              placeholder="例：灵力——修为靠功法传承，天生灵根者入门快；练气到元婴共九境，金丹可毁山、不可灭城，元婴全书不出三人"
              onChange={(e) => patch({ power: e.target.value })}
            />
          </div>
        )}
        {noPower && (
          <p className="opt">现实向 · 无超自然力量——物理与法律规则在「更多世界细节」里补即可。</p>
        )}
        {sinkZone("power", "力量体系")}
      </div>

      {/* 03 力量的代价 */}
      {!noPower && (
        <div className="mod" data-od-id="mod-cost">
          <div className="mod-head">
            <span className="m-no">03</span>
            <span className="m-name">力量的代价</span>
            <span className="m-why">用它要付什么：消耗、副作用、冷却、弱点</span>
          </div>
          <div className="field">
            <label>
              用它要付什么？有什么绝对不能碰的？
              <span className="hint">反例：一念毁城无消耗，冲突没得写；正例：改写他人记忆，代价是丢一段自己的</span>
            </label>
            <textarea
              className="textarea"
              rows={3}
              data-od-id="cost-input"
              value={world.cost}
              maxLength={300}
              placeholder="例：那双看穿修为漏洞的眼，每用一次自瞎一日，连用三次永久丢一段记忆；强行冲境会走火入魔，灵力枯竭仍施法，燃的是寿数"
              onChange={(e) => patch({ cost: e.target.value })}
            />
          </div>
          {sinkZone("cost", "力量的代价")}
        </div>
      )}

      {/* 04 势力 */}
      <div className="mod" data-od-id="mod-faction">
        <div className="mod-head">
          <span className="m-no">04</span>
          <span className="m-name">势力</span>
          <span className="m-why">谁和谁在争：先立两三个，各自想要什么、是敌是友</span>
        </div>
        <div className="fac-list">
          {world.factions.map((f, i) => (
            <div className="fac-row" key={i}>
              <input
                className="input fac-name"
                value={f.name}
                maxLength={20}
                placeholder="例：丹阁"
                onChange={(e) => {
                  const next = [...world.factions];
                  next[i] = { ...next[i], name: e.target.value };
                  patch({ factions: next });
                }}
              />
              <input
                className="input fac-goal"
                value={f.note}
                maxLength={200}
                placeholder="例：要为残卷讨一个说法，与青梧宗敌对"
                onChange={(e) => {
                  const next = [...world.factions];
                  next[i] = { ...next[i], note: e.target.value };
                  patch({ factions: next });
                }}
              />
              <button
                className="icon-btn"
                type="button"
                title="删除本行"
                aria-label="删除本行"
                onClick={() => patch({ factions: world.factions.filter((_, j) => j !== i) })}
              >
                <Ico d={P.trash} sw={1.7} />
              </button>
            </div>
          ))}
          {world.factions.length < 6 && (
            <button
              className="text-btn"
              type="button"
              data-od-id="fac-add"
              onClick={() => patch({ factions: [...world.factions, { name: "", note: "" }] })}
            >
              <Ico d={P.plus} sw={2} size={13} /> 加一个势力
            </button>
          )}
          {world.factions.length >= 4 && (
            <p className="opt">势力越多，冲突越难聚焦，建议 2-3 个。</p>
          )}
          {sinkZone("factions", "势力")}
        </div>
      </div>

      {/* 05 世界铁律 */}
      <div className="mod" data-od-id="mod-lock">
        <div className="mod-head">
          <span className="m-no">05</span>
          <span className="m-name">世界铁律</span>
          <span className="m-why">不许破的硬边界——想到哪条写哪条，也可以自己加</span>
        </div>
        <KvListEditor
          rows={world.constraints}
          onChange={(rows) => patch({ constraints: rows })}
          suggests={LOCK_SUGGESTS}
          keyPlaceholder="铁律名（≤10字）"
          valuePlaceholder="例：元婴老祖能移山填海，不能起死回生"
          addLabel="加一条铁律"
          maxItems={10}
        />
        {sinkZone("constraints", "世界铁律")}
        <p className="lock-note">确认后，写章 prompt 会逐条带上这些锁；体检也逐条对照。</p>
        {check && (
          <div className="ai-sink" data-od-id="world-check-result">
            <div className="aiz-head">AI 体检 · 简介 × 题材 × 世界</div>
            {check.items.map((item: WorldCheckItem) => (
              <div className="chk-line" key={item.name}>
                <span className="chk-name">{item.name}</span>
                <span className={`chk-res ${item.status}`}>
                  {item.status === "ok" ? "达标" : item.status === "warn" ? "风险" : "缺失"}
                </span>
                <span className="chk-note">{item.note}</span>
              </div>
            ))}
            {check.degraded && (
              <p className="opt">简介或题材还没写——相关行按缺失处理，补完再体检更准。</p>
            )}
            {/* 非达标项：提供"去补充"定位 + "AI 补"快捷按钮 */}
            {check.items.filter((i: any) => i.status !== "ok").map((item: any, idx: number) => (
              <div key={idx} className="chk-fix-row" data-od-id={`chk-fix-${idx}`}>
                <span className="opt">{item.name}需要补充</span>
                <span className="opt">→</span>
                <span className="opt">{checkFixTarget(item.name)}</span>
                <button
                  className="chk-fix-ai"
                  type="button"
                  onClick={() => checkFixAi(item.name)}
                  title={`AI 起草「${item.name}」的补充内容`}
                >
                  ✦ AI 起草
                </button>
              </div>
            ))}
            {check.verdict && <p className="opt">结论：{check.verdict}</p>}
            <div className="ans-act">
              <button className="primary" type="button" onClick={() => void runAi("check")}>
                重跑
              </button>
            </div>
          </div>
        )}
      </div>

      {/* 06 更多世界细节（可后补，折叠组） */}
      <details className="cfg" data-od-id="mod-extra">
        <summary>
          06 更多世界细节
          <span className="tag">可后补</span>
          <span className="chint">常用名目点一下就加一条，也能自己起名目——随归档持续生长</span>
          <svg className="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="13" height="13"><path d="m6 9 6 6 6-6" /></svg>
        </summary>
        <div className="inner">
          {pendingLore.length > 0 && (
            <div style={{ marginBottom: 12 }} data-od-id="lore-pending">
              <p className="opt" style={{ margin: "0 0 6px" }}>
                归档识别的世界要素建议——确认后入账（带章节来源）
              </p>
              {pendingLore.map((p, i) => (
                <div
                  key={`${p.origin}-${p.key}`}
                  style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4, flexWrap: "wrap" }}
                >
                  <span className="badge warn">{p.set}</span>
                  <span style={{ fontSize: 12.5 }}>
                    <b>{p.key}</b>：{p.value}
                    <span className="opt">（{p.origin}）</span>
                  </span>
                  <button
                    className="text-btn"
                    type="button"
                    data-od-id={`lore-adopt-${i}`}
                    onClick={async () => {
                      await worldLoreApply(projectId, [
                        { key: p.key, value: p.value, origin: p.origin, set: p.set },
                      ]);
                      const fresh = normalizeWorld(
                        await api.get(`/novels/${projectId}/settings/world`),
                      );
                      setWorld(fresh);
                      snapshotLoaded(fresh);
                      dropLoreSuggestion(projectId, p);
                      setPendingLore(getLoreSuggestions(projectId));
                      toast.success("已入账世界设定");
                    }}
                  >
                    采纳入账
                  </button>
                </div>
              ))}
            </div>
          )}
          <div className="field" style={{ marginBottom: 12 }}>
            <label>
              历史与旧账
              <span className="hint">「世界至今」活账本——创建期可空；写作期归档章节时 AI 会建议把世界级大事追加进来</span>
            </label>
            <KvListEditor
              rows={world.history}
              onChange={(rows) => patch({ history: rows })}
              suggests={HIST_SUGGESTS}
              keyPlaceholder="事件名（如：丹阁大火）"
              valuePlaceholder="时间 + 经过 + 留下的后果"
              addLabel="加一条大事"
              maxItems={100}
              rowOdId="hist-row"
            />
          </div>
          <div className="field">
            <label>
              更多名目<span className="hint">只挑剧情会用到的，其余不写</span>
            </label>
            <KvListEditor
              rows={world.extra}
              onChange={(rows) => patch({ extra: rows })}
              suggests={EXTRA_SUGGESTS}
              addLabel="加一条"
              maxItems={50}
              rowOdId="extra-row"
            />
          </div>
        </div>
      </details>
    </div>
  );
});

export default WorldSettingPanel;
