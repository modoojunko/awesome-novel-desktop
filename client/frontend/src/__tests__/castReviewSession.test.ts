// 精盘会话纯逻辑（c-character-intro 3.1 验证项）：会话恢复/换章清场/gapId 粒度/
// 降档裁剪/指纹失效；appendCastExclude cast 分型（勿走 DrawExcludeItem 过滤）。
import { beforeEach, describe, expect, it } from "vitest";
import {
  appendCastExclude,
  appendExclude,
  castInputFingerprint,
  clearCastSession,
  drawKey,
  loadCastSession,
  mergeCastGaps,
  pruneCastGap,
  saveCastSession,
  trimCastSessionForTier,
  type CastGapSession,
  type CastSession,
} from "@/lib/drawSession";
import { gapIdOf, castBackgroundLine, castChoice, verdictKind } from "@/lib/castReviewApi";

const gap = (anchor: string, over: Partial<CastGapSession> = {}): CastGapSession => ({
  anchor,
  choice: "加人",
  touched: false,
  status: "open",
  batches: [],
  exclude: [],
  ...over,
});

const card = (name: string) => ({
  axis: "身份",
  name,
  persona: "一句人设",
  entrance: "出场",
  exit_kind: "章内退场",
  exit_note: "退场",
  grade: "S",
  ranks: { 合不合适: 1, 差别在哪: 2, 好不好落地: 3 },
  reasons: { 合不合适: "a", 差别在哪: "b", 好不好落地: "c" },
});

beforeEach(() => localStorage.clear());

describe("cast 分型排除清单（appendCastExclude）", () => {
  it("axis/name/persona 三键都齐才算一条（DrawExcludeItem 的 axis+line 过滤会整批丢）", () => {
    const batch = [
      { axis: "身份", name: "魏七", persona: "笑面账精" },
      { axis: "关系", name: "灯伯", persona: "" }, // persona 空：丢
      { axis: "功能", name: "", persona: "船娘" }, // name 空：丢
    ];
    const out = appendCastExclude([], batch);
    expect(out).toHaveLength(1);
    expect(out[0].name).toBe("魏七");
    // 对照：既有过滤整批丢（cast 条目没有 line 键）
    expect(appendExclude([], batch as never)).toHaveLength(0);
  });

  it("保留最近 9 条", () => {
    const many = Array.from({ length: 12 }, (_, i) => ({
      axis: "身份",
      name: `n${i}`,
      persona: `p${i}`,
    }));
    const out = appendCastExclude([], many);
    expect(out).toHaveLength(9);
    expect(out[0].name).toBe("n3");
    expect(out[8].name).toBe("n11");
  });
});

describe("输入指纹（只盖剧情输入）", () => {
  it("plot_items＋留存格入指纹；characters 不入——落账写名字不失效", () => {
    const partial = {
      plot_items: ["甲", "乙"],
      challenge: "墙",
      plot_stage: "开局铺垫",
      ladder_exit: "落点",
      outline: { summary: "梗概", characters: ["林野"] },
    };
    const fp1 = castInputFingerprint(partial);
    // 落账写名字（characters 变）：指纹不变
    const fp2 = castInputFingerprint({
      ...partial,
      outline: { summary: "梗概", characters: ["林野", "魏七"] },
    });
    expect(fp2).toBe(fp1);
    // 剧情条目改了：指纹变（会话失效）
    expect(castInputFingerprint({ ...partial, plot_items: ["甲", "丙"] })).not.toBe(fp1);
    // 留存格改了：指纹变
    expect(castInputFingerprint({ ...partial, ladder_exit: "新落点" })).not.toBe(fp1);
    expect(castInputFingerprint({ ...partial, challenge: "新墙" })).not.toBe(fp1);
  });
});

