/*
 * 旧内核颜色兼容表生成器（c-legacy-color-fallback）
 *
 * 背景：设计系统令牌一律 oklch + color-mix（design-system spec 规定源文件如此），
 * 而这两个函数要 Chromium 111+。桌面壳的 WebView2 在国家/企业机器上可能被钉在
 * 更老的版本（现场：108.0.1462.46），页面只剩白底黑字。
 *
 * 做法：把构建产物完整复制一份，把每处 oklch()/color-mix() 换成具体 rgba 令牌
 * （--lgc-N），主题相关表达式按 :root[data-theme] 覆写。原 CSS 一个字节不动；
 * 旧内核由 index.html 里的特性检测改成加载这份完整副本——整份替换，因此规则
 * 顺序与层叠关系与原表完全一致（不是「后置补丁」，不会出现同权重覆盖错位）。
 *
 * 生成期三道闸门（任一失败＝构建红）：
 *   1. 结构对拍：副本的规则/选择器/声明顺序必须与原表逐条一致；
 *   2. 残留检查：副本的声明值里不得再出现 oklch()/color-mix()；
 *   3. 表达式可解：未知变量/未知颜色语法直接抛错，不静默产出错色。
 */

import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import postcss from "postcss";

export const LEGACY_FILE_PREFIX = "legacy-colors-";
export const LEGACY_FILE_RE = /^legacy-colors-[0-9a-f]{8}\.css$/;
const LEGACY_TOKEN_PREFIX = "--lgc-";

// ---------- 基础工具 ----------

const EPS = 1e-9;

function clamp01(v) {
  return Math.min(1, Math.max(0, v));
}

function splitTopLevel(text, sep = ",") {
  const out = [];
  let depth = 0;
  let quote = null;
  let start = 0;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (quote) {
      if (ch === "\\") i += 1;
      else if (ch === quote) quote = null;
      continue;
    }
    if (ch === '"' || ch === "'") quote = ch;
    else if (ch === "(" || ch === "[") depth += 1;
    else if (ch === ")" || ch === "]") depth -= 1;
    else if (ch === sep && depth === 0) {
      out.push(text.slice(start, i));
      start = i + 1;
    }
  }
  out.push(text.slice(start));
  return out;
}

export function findColorFn(value, from = 0) {
  let best = -1;
  for (const fn of ["oklch(", "color-mix("]) {
    let idx = value.indexOf(fn, from);
    while (idx >= 0) {
      const prev = idx > 0 ? value[idx - 1] : "";
      if (!/[\w-]/.test(prev)) {
        if (best < 0 || idx < best) best = idx;
        break;
      }
      idx = value.indexOf(fn, idx + 1);
    }
  }
  return best;
}

export function hasColorFn(value) {
  return findColorFn(String(value)) >= 0;
}

function matchParen(value, openIdx) {
  let depth = 0;
  let quote = null;
  for (let i = openIdx; i < value.length; i += 1) {
    const ch = value[i];
    if (quote) {
      if (ch === "\\") i += 1;
      else if (ch === quote) quote = null;
      continue;
    }
    if (ch === '"' || ch === "'") {
      quote = ch;
      continue;
    }
    if (ch === "(") depth += 1;
    else if (ch === ")") {
      depth -= 1;
      if (depth === 0) return i + 1;
    }
  }
  throw new Error(`括号不闭合：${value.slice(openIdx)}`);
}

function parseNumberOrPercent(token) {
  const t = String(token).trim();
  if (t.endsWith("%")) return parseFloat(t) / 100;
  const n = parseFloat(t);
  if (Number.isNaN(n)) throw new Error(`无法解析数值：${token}`);
  return n;
}

// ---------- 颜色数学 ----------

export function parseOklch(text) {
  const m = String(text).trim().match(/^oklch\((.*)\)$/is);
  if (!m) throw new Error(`不是 oklch()：${text}`);
  const [main, alphaPart] = m[1].split("/");
  const parts = main.trim().split(/\s+/);
  if (parts.length < 3) throw new Error(`oklch 分量不足：${text}`);
  const L = parseNumberOrPercent(parts[0]);
  const cRaw = parts[1];
  const C = cRaw.endsWith("%") ? (parseFloat(cRaw) / 100) * 0.4 : parseFloat(cRaw);
  const hRaw = parts[2];
  const h = /^none$/i.test(hRaw) ? 0 : parseFloat(hRaw);
  const a = alphaPart === undefined ? 1 : parseNumberOrPercent(alphaPart);
  if ([L, C, h, a].some((n) => Number.isNaN(n))) throw new Error(`oklch 非法：${text}`);
  return { L, C, h, a: clamp01(a) };
}

