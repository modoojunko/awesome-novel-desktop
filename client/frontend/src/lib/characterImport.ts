/**
 * 角色批量导入纯函数（c-char-batch-import）：模版构建、文件解析、行级校验。
 * 唯一事实源约束：IMPORT_FIELD_GUIDE 同时供给模版「填写说明」sheet 与弹窗「字段怎么填」
 * 折叠块——两处禁止各自手抄文案。
 * 不碰 DOM / React：全部输入输出为纯数据（SheetJS workbook 除外）。
 * SheetJS 按需加载：xlsx 整库 min 约 1MB，dynamic import 独立 chunk——
 * 只在「下载模版/解析文件」两个口子现场加载，不进主包（design 决策 1）。
 */
import type * as XlsxNS from "xlsx";
import { DOSSIER_FIELDS, ROLES } from "./characterModel";

type Xlsx = typeof import("xlsx");
let xlsxModule: Promise<Xlsx> | null = null;
export function loadXlsx(): Promise<Xlsx> {
  xlsxModule = xlsxModule ?? import("xlsx");
  return xlsxModule;
}
export type XlsxWorkBook = XlsxNS.WorkBook;

/** 上传护栏：超过即拒绝（不静默截断） */
export const BATCH_MAX_FILE_BYTES = 10 * 1024 * 1024;
export const BATCH_MAX_ROWS = 100;
/** 类型缺省（五轮拍板：弹窗无默认类型选择器，类型列不填＝配角） */
export const BATCH_DEFAULT_ROLE = "配角";

/** 模版「角色」sheet 列头（导出＝中文；导入中英文都认，见 normalizeHeaderKey） */
export const TEMPLATE_HEADERS = [
  "名字*", "类型", "一句话人设", "别名(用·分隔)", "性别", "年龄", "种族",
  "势力·身份", "外貌标签", "语言特征", "背景", "剧情定位",
];

/** 「填写说明」sheet / 弹窗折叠块共用文案（字段／填什么／示例） */
export const IMPORT_FIELD_GUIDE: { field: string; what: string; example: string }[] = [
  { field: "名字*", what: "必填，书内唯一（重名会跳过）。只写称呼本身，称号昵称放「别名」", example: "苏晚" },
  { field: "类型", what: "四选一：主角/配角/反派/路人。不填默认配角；主角全书只能一位", example: "配角" },
  { field: "一句话人设", what: "此人是谁、凭什么是他——一句 60 字内最好（上限 300）。每章都会带进 AI 上下文，写「身份＋特质＋关系钩子」", example: "北岭号二副，灯语专家，陆沉的旧识" },
  { field: "别名（用·分隔）", what: "称呼变体：昵称、称号、职衔，用 · 隔开。AI 靠它认出「二副」「窈姐」都是同一人", example: "老柳·二副" },
  { field: "性别 / 年龄 / 种族", what: "照实填，可留空；年龄概数也行", example: "女 / 31 / 人类" },
  { field: "势力·身份", what: "所属组织＋职位，用 · 分隔；无组织就写身份", example: "北岭号 · 二副" },
  { field: "外貌标签", what: "2~4 个短语，标签化，别写成散文", example: "瘦长个 · 旧道袍" },
  { field: "语言特征", what: "说话习惯、口吻、口头禅", example: "话少 · 命令句式" },
  { field: "背景", what: "出身与来路，一两句（上限 300）", example: "在货运航线跑了六年，上个月才转到拾荒船。" },
  { field: "剧情定位", what: "这个人在故事里干什么、承担什么功能（主角必填）", example: "守着锅炉，也守着一个关于沉船的秘密" },
];
/** 通用三条（说明 sheet 末尾 / 折叠块末尾） */
export const IMPORT_FIELD_NOTES =
  "只有名字是必填，其余都可以留空、建完在角色设定里补；一格一句别换行；类型不填默认配角。";

/** 模版「示例-」样例行（导入时按前缀防呆跳过） */
const TEMPLATE_SAMPLE_ROWS = [
  ["示例-韩十三", "配角", "北岭号新来的锅炉工", "老韩头·十三", "男", "28", "人类", "北岭号 · 锅炉工", "壮实 · 满手油灰", "嗓门大 · 爱哼船歌", "在货运航线跑了六年。", "守着锅炉，也守着一个关于沉船的秘密"],
  ["示例-灯嫂", "配角", "航标站看守，认得每一盏灯", "", "", "", "", "", "", "", "", ""],
  ["示例-唐九", "", "", "", "", "", "", "", "", "", "", ""],
];

/** 一行解析结果（预览态，可就地修改） */
export interface BatchRow {
  name: string;
  role: string;
  persona: string;
  aliases: string[];
  dossier: Record<string, string>;
}

export interface BatchRowStatus {
  cls: "ok" | "warn" | "err";
  text: string;
  ok: boolean;
}

