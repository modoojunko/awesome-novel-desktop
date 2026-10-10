// c-char-batch-import：characterImport 纯函数矩阵（列头识别/行级校验/护栏/模版同源契约）。
import { describe, expect, it } from "vitest";
import * as XLSX from "xlsx";
import { sheetToGrid as sheetToGridSync } from "@/lib/characterImport";
import {
  BATCH_MAX_ROWS,
  IMPORT_FIELD_GUIDE,
  IMPORT_FIELD_NOTES,
  TEMPLATE_HEADERS,
  buildTemplateWorkbook,
  decodeMaybeGbk,
  effectiveRole,
  gridToRows,
  normalizeHeaderKey,
  normalizeItem,
  readFileAsRows,
  rowStatus,
  sheetToGrid,
  statusContext,
} from "@/lib/characterImport";

function csvFile(name: string, content: string, sizeOverride?: number): File {
  const bytes = new TextEncoder().encode(content);
  const f = new File([bytes as unknown as BlobPart], name, { type: "text/csv" });
  if (sizeOverride !== undefined) Object.defineProperty(f, "size", { value: sizeOverride });
  Object.defineProperty(f, "arrayBuffer", { value: async () => bytes.buffer.slice(0) });
  return f;
}

describe("normalizeHeaderKey", () => {
  it("中英文键与变体都识别，未知列返回 null", () => {
    expect(normalizeHeaderKey("名字*")).toBe("name");
    expect(normalizeHeaderKey(" name ")).toBe("name");
    expect(normalizeHeaderKey("别名(用·分隔)")).toBe("aliases");
    expect(normalizeHeaderKey("别名（用·分隔）")).toBe("aliases");
    expect(normalizeHeaderKey("别名 трубка")).toBe("aliases"); // startsWith("别名") 前缀兜底
    expect(normalizeHeaderKey("势力·身份")).toBe("faction");
    expect(normalizeHeaderKey("剧情定位")).toBe("plot");
    expect(normalizeHeaderKey("备注")).toBeNull();
  });
});

describe("normalizeItem / effectiveRole", () => {
  it("clamp 与别名拆分在归一化收口", () => {
    const row = normalizeItem({
      name: "x".repeat(60),
      role: "配角",
      persona: "p".repeat(400),
      aliases: [" a ", "", "b"],
      dossier: { gender: " 女 ", look: "l".repeat(400), nope: "x" },
    });
    expect(row.name.length).toBe(50);
    expect(row.persona.length).toBe(300);
    expect(row.aliases).toEqual(["a", "b"]);
    expect(row.dossier.gender).toBe("女");
    expect(row.dossier.look.length).toBe(300);
    expect("nope" in row.dossier).toBe(false);
  });
  it("类型非法/缺失回落配角（弹窗无默认类型选择器的拍板）", () => {
    expect(effectiveRole({ name: "a", role: "", persona: "", aliases: [], dossier: {} })).toBe("配角");
    expect(effectiveRole({ name: "a", role: "龙套", persona: "", aliases: [], dossier: {} })).toBe("配角");
    expect(effectiveRole({ name: "a", role: "反派", persona: "", aliases: [], dossier: {} })).toBe("反派");
  });
  it("防御形态：dossier 非对象、别名单串/缺省、行对象缺省", () => {
    expect(normalizeItem({ name: "a", dossier: "x" }).dossier).toEqual({});
    expect(normalizeItem({ name: "a", aliases: "老柳" }).aliases).toEqual(["老柳"]);
    expect(normalizeItem({ name: "a" }).aliases).toEqual([]);
    expect(normalizeItem(undefined).name).toBe("");
  });
  it("稀疏行（cells 短于列头）按缺格处理", () => {
    const rows = gridToRows(["名字*", "类型", "一句话人设"], [["甲"], ["乙", "配角", "人设一句"]]);
    expect(rows[0]).toMatchObject({ name: "甲", role: "" });
    expect(rows[1]).toMatchObject({ name: "乙", role: "配角", persona: "人设一句" });
  });
});

describe("rowStatus", () => {
  const base = { name: "甲", role: "配角", persona: "", aliases: [] as string[], dossier: {} };
  const rows = [base, { ...base, name: "乙", role: "主角" }, { ...base, name: "甲" }];
  const ctx = statusContext(rows, { existingNames: new Set(["丙"]), hasProtagonist: true });

  it("示例行防呆：标黄不计数", () => {
    expect(rowStatus({ ...base, name: "示例-韩十三" }, 0, ctx)).toMatchObject({ cls: "warn", ok: false });
  });
  it("空名/超长名标红", () => {
    expect(rowStatus({ ...base, name: "" }, 0, ctx)).toMatchObject({ cls: "err" });
    expect(rowStatus({ ...base, name: "名".repeat(51) }, 0, ctx)).toMatchObject({ cls: "err" });
  });
  it("库内重名与批内重名都跳过（批内保留首个）", () => {
    expect(rowStatus({ ...base, name: "丙" }, 0, ctx)).toMatchObject({ cls: "warn", text: "已有同名，跳过" });
    expect(rowStatus(rows[0], 0, ctx)).toMatchObject({ cls: "ok" });
    expect(rowStatus(rows[2], 2, ctx)).toMatchObject({ cls: "warn", text: "批内重名，跳过" });
  });
  it("多主角标红（批内互相叠加＋库内已有主角）", () => {
    // 库内已有主角：批内第 1 个主角也拦
    expect(rowStatus(rows[1], 1, ctx)).toMatchObject({ cls: "err", text: "每书一位主角" });
  });
  it("有效行带别名/档案徽标", () => {
    const st = rowStatus({ ...base, aliases: ["a"], dossier: { gender: "女" } }, 0, {
      ...ctx,
      rows: [{ ...base, aliases: ["a"], dossier: { gender: "女" } }],
    });
    expect(st).toMatchObject({ cls: "ok", text: "将新建 · 别名×1 · 含档案" });
  });
});