export function srgbToOklch(r, g, b, a = 1) {
  const lin = [r, g, b].map((v) => {
    const x = v / 255;
    return x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
  });
  const l = 0.4122214708 * lin[0] + 0.5363325363 * lin[1] + 0.0514459929 * lin[2];
  const m = 0.2119034982 * lin[0] + 0.6806995451 * lin[1] + 0.1073969566 * lin[2];
  const s = 0.0883024619 * lin[0] + 0.2817188376 * lin[1] + 0.6299787005 * lin[2];
  const l_ = Math.cbrt(l);
  const m_ = Math.cbrt(m);
  const s_ = Math.cbrt(s);
  const L = 0.2104542553 * l_ + 0.793617785 * m_ - 0.0040720468 * s_;
  const A = 1.9779984951 * l_ - 2.428592205 * m_ + 0.4505937099 * s_;
  const B = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.808675766 * s_;
  const C = Math.hypot(A, B);
  let h = (Math.atan2(B, A) * 180) / Math.PI;
  if (h < 0) h += 360;
  return { L, C, h, a };
}

function oklchToSrgbFloat({ L, C, h }) {
  const hr = ((h || 0) * Math.PI) / 180;
  const A = C * Math.cos(hr);
  const B = C * Math.sin(hr);
  const l_ = L + 0.3963377774 * A + 0.2158037573 * B;
  const m_ = L - 0.1055613458 * A - 0.0638541728 * B;
  const s_ = L - 0.0894841775 * A - 1.291485548 * B;
  const l = l_ ** 3;
  const m = m_ ** 3;
  const s = s_ ** 3;
  const lin = [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
  return lin.map((x) => {
    const v = x <= 0.0031308 ? 12.92 * x : 1.055 * Math.max(x, 0) ** (1 / 2.4) - 0.055;
    return clamp01(v);
  });
}

export function oklchToSrgb(color) {
  return oklchToSrgbFloat(color).map((v) => Math.round(v * 255));
}

function oklchToSrgbUnit(color) {
  return oklchToSrgbFloat(color);
}

export function formatColor(color) {
  if (color.a <= 0.0001) return "rgba(0, 0, 0, 0)";
  const [r, g, b] = oklchToSrgb(color);
  if (color.a >= 0.9999) return `rgb(${r}, ${g}, ${b})`;
  const a = Math.round(color.a * 10000) / 10000;
  return `rgba(${r}, ${g}, ${b}, ${a})`;
}

// ---------- 表达式求值 ----------

function parseHexColor(text) {
  let h = text.slice(1);
  if (h.length === 3 || h.length === 4) h = [...h].map((c) => c + c).join("");
  if (h.length !== 6 && h.length !== 8) throw new Error(`非法 hex 颜色：${text}`);
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  const a = h.length === 8 ? parseInt(h.slice(6, 8), 16) / 255 : 1;
  return srgbToOklch(r, g, b, a);
}

function parseRgbColor(text) {
  const m = text.match(/^rgba?\((.*)\)$/is);
  if (!m) throw new Error(`非法 rgb 颜色：${text}`);
  const parts = m[1].trim().split(/\s*[,/]\s*|\s+/).filter(Boolean);
  if (parts.length < 3) throw new Error(`rgb 分量不足：${text}`);
  const channel = (raw) => (raw.endsWith("%") ? (parseFloat(raw) / 100) * 255 : parseFloat(raw));
  const r = channel(parts[0]);
  const g = channel(parts[1]);
  const b = channel(parts[2]);
  const a = parts[3] === undefined ? 1 : parseFloat(parts[3]);
  return srgbToOklch(r, g, b, a);
}

function parseVar(text) {
  const inner = text.slice(4, -1);
  const parts = splitTopLevel(inner, ",");
  return {
    name: parts[0].trim(),
    fallback: parts.length > 1 ? parts.slice(1).join(",").trim() : null,
  };
}

function parseColorOperand(part, tokens, stack) {
  let s = part.trim();
  let pct = null;
  const m = s.match(/\s+([\d.]+)%\s*$/);
  if (m) {
    pct = parseFloat(m[1]) / 100;
    s = s.slice(0, m.index).trim();
  }
  return { ...resolveColor(s, tokens, stack), pct };
}

function mixOklch(c1, c2, p1, p2) {
  const a1 = c1.a;
  const a2 = c2.a;
  const ap = a1 * p1 + a2 * p2;
  if (ap <= EPS) return { L: 0, C: 0, h: 0, a: 0, powerless: true };
  const L = (c1.L * a1 * p1 + c2.L * a2 * p2) / ap;
  const C = (c1.C * a1 * p1 + c2.C * a2 * p2) / ap;
  const powerless1 = c1.powerless || a1 <= EPS;
  const powerless2 = c2.powerless || a2 <= EPS;
  let h;
  if (powerless1 && powerless2) {
    h = 0;
  } else if (powerless1) {
    h = c2.h;
  } else if (powerless2) {
    h = c1.h;
  } else {
    let h1 = c1.h;
    let h2 = c2.h;
    const d = h2 - h1;
    if (d > 180) h2 -= 360;
    else if (d < -180) h2 += 360;
    h = h1 * p1 + h2 * p2;
  }
  h = ((h % 360) + 360) % 360;
  return { L, C, h, a: clamp01(ap), powerless: C <= EPS };
}

function mixSrgb(c1, c2, p1, p2) {
  const a1 = c1.a;
  const a2 = c2.a;
  const ap = a1 * p1 + a2 * p2;
  if (ap <= EPS) return { L: 0, C: 0, h: 0, a: 0, powerless: true };
  const [r1, g1, b1] = oklchToSrgbUnit(c1);
  const [r2, g2, b2] = oklchToSrgbUnit(c2);
  const r = (r1 * a1 * p1 + r2 * a2 * p2) / ap;
  const g = (g1 * a1 * p1 + g2 * a2 * p2) / ap;
  const b = (b1 * a1 * p1 + b2 * a2 * p2) / ap;
  const mixed = srgbToOklch(r * 255, g * 255, b * 255, clamp01(ap));
  return { ...mixed, powerless: mixed.C <= EPS };
}

function evalColorMix(text, tokens, stack) {
  const open = text.indexOf("(");
  const inner = text.slice(open + 1, -1);
  const parts = splitTopLevel(inner, ",");
  if (parts.length !== 3) throw new Error(`color-mix 参数数量不对：${text}`);
  const space = parts[0].trim().replace(/\s+/g, " ");
  const inOklch = /^in oklch(\s|$)/i.test(space);
  const inSrgb = /^in srgb(\s|$)/i.test(space);
  if (!inOklch && !inSrgb) {
    throw new Error(`不支持的颜色空间：${space}（仅支持 in oklch / in srgb）`);
  }
  const c1 = parseColorOperand(parts[1], tokens, stack);
  const c2 = parseColorOperand(parts[2], tokens, stack);
  let w1 = c1.pct;
  let w2 = c2.pct;
  if (w1 == null && w2 == null) {
    w1 = 0.5;
    w2 = 0.5;
  } else if (w1 == null) {
    w1 = 1 - w2;
  } else if (w2 == null) {
    w2 = 1 - w1;
  }
  const total = w1 + w2;
  if (!(total > 0)) throw new Error(`color-mix 权重非法：${text}`);
  return inSrgb
    ? mixSrgb(c1, c2, w1 / total, w2 / total)
    : mixOklch(c1, c2, w1 / total, w2 / total);
}

export function resolveColor(text, tokens, stack = []) {
  const t = String(text).trim();
  if (/^transparent$/i.test(t)) return { L: 0, C: 0, h: 0, a: 0, powerless: true };
  if (/^oklch\(/i.test(t)) return { ...parseOklch(t), powerless: false };
  if (/^color-mix\(/i.test(t)) return evalColorMix(t, tokens, stack);
  if (/^var\(/i.test(t)) {
    const { name, fallback } = parseVar(t);
    if (stack.includes(name)) throw new Error(`变量循环：${[...stack, name].join(" -> ")}`);
    if (tokens.has(name)) return resolveColor(tokens.get(name), tokens, [...stack, name]);
    if (fallback != null) return resolveColor(fallback, tokens, stack);
    throw new Error(`未定义的颜色变量：${name}（表达式 ${stack[stack.length - 1] ?? "?"}）`);
  }
  if (/^#[0-9a-f]{3,8}$/i.test(t)) return { ...parseHexColor(t), powerless: false };
  if (/^rgba?\(/i.test(t)) return { ...parseRgbColor(t), powerless: false };
  throw new Error(`不支持的颜色表达式：${t}`);
}

export function compileValue(value, tokens) {
  let out = "";
  let i = 0;
  let replaced = 0;
  for (;;) {
    const start = findColorFn(value, i);
    if (start < 0) {
      out += value.slice(i);
      break;
    }
    out += value.slice(i, start);
    const open = value.indexOf("(", start);
    const end = matchParen(value, open);
    out += formatColor(resolveColor(value.slice(start, end), tokens));
    replaced += 1;
    i = end;
  }
  return { value: out, replaced };
}

// ---------- 令牌表 ----------

function parseRootSelector(selector) {
  const m = String(selector)
    .trim()
    .match(/^:root(?:\[data-theme=(?:"([^"]+)"|'([^']+)'|([^\]]+))\])?$/);
  if (!m) return null;
  return { theme: m[1] ?? m[2] ?? m[3] ?? null };
}

export function collectTokenTables(root) {
  const base = new Map();
  const themes = new Map();
  root.walkRules((rule) => {
    const info = parseRootSelector(rule.selector);
    if (!info) return;
    let map = base;
    if (info.theme) {
      if (!themes.has(info.theme)) themes.set(info.theme, new Map());
      map = themes.get(info.theme);
    }
    rule.walkDecls((decl) => {
      if (decl.prop.startsWith("--")) map.set(decl.prop, decl.value);
    });
  });
  return { base, themes };
}

// ---------- 结构对拍（生成期闸门 1） ----------

function assertStructure(originalRoot, legacyRoot, exprNames) {
  const originalNodes = originalRoot.nodes ?? [];
  const legacyNodes = legacyRoot.nodes ?? [];
  if (originalNodes.length !== legacyNodes.length) {
    throw new Error(
      `结构对拍失败：顶层节点数 ${legacyNodes.length} != ${originalNodes.length}`,
    );
  }
  for (let i = 0; i < originalNodes.length; i += 1) {
    compareNode(originalNodes[i], legacyNodes[i], `${i}`);
  }

  function compareNode(a, b, where) {
    if (a.type !== b.type) throw new Error(`结构对拍失败 @${where}：类型 ${b.type} != ${a.type}`);
    if (a.type === "rule") {
      if (a.selector !== b.selector) {
        throw new Error(`结构对拍失败 @${where}：选择器漂移「${b.selector}」!=「${a.selector}」`);
      }
    } else if (a.type === "atrule") {
      if (a.name !== b.name || (a.params ?? "") !== (b.params ?? "")) {
        throw new Error(`结构对拍失败 @${where}：@${b.name} ${b.params} != @${a.name} ${a.params}`);
      }
    } else if (a.type === "decl") {
      if (a.prop !== b.prop) throw new Error(`结构对拍失败 @${where}：属性 ${b.prop} != ${a.prop}`);
      if (Boolean(a.important) !== Boolean(b.important)) {
        throw new Error(`结构对拍失败 @${where}：${a.prop} 的 !important 丢失`);
      }
      const expected = hasColorFn(a.value)
        ? replaceWithNames(a.value, exprNames)
        : a.value;
      if (expected !== b.value) {
        throw new Error(
          `结构对拍失败 @${where}：${a.prop} 值「${b.value}」!= 期望「${expected}」`,
        );
      }
      return;
    }
    const aNodes = a.nodes ?? [];
    const bNodes = b.nodes ?? [];
    if (aNodes.length !== bNodes.length) {
      throw new Error(`结构对拍失败 @${where}：子节点数 ${bNodes.length} != ${aNodes.length}`);
    }
    for (let i = 0; i < aNodes.length; i += 1) compareNode(aNodes[i], bNodes[i], `${where}.${i}`);
  }
}

function replaceWithNames(value, exprNames) {
  let out = "";
  let i = 0;
  for (;;) {
    const start = findColorFn(value, i);
    if (start < 0) {
      out += value.slice(i);
      break;
    }
    out += value.slice(i, start);
    const open = value.indexOf("(", start);
    const end = matchParen(value, open);
    const expr = value.slice(start, end);
    if (!exprNames.has(expr)) throw new Error(`结构对拍失败：表达式未登记 ${expr}`);
    out += `var(${exprNames.get(expr)})`;
    i = end;
  }
  return out;
}

// ---------- 主变换 ----------

export function buildLegacyStylesheet(cssText) {
  const originalRoot = postcss.parse(cssText);
  const root = postcss.parse(cssText);
  const { base, themes } = collectTokenTables(originalRoot);
  const themeKeys = [...themes.keys()].sort();
  const tokensFor = (theme) => {
    const map = new Map(base);
    if (theme && themes.has(theme)) for (const [k, v] of themes.get(theme)) map.set(k, v);
    return map;
  };

  root.walkAtRules((at) => {
    if (hasColorFn(at.params ?? "")) {
      throw new Error(`@${at.name} 参数里出现颜色函数，兼容表无法安全改写：${at.params}`);
    }
  });

  const exprNames = new Map();
  let counter = 0;
  root.walkDecls((decl) => {
    if (!hasColorFn(decl.value)) return;
    let out = "";
    let i = 0;
    for (;;) {
      const start = findColorFn(decl.value, i);
      if (start < 0) {
        out += decl.value.slice(i);
        break;
      }
      out += decl.value.slice(i, start);
      const open = decl.value.indexOf("(", start);
      const end = matchParen(decl.value, open);
      const expr = decl.value.slice(start, end);
      if (!exprNames.has(expr)) {
        counter += 1;
        exprNames.set(expr, `${LEGACY_TOKEN_PREFIX}${counter}`);
      }
      out += `var(${exprNames.get(expr)})`;
      i = end;
    }
    decl.value = out;
  });

  // 默认主题值 + 各主题差异值（只对确实变化的主题出覆写）
  const defs = new Map();
  for (const [expr, name] of exprNames) {
    const def = formatColor(resolveColor(expr, tokensFor(null)));
    const themeValues = new Map();
    for (const theme of themeKeys) {
      const v = formatColor(resolveColor(expr, tokensFor(theme)));
      if (v !== def) themeValues.set(theme, v);
    }
    defs.set(name, { expr, def, themeValues });
  }

  assertStructure(originalRoot, root, exprNames);

  if (defs.size > 0) {
    const rootRule = postcss.rule({ selector: ":root" });
    for (const [name, { def }] of defs) {
      rootRule.append(postcss.decl({ prop: name, value: def }));
    }
    root.append(rootRule);
    for (const theme of themeKeys) {
      const rule = postcss.rule({ selector: `:root[data-theme=${JSON.stringify(theme)}]` });
      for (const [name, { themeValues }] of defs) {
        if (themeValues.has(theme)) {
          rule.append(postcss.decl({ prop: name, value: themeValues.get(theme) }));
        }
      }
      if (rule.nodes.length > 0) root.append(rule);
    }
  }

  // 闸门 2：成品声明值里不得再有颜色函数
  root.walkDecls((decl) => {
    if (hasColorFn(decl.value)) {
      throw new Error(`兼容表仍残留颜色函数：${decl.prop}: ${decl.value}`);
    }
  });

  // 闸门 3：引用到的 --lgc-* 必须都有定义
  const defined = new Set(defs.keys());
  root.walkDecls((decl) => {
    if (decl.prop.startsWith(LEGACY_TOKEN_PREFIX)) return;
    const re = new RegExp(`var\\((${LEGACY_TOKEN_PREFIX}[\\w-]+)`, "g");
    let m;
    while ((m = re.exec(decl.value))) {
      if (!defined.has(m[1])) throw new Error(`兼容表引用了未定义令牌：${m[1]}`);
    }
  });

  return {
    css: root.toString(),
    expressionCount: defs.size,
    themeOverrideCount: [...defs.values()].reduce((n, d) => n + d.themeValues.size, 0),
  };
}

// ---------- CLI ----------

function listCssHrefs(html) {
  const hrefs = [];
  const re = /<link\b[^>]*>/gi;
  let m;
  while ((m = re.exec(html))) {
    const tag = m[0];
    if (!/\brel\s*=\s*["']stylesheet["']/i.test(tag)) continue;
    const hrefMatch = tag.match(/\bhref\s*=\s*["']([^"']+)["']/i);
    if (hrefMatch) hrefs.push(hrefMatch[1]);
  }
  return hrefs;
}

export function generateIntoDist(distDir = "dist", log = console.log) {
  const indexPath = path.join(distDir, "index.html");
  if (!fs.existsSync(indexPath)) throw new Error(`找不到 ${indexPath}——先跑 vite build`);
  let html = fs.readFileSync(indexPath, "utf8");
  // 排除自己注入的兼容表链接：否则二次构建会把上次的产物当输入再编译一遍（体积翻倍）
  const hrefs = listCssHrefs(html).filter(
    (href) => !/legacy-colors(-[0-9a-f]{8})?\.css/.test(href.split("?")[0]),
  );
  if (hrefs.length === 0) throw new Error("index.html 里没有样式表引用，无法生成兼容表");

  const cssTexts = hrefs.map((href) => {
    const clean = href.split("?")[0].replace(/^\.\//, "");
    const full = path.resolve(distDir, clean);
    if (!fs.existsSync(full)) throw new Error(`样式表不存在：${full}`);
    return fs.readFileSync(full, "utf8");
  });

  const result = buildLegacyStylesheet(cssTexts.join("\n"));
  // 文件名带内容哈希：Web 侧静态缓存不会拿旧表配新 HTML
  const hash = crypto.createHash("sha256").update(result.css).digest("hex").slice(0, 8);
  const fileName = `${LEGACY_FILE_PREFIX}${hash}.css`;
  const legacyPath = path.join(distDir, fileName);
  for (const name of fs.readdirSync(distDir)) {
    if (name !== fileName && (LEGACY_FILE_RE.test(name) || name === "legacy-colors.css")) {
      fs.unlinkSync(path.join(distDir, name));
    }
  }
  fs.writeFileSync(legacyPath, result.css, "utf8");

  // 先移除旧注入（含历史无哈希文件名），再插当前版本——避免升级后残留旧引用
  html = html.replace(
    /<script>if\(!\(window\.CSS&&CSS\.supports[\s\S]*?legacy-colors[\s\S]*?<\/script>/g,
    "",
  );
  const lastLink = [...html.matchAll(/<link\b[^>]*>/gi)]
    .filter((m) => /\brel\s*=\s*["']stylesheet["']/i.test(m[0]))
    .pop();
  if (!lastLink) throw new Error("找不到可插入兼容表的样式表标签");
  const insertAt = lastLink.index + lastLink[0].length;
  const snippet =
    `<script>if(!(window.CSS&&CSS.supports` +
    `&&CSS.supports('color','oklch(50% 0.1 200)')` +
    `&&CSS.supports('color','color-mix(in oklch, red, blue)')))` +
    `{document.write('<link rel="stylesheet" href="./${fileName}">');}</script>`;
  html = html.slice(0, insertAt) + snippet + html.slice(insertAt);
  fs.writeFileSync(indexPath, html, "utf8");

  log(
    `legacy colors: ${result.expressionCount} 个表达式，` +
      `${result.themeOverrideCount} 条主题覆写，` +
      `${(Buffer.byteLength(result.css) / 1024).toFixed(1)}KB → ${legacyPath}`,
  );
  return result;
}

const isCli = process.argv[1] && pathToFileURL(path.resolve(process.argv[1])).href === import.meta.url;
if (isCli) {
  try {
    generateIntoDist(process.argv[2] ?? "dist");
  } catch (err) {
    console.error(`legacy colors 生成失败：${err.message}`);
    process.exitCode = 1;
  }
}