describe("会话存取与清理", () => {
  const key = drawKey.cast("p1", "vol-1-ch-2");
  const session: CastSession = {
    fp: "fp1",
    review: { rows: [], quota: { named_count: 0, regime: "open" }, hints: [] },
    gaps: {
      "gap-2": gap("段二", { batches: [[card("魏七")]], exclude: [{ axis: "身份", name: "魏七", persona: "p" }] }),
      "gap-3": gap("段三", { batches: [[card("灯伯")]] }),
    },
  };

  it("换章清场：不同章不同键，互不可见", () => {
    saveCastSession(key, session);
    expect(loadCastSession(key)).not.toBeNull();
    expect(loadCastSession(drawKey.cast("p1", "vol-1-ch-3"))).toBeNull();
    expect(drawKey.cast("p1", "vol-1-ch-2")).toBe("cs-draw:p1:vol-1-ch-2");
  });

  it("gapId 粒度清理：写入落账/从头再来只清该缺口批次，其他缺口不动", () => {
    saveCastSession(key, session);
    pruneCastGap(key, "gap-2");
    const s = loadCastSession(key)!;
    expect(s.gaps["gap-2"].batches).toHaveLength(0);
    expect(s.gaps["gap-2"].exclude).toHaveLength(0);
    expect(s.gaps["gap-2"].status).toBe("open"); // 处理记录保留
    expect(s.gaps["gap-3"].batches).toHaveLength(1); // 其他缺口不动
  });

  it("全键清理只在全部处理完（clearCastSession）", () => {
    saveCastSession(key, session);
    clearCastSession(key);
    expect(loadCastSession(key)).toBeNull();
  });

  it("恢复按档位裁剪：免费档丢 cards 载荷（批次＋排除清单），三选一保留", () => {
    saveCastSession(key, session);
    const free = trimCastSessionForTier(loadCastSession(key)!, false);
    expect(free.gaps["gap-2"].batches).toHaveLength(0);
    expect(free.gaps["gap-2"].exclude).toHaveLength(0);
    expect(free.gaps["gap-2"].choice).toBe("加人");
    // 裁剪只在内存：磁盘批次还在（PRO 恢复不受影响）
    expect(loadCastSession(key)!.gaps["gap-2"].batches).toHaveLength(1);
    // PRO 原样
    expect(trimCastSessionForTier(loadCastSession(key)!, true).gaps["gap-2"].batches).toHaveLength(1);
  });

  it("损坏载荷不炸（loadCastSession 归 null）", () => {
    localStorage.setItem(key, JSON.stringify({ nope: 1 }));
    expect(loadCastSession(key)).toBeNull();
    localStorage.setItem(key, "{bad json");
    expect(loadCastSession(key)).toBeNull();
  });
});

describe("重新盘点按段 idx 对回合并", () => {
  it("段文本未变沿用处理记录与批次，段文本已变作废", () => {
    const prev = {
      "gap-2": gap("段二原文", {
        choice: "延后" as const,
        touched: true,
        status: "deferred" as const,
        batches: [[card("魏七")]],
      }),
      "gap-3": gap("段三原文", { batches: [[card("灯伯")]] }),
    };
    const next = {
      "gap-2": gap("段二原文"), // 未变：沿用
      "gap-3": gap("段三改过了"), // 已变：作废
      "gap-4": gap("新缺口"), // 新增
    };
    const merged = mergeCastGaps(prev, next);
    expect(merged["gap-2"].status).toBe("deferred");
    expect(merged["gap-2"].choice).toBe("延后");
    expect(merged["gap-2"].batches).toHaveLength(1);
    expect(merged["gap-3"].status).toBe("open");
    expect(merged["gap-3"].batches).toHaveLength(0);
    expect(merged["gap-4"].status).toBe("open");
  });
});

describe("闭集与拼句（前端侧口径）", () => {
  it("gapId=f(段 idx)，退化整章行锚 chapter", () => {
    expect(gapIdOf(2)).toBe("gap-2");
    expect(gapIdOf(null)).toBe("gap-chapter");
  });

  it("suggest 归一只认三值；出界缺省加人（defaulted 由响应带）", () => {
    expect(castChoice("加人")).toBe("加人");
    expect(castChoice("改段")).toBe("改段");
    expect(castChoice("延后")).toBe("延后");
    expect(castChoice("加人或改段")).toBe("加人");
    expect(castChoice("")).toBe("加人");
  });

  it("verdict 三分类归一（未知值=没判出来）", () => {
    expect(verdictKind("老角色能演")).toBe("old");
    expect(verdictKind("不起名也行")).toBe("unnamed");
    expect(verdictKind("缺一个新角色")).toBe("new");
    expect(verdictKind("缺一个新角色。")).toBe("unknown");
  });

  it("建卡 background 拼句（怎么出场＋怎么退场档值原文拍平）", () => {
    expect(
      castBackgroundLine({ entrance: "巷口拦人", exitKind: "本卷退场", exitNote: "卖错主顾" }),
    ).toBe("怎么出场：巷口拦人；怎么退场（本卷退场）：卖错主顾");
    expect(castBackgroundLine({ entrance: "", exitKind: "", exitNote: "" })).toBe("");
  });
});
