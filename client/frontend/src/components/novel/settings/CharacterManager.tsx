// 角色面板（character-settings-v2）：真表 API + 分组列表 + 卷宗人物卡 + 单向关系
// + 删除/合并（L3 名称输入确认）+ 单格自动保存（防抖 + 串行队列 + rev 冲突 409 处理）
// + 右栏 AI 经 SettingsView 分发（本组件暴露 runAi/clearAi 句柄）。
import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import { charactersApi, CharacterCard } from "@/lib/charactersApi";
import { COG_LAYERS, DOSSIER_FIELDS, ROLES } from "@/lib/characterModel";
import { Ico } from "@/components/icons";

interface Props {
  projectId: string;
  /** P2-1：脏状态回调（有未落库修改时 true） */
  onDirtyChange?: (dirty: boolean) => void;
}

interface SaveHandle {
  save: () => Promise<boolean>;
  /** 兼容 SettingSaveHandle 可选成员 */
  clearAi?: () => void;
  runAi?: (key: string) => Promise<void>;
}

type SaveState = "saved" | "saving" | "dirty" | "failed";

interface AiSink {
  target?: string;
  cells: { path: string; value: string }[];
  skipped?: { key: string; why: string }[];
  act: "insert" | "replace";
}

interface CheckResult {
  items: { name: string; status: "ok" | "warn" | "conflict" | "miss"; note: string; goto?: string }[];
  degraded: boolean;
  degraded_reasons: string[];
  verdict: string;
}

const GROUPS = ROLES;