describe("模版构建 → 回读（同源契约）", () => {
  it("双 sheet、中文列头序、填写说明与 IMPORT_FIELD_GUIDE 逐字一致", async () => {
    const wb = await buildTemplateWorkbook();
    expect(wb.SheetNames).toEqual(["角色", "填写说明"]);
    const grid = XLSX.utils.sheet_to_json<unknown[]>(wb.Sheets["角色"], { header: 1, raw: false, defval: "" });
    expect(grid[0]).toEqual(TEMPLATE_HEADERS);
    expect(String(grid[1][0])).toMatch(/^示例-/);
    const guide = XLSX.utils.sheet_to_json<unknown[]>(wb.Sheets["填写说明"], { header: 1, raw: false, defval: "" });
    IMPORT_FIELD_GUIDE.forEach((g, i) => {
      expect(guide[i + 1]).toEqual([g.field, g.what, g.example]);
    });
    expect(String(guide[guide.length - 2]?.[1])).toBe(IMPORT_FIELD_NOTES);
  });
});

describe("sheetToGrid / gridToRows", () => {
  it("英文列头乱序＋多余列照常解析；未知列忽略", async () => {
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(
      wb,
      XLSX.utils.aoa_to_sheet([
        ["role", "extra", "name", "persona", "aliases", "gender"],
        ["配角", "忽略我", "苏晚", "灯语专家", "二副·老柳", "女"],
        ["", "", "老轨", "", "", ""],
      ]),
      "mydata", // sheet 名不依赖
    );
    const grid = await sheetToGrid(wb);
    expect(grid).not.toBeNull();
    const rows = gridToRows(grid!.headers, grid!.rows);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({ name: "苏晚", role: "配角", persona: "灯语专家" });
    expect(rows[0].aliases).toEqual(["二副", "老柳"]);
    expect(rows[0].dossier.gender).toBe("女");
    expect(rows[1].name).toBe("老轨");
  });
  it("缺「名字」列返回 null", async () => {
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet([["role", "类型"], ["配角"]]), "s");
    await expect(sheetToGrid(wb)).resolves.toBeNull();
  });
  it("空 sheet 容错：跳过空表，取下一个能识别出名字列的表", async () => {
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet([]), "空表");
    XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet([["名字*"], ["甲"]]), "角色");
    const grid = await sheetToGrid(wb);
    expect(grid?.headers).toContain("name");
    expect(grid?.rows[0][0]).toBe("甲");
  });
  it("gridToRows 防御：无名字列返回空；全空白行丢弃", () => {
    expect(gridToRows(["类型"], [["配角"]])).toEqual([]);
    const rows = gridToRows(["名字*", "类型"], [["   ", "配角"], ["乙", "配角"]]);
    expect(rows).toHaveLength(1);
    expect(rows[0].name).toBe("乙");
  });
});

describe("readFileAsRows 护栏", () => {
  it("utf-8（含 BOM）csv 解析：示例行/纯名字行原样进预览", async () => {
    const rows = await readFileAsRows(
      csvFile("a.csv", "\ufeff名字*,类型,一句话人设\n示例-韩十三,配角,锅炉工\n苏晚,主角,灯语专家\n白芷,,药铺学徒"),
    );
    expect(rows).toHaveLength(3);
    expect(rows[0].name).toBe("示例-韩十三");
    expect(rows[1]).toMatchObject({ name: "苏晚", role: "主角", persona: "灯语专家" });
    expect(rows[2].role).toBe(""); // 类型空 → 弹窗按配角落卡
  });
  it("GBK 字节回退解码", () => {
    // 「名字,role」的 GBK 字节流（中文 Windows 传统 CSV）
    const bytes = new Uint8Array([0xc3, 0xfb, 0xd7, 0xd6, 0x2c, 0x72, 0x6f, 0x6c, 0x65]);
    expect(decodeMaybeGbk(bytes.buffer.slice(0))).toBe("名字,role");
  });
  it("xlsx 二进制（真模版回读）：示例行全进预览", async () => {
    const wb = await buildTemplateWorkbook();
    const buf = XLSX.write(wb, { bookType: "xlsx", type: "array" }) as ArrayBuffer;
    const f = new File([buf as unknown as BlobPart], "模版.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    Object.defineProperty(f, "arrayBuffer", { value: async () => buf });
    const rows = await readFileAsRows(f);
    expect(rows).toHaveLength(3);
    expect(rows[0].name).toBe("示例-韩十三");
    expect(rows[0].dossier.faction).toBe("北岭号 · 锅炉工");
  });
  it("非 xlsx/csv 扩展名拒绝", async () => {
    await expect(readFileAsRows(csvFile("a.docx", "x"))).rejects.toThrow(/只支持/);
  });
  it("超 10MB 拒绝", async () => {
    await expect(readFileAsRows(csvFile("big.csv", "名字*", 11 * 1024 * 1024))).rejects.toThrow(/10MB/);
  });
  it(`超 ${BATCH_MAX_ROWS} 行拒绝且不截断`, async () => {
    const lines = ["名字*"];
    for (let i = 0; i < BATCH_MAX_ROWS + 1; i++) lines.push(`角色${i}`);
    await expect(readFileAsRows(csvFile("many.csv", lines.join("\n")))).rejects.toThrow(/分批/);
  });
  it("缺「名字」列报错", async () => {
    await expect(readFileAsRows(csvFile("bad.csv", "类型,性别\n配角,女"))).rejects.toThrow(/名字/);
  });
});