const DOSSIER_KEYS = DOSSIER_FIELDS.map((f) => f.k);
const DOSSIER_LABELS: Record<string, string> = Object.fromEntries(
  DOSSIER_FIELDS.map((f) => [f.k, f.label]),
);

const HEADER_KEYS: Record<string, string> = {
  名字: "name", 名称: "name", name: "name",
  类型: "role", 角色类型: "role", role: "role",
  一句话人设: "persona", 人设: "persona", persona: "persona",
  别名: "aliases", aliases: "aliases",
  性别: "gender", gender: "gender",
  年龄: "age", age: "age",
  种族: "race", race: "race",
  "势力·身份": "faction", 势力身份: "faction", faction: "faction",
  外貌标签: "look", 外貌: "look", look: "look",
  语言特征: "speech", speech: "speech",
  背景: "background", background: "background",
  剧情定位: "plot", plot: "plot",
};

/** 列头归一：trim → 去尾部 * → 去空白；「别名(用·分隔)」等变体按前缀兜底 */
export function normalizeHeaderKey(raw: unknown): string | null {
  const key = String(raw ?? "").trim().replace(/\*$/, "").replace(/\s+/g, "");
  if (HEADER_KEYS[key]) return HEADER_KEYS[key];
  if (key.startsWith("别名")) return "aliases";
  return null;
}

function clampText(v: unknown, max: number): string {
  return String(v ?? "").trim().slice(0, max);
}

/** 任意来源的行对象 → 预览行（clamp 与别名拆分在这里收口） */
export function normalizeItem(o: Record<string, unknown> | undefined): BatchRow {
  const rawDossier = typeof o?.dossier === "object" && o?.dossier ? o.dossier : {};
  const dossier: Record<string, string> = {};
  for (const k of DOSSIER_KEYS) {
    const v = (rawDossier as Record<string, unknown>)[k];
    const s = clampText(v, 300);
    if (s) dossier[k] = s;
  }
  const rawAliases = o?.aliases;
  const aliasList: string[] = [];
  if (Array.isArray(rawAliases)) {
    for (const a of rawAliases) aliasList.push(String(a));
  } else if (rawAliases) {
    aliasList.push(String(rawAliases));
  }
  return {
    name: clampText(o?.name, 50),
    role: String(o?.role ?? "").trim(),
    persona: clampText(o?.persona, 300),
    aliases: aliasList.map((a) => a.trim()).filter(Boolean),
    dossier,
  };
}

export function effectiveRole(row: BatchRow): string {
  return (ROLES as readonly string[]).indexOf(row.role) >= 0 ? row.role : BATCH_DEFAULT_ROLE;
}

/** 行级校验上下文：整批行＋库内重名集合＋「已有主角」由调用方注入 */
export interface BatchStatusContext {
  existingNames: Set<string>;
  hasProtagonist: boolean;
  rows: BatchRow[];
  batchNames: Set<string>;
  batchFirstIdx: Map<string, number>;
}

export function statusContext(
  rows: BatchRow[],
  ctx: { existingNames: Set<string>; hasProtagonist: boolean },
): BatchStatusContext {
  const batchNames = new Set<string>();
  const batchFirstIdx = new Map<string, number>();
  rows.forEach((r, i) => {
    if (r.name && !batchNames.has(r.name)) {
      batchNames.add(r.name);
      batchFirstIdx.set(r.name, i);
    }
  });
  return { ...ctx, rows, batchNames, batchFirstIdx };
}

/** 行级校验（纯函数：上下文由 statusContext 整批构造） */
export function rowStatus(row: BatchRow, idx: number, ctx: BatchStatusContext): BatchRowStatus {
  if (/^示例/.test(row.name || "")) return { cls: "warn", text: "示例行，不导入", ok: false };
  if (!row.name) return { cls: "err", text: "没写名字", ok: false };
  if (row.name.length > 50) return { cls: "err", text: "名字超 50 字", ok: false };
  const dupExisting = ctx.existingNames.has(row.name);
  const dupBatch = ctx.batchNames.has(row.name) && ctx.batchFirstIdx.get(row.name) !== idx;
  if (dupExisting || dupBatch) {
    return { cls: "warn", text: dupExisting ? "已有同名，跳过" : "批内重名，跳过", ok: false };
  }
  const mains = ctx.rows.filter((r) => effectiveRole(r) === "主角").length + (ctx.hasProtagonist ? 1 : 0);
  if (effectiveRole(row) === "主角" && mains > 1) {
    return { cls: "err", text: "每书一位主角", ok: false };
  }
  const extras: string[] = [];
  if (row.aliases.length) extras.push(`别名×${row.aliases.length}`);
  if (Object.keys(row.dossier).length) extras.push("含档案");
  return { cls: "ok", text: "将新建" + (extras.length ? ` · ${extras.join(" · ")}` : ""), ok: true };
}