const CharacterManager = forwardRef<SaveHandle, Props>(function CharacterManager(
  props,
  ref,
) {
  const { projectId, onDirtyChange } = props;
  const [list, setList] = useState<CharacterCard[]>([]);
  const [gate, setGate] = useState<{ ok: boolean; no_protagonist: boolean; confirmed: boolean }>({
    ok: false, no_protagonist: true, confirmed: false,
  });
  const [selectedId, setSelectedId] = useState("");
  const [card, setCard] = useState<CharacterCard | null>(null);
  const [groupsOpen, setGroupsOpen] = useState<Record<string, boolean>>({
    "\u4e3b\u89d2": true, "\u914d\u89d2": true, "\u53cd\u6d3e": true, "\u8def\u4eba": false,
  });
  const [query, setQuery] = useState("");
  const [saveState, setSaveState] = useState<SaveState>("saved");
  const [opsPanel, setOpsPanel] = useState<"" | "del" | "merge">("");
  const [opsName, setOpsName] = useState("");
  const [mergeTarget, setMergeTarget] = useState("");
  const [cogOpen, setCogOpen] = useState<Record<string, boolean>>({});
  const [relForm, setRelForm] = useState(false);
  const [relDraft, setRelDraft] = useState({ other: "", rel_type: "\u540c\u76df", stance: "", note: "" });
  const [sink, setSink] = useState<AiSink | null>(null);
  const [check, setCheck] = useState<CheckResult | null>(null);
  const [aiBusy, setAiBusy] = useState(false);
  const [toast, setToast] = useState("");

  const queueRef = useRef<{ path: string; value: unknown }[]>([]);
  const runningRef = useRef(false);
  const revRef = useRef(1);
  const timerRef = useRef<number | null>(null);
  const selectedIdRef = useRef("");
  const [dirty, setDirty] = useState(false);
  const markDirty = useCallback(() => setDirty(true), []);
  const clearDirty = useCallback(() => setDirty(false), []);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(""), 2600);
  }, []);

  const reloadList = useCallback(async (): Promise<CharacterCard[]> => {
    const data = await charactersApi.list(projectId);
    setList(data.items);
    setGate({ ok: data.gate.ok, no_protagonist: data.gate.no_protagonist, confirmed: data.confirmed });
    return data.items;
  }, [projectId]);

  const loadCard = useCallback(async (id: string) => {
    const full = await charactersApi.get(projectId, id);
    setCard(full);
    revRef.current = full.rev;
    setSaveState("saved");
    clearDirty();
    onDirtyChange?.(false);
    setSink(null);
    setCheck(null);
  }, [projectId, clearDirty, onDirtyChange]);

  useEffect(() => {
    (async () => {
      try {
        const items = await reloadList();
        if (items.length) {
          selectedIdRef.current = items[0].id;
          setSelectedId(items[0].id);
          await loadCard(items[0].id);
        }
      } catch {
        showToast("\u89d2\u8272\u52a0\u8f7d\u5931\u8d25\uff0c\u8bf7\u5237\u65b0\u91cd\u8bd5");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const flushQueue = useCallback(async () => {
    if (runningRef.current || queueRef.current.length === 0 || !card) return;
    runningRef.current = true;
    setSaveState("saving");
    try {
      while (queueRef.current.length > 0) {
        const next = queueRef.current.shift()!;
        await charactersApi.patch(projectId, card.id, next.path, next.value, revRef.current);
        revRef.current += 1;
      }
      setSaveState("saved");
      clearDirty();
      onDirtyChange?.(false);
    } catch (e) {
      const err = e as Error & { status?: number; field?: string; rev?: number };
      if (err.status === 409 && err.rev !== undefined) {
        revRef.current = err.rev;
        setSaveState("dirty");
        showToast("\u8fd9\u4e00\u683c\u5df2\u88ab\u5176\u5b83\u6539\u52a8\u66f4\u65b0\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5");
      } else {
        setSaveState("failed");
        showToast("\u81ea\u52a8\u4fdd\u5b58\u5931\u8d25\u2014\u2014\u8bf7\u68c0\u67e5\u7f51\u7edc\u540e\u91cd\u8bd5");
      }
    } finally {
      runningRef.current = false;
      if (queueRef.current.length > 0) void flushQueue();
    }
  }, [card, projectId, clearDirty, onDirtyChange, showToast]);

  const enqueue = useCallback(
    (path: string, value: unknown) => {
      queueRef.current = queueRef.current.filter((p) => p.path !== path);
      queueRef.current.push({ path, value });
      markDirty();
      onDirtyChange?.(true);
      setSaveState("dirty");
      if (timerRef.current) window.clearTimeout(timerRef.current);
      timerRef.current = window.setTimeout(() => void flushQueue(), 600);
    },
    [flushQueue, markDirty, onDirtyChange],
  );

  const setField = useCallback(
    (path: string, value: unknown) => {
      setCard((prev) => {
        if (!prev) return prev;
        const next: CharacterCard = { ...prev };
        if (path.includes(".")) {
          const [bucket, key] = path.split(".") as ["dossier" | "cog", string];
          next[bucket] = { ...prev[bucket], [key]: String(value) };
        } else {
          (next as unknown as Record<string, unknown>)[path] = value;
        }
        return next;
      });
      enqueue(path, value);
    },
    [enqueue],
  );

  useImperativeHandle(ref, () => ({
    save: async () => {
      if (timerRef.current) window.clearTimeout(timerRef.current);
      await flushQueue();
      return queueRef.current.length === 0 && saveState !== "failed";
    },
    clearAi: () => {
      setSink(null);
      setCheck(null);
    },
    runAi: async (key: string) => {
      if (aiBusy || !card) return;
      setAiBusy(true);
      const cardId = card.id;
      try {
        if (key === "check") {
          const res = await charactersApi.aiCheck(projectId, cardId);
          if (selectedIdRef.current === cardId) setCheck(res);
        } else {
          const res = await charactersApi.aiDraft(projectId, cardId, key as "persona" | "dossier" | "cog");
          if (selectedIdRef.current === cardId) setSink(res);
        }
      } catch (e) {
        showToast((e as Error).message || "AI \u751f\u6210\u5931\u8d25\uff0c\u53ef\u91cd\u8bd5");
      } finally {
        setAiBusy(false);
      }
    },
  }));

  const pick = useCallback(
    async (id: string) => {
      if (id === selectedIdRef.current) return;
      if (timerRef.current) window.clearTimeout(timerRef.current);
      await flushQueue();
      selectedIdRef.current = id;
      setSelectedId(id);
      setOpsPanel("");
      setRelForm(false);
      setCogOpen({});
      await loadCard(id);
    },
    [flushQueue, loadCard],
  );

  const addCharacter = useCallback(async () => {
    try {
      const created = await charactersApi.create(projectId, "");
      await reloadList();
      selectedIdRef.current = created.id;
      setSelectedId(created.id);
      setOpsPanel("");
      setRelForm(false);
      await loadCard(created.id);
      showToast("\u540d\u5b57\u4e00\u5199\u5c31\u51fa\u73b0\u5728\u5de6\u8fb9\u5217\u8868");
    } catch (e) {
      showToast((e as Error).message || "\u521b\u5efa\u5931\u8d25");
    }
  }, [projectId, reloadList, loadCard, showToast]);

  const adoptSink = useCallback(async () => {
    if (!sink || !card) return;
    try {
      for (const cell of sink.cells) {
        await charactersApi.patch(projectId, card.id, cell.path, cell.value, revRef.current);
        revRef.current += 1;
      }
      setSink(null);
      await loadCard(card.id);
      await reloadList();
      showToast("\u5df2\u91c7\u7eb3\uff0c\u53ef\u7ee7\u7eed\u6539");
    } catch (e) {
      showToast((e as Error).message || "\u91c7\u7eb3\u5931\u8d25");
    }
  }, [sink, card, projectId, loadCard, reloadList, showToast]);

  const doDelete = useCallback(async () => {
    if (!card) return;
    try {
      const res = await charactersApi.remove(projectId, card.id);
      await reloadList();
      const rest = (await charactersApi.list(projectId)).items;
      if (rest.length) {
        selectedIdRef.current = rest[0].id;
        setSelectedId(rest[0].id);
        await loadCard(rest[0].id);
      } else {
        setCard(null);
      }
      setOpsPanel("");
      showToast(res.receipt);
    } catch (e) {
      showToast((e as Error).message || "\u5220\u9664\u5931\u8d25");
    }
  }, [card, projectId, reloadList, loadCard, showToast]);

  const doMerge = useCallback(async () => {
    if (!card || !mergeTarget) return;
    try {
      const res = await charactersApi.merge(projectId, card.id, mergeTarget);
      await reloadList();
      selectedIdRef.current = mergeTarget;
      setSelectedId(mergeTarget);
      await loadCard(mergeTarget);
      setOpsPanel("");
      showToast(res.receipt);
    } catch (e) {
      showToast((e as Error).message || "\u5408\u5e76\u5931\u8d25");
    }
  }, [card, mergeTarget, projectId, reloadList, loadCard, showToast]);

  const q = query.trim();
  const grouped = GROUPS.map((role) => ({
    role,
    items: list.filter(
      (c) => c.role === role && (!q || c.name.includes(q) || c.aliases.some((a) => a.includes(q))),
    ),
  }));
  const sealChar = card?.name?.trim()?.[0] ?? "\uff1f";

  return (
    <div className="sub-wrap">
      <nav className="sub-list char-list" aria-label="角色列表">
        <div className="sub-list-head">
          角色列表
          <span style={{ marginLeft: "auto", fontSize: 10.5, color: "var(--muted)" }}>{list.length}</span>
        </div>
        <button type="button" className="char-add" onClick={() => void addCharacter()}>
          <Ico d="plus" size={13} /> 添加角色
        </button>
        <input
          className="char-search"
          type="search"
          placeholder="搜名字 / 别名"
          aria-label="搜索角色"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className="char-groups">
          {grouped.map(({ role, items }) =>
            q && !items.length ? null : (
              <div key={role} className={`char-group${groupsOpen[role] ? " open" : ""}`}>
                <button
                  type="button"
                  className="char-group-head"
                  onClick={() => setGroupsOpen((g) => ({ ...g, [role]: !g[role] }))}
                >
                  <span className="nm">{role}</span>
                  <span className="cnt">{items.length}</span>
                </button>
                {groupsOpen[role] && (
                  <div className="char-rows">
                    {items.map((c) => (
                      <button
                        key={c.id}
                        type="button"
                        className={`char-row-btn${selectedId === c.id ? " on" : ""}`}
                        onClick={() => void pick(c.id)}
                      >
                        <i className="char-ava">{c.name?.[0] ?? "？"}</i>
                        <span className="char-row-main">
                          <span className="nm">{c.name || "未命名"}</span>
                          <span className="sub">{c.code}</span>
                        </span>
                        {c.role === "主角" && (!c.name || !c.persona) && (
                          <span className="pill pill-warn">待立</span>
                        )}
                      </button>
                    ))}
                    {!items.length && <span className="opt">空</span>}
                  </div>
                )}
              </div>
            ),
          )}
        </div>
      </nav>

      <div className="sub-form char-main">
        {!card ? (
          <p className="opt">左侧添加或选择一个角色。</p>
        ) : (
          <>
            <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 6 }}>
              <span className={`char-save-state ${saveState}`}>
                {saveState === "saving" && "保存中…"}
                {saveState === "saved" && "已自动保存"}
                {saveState === "dirty" && "有未保存修改"}
                {saveState === "failed" && "保存失败 · 请重试"}
              </span>
            </div>

            <header className="char-head">
              <span className="char-seal">{sealChar}</span>
              <div className="char-idblock">
                <div className="char-name-row">
                  <input
                    className="char-name-input"
                    value={card.name}
                    placeholder="姓名 / 称号"
                    aria-label="角色名称"
                    onChange={(e) => setField("name", e.target.value)}
                  />
                  <span role="group" aria-label="角色类型" style={{ display: "inline-flex", gap: 6 }}>
                    {ROLES.map((role) => (
                      <button
                        key={role}
                        type="button"
                        className={`chip${card.role === role ? " on" : ""}`}
                        onClick={() => setField("role", role)}
                      >
                        {role}
                      </button>
                    ))}
                  </span>
                </div>
                <input
                  className="char-alias-input"
                  value={card.aliases.join(" · ")}
                  placeholder="别名 / 称号（可选）"
                  aria-label="别名"
                  onChange={(e) =>
                    setField("aliases", e.target.value.split("·").map((s) => s.trim()).filter(Boolean))
                  }
                />
                <div className="char-meta">{card.code} · 修订 r{card.rev}</div>
              </div>
              <div className="char-side">
                <span className={`badge ${card.role === "主角" ? (card.name && card.persona ? "ok" : "warn") : "empty"}`}>
                  {card.role === "主角" ? (card.name && card.persona ? "已立主角" : "主角待立") : card.role}
                </span>
                <div className="char-ops">
                  <button type="button" onClick={() => { setOpsPanel(opsPanel === "merge" ? "" : "merge"); setOpsName(""); }}>合并…</button>
                  <button type="button" onClick={() => { setOpsPanel(opsPanel === "del" ? "" : "del"); setOpsName(""); }}>删除</button>
                </div>
              </div>
            </header>

            {opsPanel === "del" && (
              <div className="char-ops-panel danger">
                <span className="op-t">
                  删除《{card.name || "未命名"}》？相关关系会一并移除。
                  {card.role === "主角" && " 主角位会空出来。"}
                  删错了可撤销——撤销保留到你继续编辑或刷新之前。
                </span>
                <input
                  placeholder={`输入「${card.name || "未命名"}」以确认`}
                  aria-label="输入角色名以确认"
                  value={opsName}
                  onChange={(e) => setOpsName(e.target.value)}
                />
                <button
                  type="button"
                  className="btn btn-danger"
                  disabled={opsName.trim() !== (card.name || "未命名")}
                  onClick={() => void doDelete()}
                >
                  删除
                </button>
                <button type="button" className="btn btn-secondary" onClick={() => setOpsPanel("")}>取消</button>
              </div>
            )}
            {opsPanel === "merge" && (
              <div className="char-ops-panel">
                <span className="op-t">
                  把《{card.name || "未命名"}》并到另一张卡：<b>那张卡写过的不动，空格用这张补上</b>。可撤销。
                </span>
                <select aria-label="合并到哪张卡" value={mergeTarget} onChange={(e) => setMergeTarget(e.target.value)}>
                  <option value="">合并到…</option>
                  {list.filter((x) => x.id !== card.id).map((x) => (
                    <option key={x.id} value={x.id}>{x.name || "未命名"} · {x.code}</option>
                  ))}
                </select>
                <input
                  placeholder={`输入「${card.name || "未命名"}」以确认`}
                  aria-label="输入角色名以确认"
                  value={opsName}
                  onChange={(e) => setOpsName(e.target.value)}
                />
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={!mergeTarget || opsName.trim() !== (card.name || "未命名")}
                  onClick={() => void doMerge()}
                >
                  合并
                </button>
                <button type="button" className="btn btn-secondary" onClick={() => setOpsPanel("")}>取消</button>
              </div>
            )}

            <div className="char-persona">
              <span className="char-persona-label">一句话人设 · 每章都会带上这张卡的这句</span>
              <textarea
                rows={2}
                value={card.persona}
                placeholder="此人是谁、凭什么是他"
                aria-label="一句话人设"
                onChange={(e) => setField("persona", e.target.value)}
              />
            </div>

            {sink && (
              <div className="ai-sink" role="status">
                <div className="aiz-head">AI 生成 · 采纳才写入</div>
                {sink.cells.map((cell) => (
                  <div key={cell.path} className="aiz-line">
                    <span className="aiz-k">{cell.path}</span>
                    <span className="aiz-v">{cell.value}</span>
                  </div>
                ))}
                {sink.skipped?.map((s) => (
                  <div key={s.key} className="opt">跳过 {s.key}：{s.why}</div>
                ))}
                <div className="ans-act">
                  <button type="button" className="btn btn-primary" onClick={() => void adoptSink()}>采纳 · 写入</button>
                  <button type="button" className="btn btn-secondary" onClick={() => setSink(null)}>放弃</button>
                </div>
              </div>
            )}

            <section className="sec">
              <header className="sec-h">
                <h3>基础档案</h3>
                <span className="sec-sub">写每一章都用得上的硬信息——点一下就能改。</span>
              </header>
              <div>
                <div className="char-dossier-row">
                  <span className="char-dossier-k">性别 · 年龄 · 种族</span>
                  <span className="char-dossier-v char-tri">
                    <input value={card.dossier.gender ?? ""} placeholder="性别" aria-label="性别" onChange={(e) => setField("dossier.gender", e.target.value)} />
                    <input value={card.dossier.age ?? ""} placeholder="年龄" aria-label="年龄" onChange={(e) => setField("dossier.age", e.target.value)} />
                    <input value={card.dossier.race ?? ""} placeholder="种族" aria-label="种族" onChange={(e) => setField("dossier.race", e.target.value)} />
                  </span>
                </div>
                <div className="char-dossier-row">
                  <span className="char-dossier-k">势力 · 身份</span>
                  <span className="char-dossier-v">
                    <input value={card.dossier.faction ?? ""} placeholder="例：青梧宗外门 · 杂役弟子" aria-label="势力·身份" onChange={(e) => setField("dossier.faction", e.target.value)} />
                  </span>
                </div>
                <div className="char-dossier-row">
                  <span className="char-dossier-k">外貌标签</span>
                  <span className="char-dossier-v">
                    <input value={card.dossier.look ?? ""} placeholder="例：瘦长个 · 旧道袍" aria-label="外貌标签" onChange={(e) => setField("dossier.look", e.target.value)} />
                  </span>
                </div>
                <div className="char-dossier-row">
                  <span className="char-dossier-k">语言特征</span>
                  <span className="char-dossier-v">
                    <input value={card.dossier.speech ?? ""} placeholder="例：说话慢半拍 · 口头禅" aria-label="语言特征" onChange={(e) => setField("dossier.speech", e.target.value)} />
                  </span>
                </div>
                <div className="char-dossier-row">
                  <span className="char-dossier-k">背景</span>
                  <span className="char-dossier-v">
                    <textarea rows={1} value={card.dossier.background ?? ""} placeholder="出身与来路" aria-label="背景" onChange={(e) => setField("dossier.background", e.target.value)} />
                  </span>
                </div>
                <div className="char-dossier-row">
                  <span className="char-dossier-k">剧情定位 <i className="req">必填</i></span>
                  <span className="char-dossier-v">
                    <input value={card.dossier.plot ?? ""} placeholder="在故事里干什么——主角必填" aria-label="剧情定位" onChange={(e) => setField("dossier.plot", e.target.value)} />
                  </span>
                </div>
              </div>
            </section>

            <section className="sec">
              <header className="sec-h">
                <h3>人物关系</h3>
                <span className="sec-sub">只记这个角色怎么看别人——同一对方一条。</span>
                <button type="button" className="text-btn" onClick={() => setRelForm((v) => !v)}>＋记一段关系</button>
              </header>
              <div>
                {(card.relations ?? []).map((rel) => (
                  <div key={rel.id} className="rel-row-item">
                    <div className="rel-line">
                      <span className="rel-who">
                        <span className="pill pill-status">{rel.rel_type}</span>
                        <span className="rel-other-name">{rel.other_name || rel.other_id.slice(0, 8)}</span>
                      </span>
                      <span className="rel-note">
                        {rel.stance}
                        {rel.stance && rel.note ? "——" : ""}
                        {rel.note}
                      </span>
                      {rel.ch_ref && <span className="rel-meta">记于 {rel.ch_ref}</span>}
                      <span className="rel-acts">
                        <button
                          type="button"
                          onClick={() => {
                            setRelForm(true);
                            setRelDraft({ other: rel.other_id, rel_type: rel.rel_type, stance: rel.stance, note: rel.note });
                          }}
                        >
                          编辑
                        </button>
                        <button
                          type="button"
                          onClick={() =>
                            void charactersApi
                              .deleteRelation(projectId, card.id, rel.other_id)
                              .then(() => loadCard(card.id))
                          }
                        >
                          删除
                        </button>
                      </span>
                    </div>
                  </div>
                ))}
                {!card.relations?.length && (
                  <p className="opt">还没有关系记录——遇到值得记的人，点「＋记一段关系」。</p>
                )}
              </div>
              {relForm && (
                <div className="rel-form-inline">
                  <select
                    aria-label="对方角色"
                    value={relDraft.other}
                    onChange={(e) => setRelDraft((d) => ({ ...d, other: e.target.value }))}
                  >
                    <option value="">选对方…</option>
                    {list.filter((x) => x.id !== card.id).map((x) => (
                      <option key={x.id} value={x.id}>{x.name || "未命名"}</option>
                    ))}
                  </select>
                  <select
                    aria-label="关系类型"
                    value={relDraft.rel_type}
                    onChange={(e) => setRelDraft((d) => ({ ...d, rel_type: e.target.value }))}
                  >
                    {["父子", "母女", "兄弟", "姐妹", "血亲", "师徒", "同门", "举荐", "同盟", "友好", "主仆", "上下级", "竞争", "纵容", "管束", "恩情", "亏欠", "敌对", "仇人", "畏惧"].map((t) => (
                      <option key={t}>{t}</option>
                    ))}
                  </select>
                  <input placeholder="一句立场" aria-label="立场" value={relDraft.stance} onChange={(e) => setRelDraft((d) => ({ ...d, stance: e.target.value }))} />
                  <input placeholder="一句说明" aria-label="关系说明" value={relDraft.note} onChange={(e) => setRelDraft((d) => ({ ...d, note: e.target.value }))} />
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={async () => {
                      if (!relDraft.other) {
                        showToast("先选对方");
                        return;
                      }
                      try {
                        await charactersApi.upsertRelation(projectId, card.id, relDraft.other, {
                          rel_type: relDraft.rel_type,
                          stance: relDraft.stance,
                          note: relDraft.note,
                        });
                        setRelForm(false);
                        await loadCard(card.id);
                      } catch (e) {
                        showToast((e as Error).message || "保存失败");
                      }
                    }}
                  >
                    记下
                  </button>
                  <button type="button" className="btn btn-secondary" onClick={() => setRelForm(false)}>取消</button>
                </div>
              )}
            </section>

            <section className="sec">
              <header className="sec-h">
                <h3>认知内核</h3>
                <span className="sec-sub">六层是一条链：世界观 → 自我观 → 价值观 → 能力 → 行为 → 环境。</span>
              </header>
              {check && (
                <div className="ai-sink" role="status">
                  <div className="aiz-head">AI 体检 · {check.verdict || "逐项结论"}</div>
                  {check.items.map((item) => (
                    <div key={item.name} className="chk-row">
                      <span className="chk-name">{item.name}</span>
                      <span className={`chk-res ${item.status}`}>
                        {item.status === "ok" ? "达标" : item.status === "warn" ? "风险" : item.status === "conflict" ? "矛盾" : "缺输入"}
                      </span>
                      <span className="chk-note">{item.note}</span>
                      {item.goto?.startsWith("layer:") && (
                        <button
                          type="button"
                          className="chk-go"
                          onClick={() => setCogOpen((m) => ({ ...m, [item.goto!.split(":")[1]]: true }))}
                        >
                          去改
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
              <div className="char-cog">
                {COG_LAYERS.map((layer) => {
                  const open = !!cogOpen[layer.id];
                  const filledCount = layer.fields.filter((f) => String(card.cog[f.k] ?? "").trim()).length;
                  const missingReq = layer.fields.filter((f) => f.req && !String(card.cog[f.k] ?? "").trim());
                  const primary = card.cog[layer.primary] ?? "";
                  return (
                    <article
                      key={layer.id}
                      className={`cog-layer${open ? " open" : ""}${missingReq.length ? " missing" : filledCount ? " filled" : ""}`}
                    >
                      <button
                        type="button"
                        className="cog-layer-head"
                        onClick={() => setCogOpen((m) => ({ ...m, [layer.id]: !m[layer.id] }))}
                      >
                        <span className="cog-layer-no">{layer.no}</span>
                        <span className="cog-layer-name">{layer.name}</span>
                        <span className="cog-layer-tag">{layer.tag}</span>
                        <span className={`cog-layer-prev${primary ? " has" : ""}`}>
                          {primary || "还没写——展开补这一层的核心一句"}
                        </span>
                        {missingReq.length ? (
                          <span className="cog-layer-miss">还差 {missingReq.length} 项必填</span>
                        ) : (
                          <span className="cog-layer-state">{filledCount}/{layer.fields.length}</span>
                        )}
                      </button>
                      {open && (
                        <div className="cog-layer-grid">
                          {layer.fields.map((f) => (
                            <div key={f.k} className={`cog-field${f.k === layer.primary ? " full" : ""}`}>
                              <div className="f-label">
                                <b>
                                  {f.label}
                                  {f.req && <i className="req">必填</i>}
                                </b>
                              </div>
                              <input
                                value={card.cog[f.k] ?? ""}
                                aria-label={f.label}
                                onChange={(e) => setField(`cog.${f.k}`, e.target.value)}
                              />
                            </div>
                          ))}
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>
            </section>

            {toast && <p className="opt" role="status">{toast}</p>}
          </>
        )}
      </div>
    </div>
  );
});

export default CharacterManager;