/** 模版工作簿：「角色」（列头＋示例行）＋「填写说明」（IMPORT_FIELD_GUIDE＋通用三条） */
export async function buildTemplateWorkbook(): Promise<XlsxWorkBook> {
  const X = await loadXlsx();
  const wb = X.utils.book_new();
  X.utils.book_append_sheet(wb, X.utils.aoa_to_sheet([TEMPLATE_HEADERS, ...TEMPLATE_SAMPLE_ROWS]), "角色");
  const guide: (string | null)[][] = [
    ["字段", "填什么", "示例"],
    ...IMPORT_FIELD_GUIDE.map((g) => [g.field, g.what, g.example]),
    [null, null, null],
    ["通用", IMPORT_FIELD_NOTES, null],
    ["规则", "一行一个角色；列头行不要改；「示例-」开头的行导入时会自动跳过（记得删掉示例行再导入）", null],
  ];
  X.utils.book_append_sheet(wb, X.utils.aoa_to_sheet(guide), "填写说明");
  return wb;
}

/** 首个能识别出「名字」列的 sheet 的二维表（首行＝列头）；找不到返回 null */
export async function sheetToGrid(wb: XlsxWorkBook): Promise<{ headers: string[]; rows: unknown[][] } | null> {
  const X = await loadXlsx();
  for (const name of wb.SheetNames) {
    const grid = X.utils.sheet_to_json<unknown[]>(wb.Sheets[name], {
      header: 1,
      raw: false, // 显示文本（"31" 就是 "31"）——Excel 自动转日期/浮点的防线上移到读出口
      defval: "",
      blankrows: false,
    });
    if (!grid.length) continue;
    const headers = (grid[0] as unknown[]).map(normalizeHeaderKey);
    if (headers.indexOf("name") >= 0) {
      return { headers: headers as string[], rows: grid.slice(1) as unknown[][] };
    }
  }
  return null;
}

/** 二维表 → 预览行（列头按名匹配、多余列忽略；行数护栏在这里收） */
export function gridToRows(headers: string[], rows: unknown[][]): BatchRow[] {
  const cols = headers.map(normalizeHeaderKey);
  if (cols.indexOf("name") < 0) return [];
  const out: BatchRow[] = [];
  for (const cells of rows) {
    const o: Record<string, unknown> = { dossier: {} };
    cols.forEach((k, c) => {
      if (!k) return;
      const v = String((cells[c] ?? "") as string).trim();
      if (!v) return;
      if (k === "aliases") o.aliases = v.split(/[·・、,，]/);
      else if (DOSSIER_KEYS.indexOf(k) >= 0) (o.dossier as Record<string, string>)[k] = v;
      else o[k] = v;
    });
    const row = normalizeItem(o);
    if (row.name || row.persona || row.aliases.length || Object.keys(row.dossier).length) {
      out.push(row);
    }
  }
  return out;
}

const utf8Decoder = new TextDecoder("utf-8");
let gbkDecoder: TextDecoder | null = null;
/** CSV 字节解码：utf-8 优先；出现 U+FFFD 再试 GBK（中文 Windows 传统 CSV 的最大乱码源） */
export function decodeMaybeGbk(buf: ArrayBuffer): string {
  const text = utf8Decoder.decode(buf);
  if (!text.includes("\uFFFD")) return text;
  /* v8 ignore start -- catch 分支＝环境无 gbk 解码器（Node/Chromium 均内置，不可达） */
  try {
    gbkDecoder = gbkDecoder ?? new TextDecoder("gbk");
    const gbk = gbkDecoder.decode(buf);
    if (!gbk.includes("\uFFFD")) return gbk;
  } catch {
    /* 维持 utf-8 结果 */
  }
  /* v8 ignore end */
  return text;
}

/**
 * 上传文件 → 预览行。护栏：扩展名 / 10MB / 100 行；无「名字」列报错（红条文案）。
 * 抛 Error(message)＝弹窗红条文案。
 */
export async function readFileAsRows(file: File): Promise<BatchRow[]> {
  const okExt = /\.(xlsx|csv)$/i.test(file.name);
  if (!okExt) throw new Error("只支持 .xlsx 或 .csv——请用「下载模版」的格式");
  if (file.size > BATCH_MAX_FILE_BYTES) throw new Error("文件超过 10MB——请精简后再导入");
  const X = await loadXlsx();
  let wb: XlsxWorkBook;
  if (/\.csv$/i.test(file.name)) {
    const text = decodeMaybeGbk(await file.arrayBuffer());
    wb = X.read(text, { type: "string", raw: false });
  } else {
    wb = X.read(await file.arrayBuffer(), { type: "array", raw: false });
  }
  const grid = await sheetToGrid(wb);
  if (!grid) {
    throw new Error("模版列头不对——没有「名字」列。请用「下载模版」的格式，或把列头改成与模版一致");
  }
  const rows = gridToRows(grid.headers, grid.rows);
  if (rows.length > BATCH_MAX_ROWS) {
    throw new Error(`一次最多导入 ${BATCH_MAX_ROWS} 行（当前 ${rows.length} 行）——请分批导入`);
  }
  return rows;
}
