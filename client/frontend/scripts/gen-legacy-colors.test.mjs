import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import postcss from "postcss";
import { describe, expect, it } from "vitest";

import {
  buildLegacyStylesheet,
  compileValue,
  formatColor,
  generateIntoDist,
  hasColorFn,
  parseOklch,
} from "./gen-legacy-colors.mjs";

const FIXTURE = `
:root {
  --bg: oklch(98% 0.004 240);
  --border: oklch(90% 0.006 240);
  --fg: oklch(20% 0.02 240);
  --accent: oklch(48% 0.11 170);
  --accent-soft: color-mix(in oklch, var(--accent) 12%, transparent);
  --shadow: 0 1px 2px color-mix(in oklch, var(--fg) 5%, transparent);
}
:root[data-theme=ink] { --accent: oklch(37% 0.01 250); }
.btn { color: var(--fg); border: 1px solid var(--accent-soft); }
.tone { background: color-mix(in oklch, var(--accent) 6%, var(--surface, #fff)); }
.pair, .twin:hover { box-shadow: 0 0 0 1px color-mix(in oklch, var(--fg) 8%, transparent); }
.imp { color: color-mix(in oklch, var(--accent) 40%, var(--fg)) !important; }
@keyframes pulse {
  0% { background: color-mix(in oklch, var(--accent) 10%, transparent); }
  to { background: transparent; }
}
@media (max-width: 600px) {
  .tone { border-color: color-mix(in oklch, var(--accent) 40%, var(--border)); }
}
`;

function parse(css) {
  return postcss.parse(css);
}

function declValue(css, selector, prop) {
  let found = null;
  parse(css).walkRules((rule) => {
    if (rule.selector !== selector) return;
    rule.walkDecls((decl) => {
      if (decl.prop === prop) found = decl.value;
    });
  });
  return found;
}

function tokenName(value) {
  const m = value.match(/var\((--lgc-\d+)\)/);
  return m ? m[1] : null;
}

function tokenValue(css, selector, name) {
  let found = null;
  parse(css).walkRules((rule) => {
    if (rule.selector !== selector) return;
    rule.walkDecls((decl) => {
      if (decl.prop === name) found = decl.value;
    });
  });
  return found;
}

describe("颜色数学", () => {
  it("oklch 极值转 sRGB", () => {
    expect(formatColor(parseOklch("oklch(100% 0 0)"))).toBe("rgb(255, 255, 255)");
    expect(formatColor(parseOklch("oklch(0% 0 0)"))).toBe("rgb(0, 0, 0)");
  });

  it("color-mix 与 transparent 混色＝原色带 alpha", () => {
    const tokens = new Map([["--fg", "oklch(20% 0.02 240)"]]);
    const { value, replaced } = compileValue(
      "color-mix(in oklch, var(--fg) 5%, transparent)",
      tokens,
    );
    expect(replaced).toBe(1);
    expect(value).toMatch(/^rgba\(\d+, \d+, \d+, 0\.05\)$/);
  });

  it("in srgb 混色同样可编译", () => {
    const tokens = new Map([
      ["--fg", "oklch(20% 0.02 240)"],
      ["--surface", "oklch(100% 0 0)"],
    ]);
    const { value, replaced } = compileValue(
      "color-mix(in srgb, var(--fg) 6%, var(--surface))",
      tokens,
    );
    expect(replaced).toBe(1);
    expect(value).toMatch(/^rgb\(\d+, \d+, \d+\)$/);
  });

  it("不透明无彩色按 hue=0 参与短弧插值（与 Chromium 实测一致）", () => {
    const tokens = new Map([
      ["--a", "oklch(48% 0.11 170)"],
      ["--w", "oklch(100% 0 0)"],
    ]);
    const { value } = compileValue("color-mix(in oklch, var(--a) 50%, var(--w))", tokens);
    // Chromium 对同一表达式给出 oklch(0.74 0.055 85)（170 与 0 取短弧中点）
    expect(value).toBe(formatColor(parseOklch("oklch(0.74 0.055 85)")));
  });

  it("显式非默认色相插值方法直接报错（不静默按短弧算）", () => {
    expect(() =>
      buildLegacyStylesheet(
        ":root{--a:oklch(50% 0.1 100)}.x{color:color-mix(in oklch longer hue, var(--a), oklch(100% 0 0))}",
      ),
    ).toThrow(/色相插值方法/);
  });

  it("rgb() 百分比 alpha 按 0–1 解析", () => {
    const { value } = compileValue(
      "color-mix(in srgb, rgb(0 0 0 / 50%) 50%, rgb(255 255 255))",
      new Map(),
    );
    expect(value).toBe("rgba(170, 170, 170, 0.75)");
  });

  it("一个值里的多个颜色函数都替换", () => {
    const tokens = new Map([["--fg", "oklch(20% 0.02 240)"]]);
    const { value, replaced } = compileValue(
      "0 1px 2px color-mix(in oklch, var(--fg) 5%, transparent), 0 2px 4px color-mix(in oklch, var(--fg) 14%, transparent)",
      tokens,
    );
    expect(replaced).toBe(2);
    expect(hasColorFn(value)).toBe(false);
  });
});

describe("兼容表生成", () => {
  const { css, expressionCount, themeOverrideCount } = buildLegacyStylesheet(FIXTURE);

  it("成品声明里不再有 oklch/color-mix", () => {
    parse(css).walkDecls((decl) => {
      expect(hasColorFn(decl.value), `${decl.prop}: ${decl.value}`).toBe(false);
    });
  });

  it("规则顺序、选择器列表、媒体查询与关键帧都原样保留", () => {
    const selectors = [];
    parse(css).walkRules((rule) => {
      if (!rule.parent || rule.parent.type === "root") selectors.push(rule.selector);
    });
    expect(selectors).toContain(".pair, .twin:hover");
    expect(selectors).toContain(".tone");
    const atRules = [];
    parse(css).walkAtRules((at) => atRules.push(`@${at.name} ${at.params}`.trim()));
    expect(atRules).toContain("@keyframes pulse");
    expect(atRules).toContain("@media (max-width: 600px)");
  });

  it("!important 保留", () => {
    let important = null;
    parse(css).walkRules((rule) => {
      if (rule.selector !== ".imp") return;
      rule.walkDecls((decl) => {
        important = decl.important;
      });
    });
    expect(important).toBe(true);
  });

  it("主题相关表达式出按主题覆写，且值与默认不同", () => {
    const toneToken = tokenName(declValue(css, ".tone", "background"));
    expect(toneToken).toBeTruthy();
    const base = tokenValue(css, ":root", toneToken);
    const ink = tokenValue(css, ':root[data-theme="ink"]', toneToken);
    expect(base).toMatch(/^rgb/);
    expect(ink).toMatch(/^rgb/);
    expect(ink).not.toBe(base);
    expect(themeOverrideCount).toBeGreaterThan(0);
  });

  it("与主题无关的表达式不产生主题覆写", () => {
    const pairToken = tokenName(declValue(css, ".pair, .twin:hover", "box-shadow"));
    expect(pairToken).toBeTruthy();
    expect(tokenValue(css, ':root[data-theme="ink"]', pairToken)).toBeNull();
  });

  it("自定义属性里的颜色函数也被编译（--accent-soft / --shadow）", () => {
    const accentSoft = tokenValue(css, ":root", "--accent-soft");
    expect(accentSoft).toMatch(/^var\(--lgc-\d+\)$/);
    const shadow = tokenValue(css, ":root", "--shadow");
    expect(shadow).toContain("var(--lgc-");
    expect(shadow).not.toContain("color-mix");
  });

  it("表达式数量与覆写计数可对账", () => {
    expect(expressionCount).toBeGreaterThanOrEqual(6);
    expect(themeOverrideCount).toBeGreaterThan(0);
  });

  it("未知令牌直接报错（构建红，不静默出错色）", () => {
    expect(() =>
      buildLegacyStylesheet(
        ":root{--a:oklch(50% 0.1 100)}.x{color:color-mix(in oklch, var(--missing) 10%, transparent)}",
      ),
    ).toThrow(/未定义的颜色变量/);
  });
});

describe("产物落盘", () => {
  it("生成 legacy-colors.css 并给 index.html 注入特性检测加载，原 CSS 不动", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "legacy-colors-"));
    const assets = path.join(dir, "assets");
    fs.mkdirSync(assets, { recursive: true });
    const originalCss = FIXTURE;
    fs.writeFileSync(path.join(assets, "app.css"), originalCss, "utf8");
    fs.writeFileSync(
      path.join(dir, "index.html"),
      '<!doctype html><html><head><link rel="stylesheet" crossorigin href="./assets/app.css"></head><body></body></html>',
      "utf8",
    );

    generateIntoDist(dir, () => {});

    const legacyName = fs
      .readdirSync(dir)
      .find((name) => /^legacy-colors-[0-9a-f]{8}\.css$/.test(name));
    expect(legacyName).toBeTruthy();
    const legacy = fs.readFileSync(path.join(dir, legacyName), "utf8");
    expect(hasColorFn(legacy)).toBe(false);
    expect(legacy).toContain("--lgc-1");

    const html = fs.readFileSync(path.join(dir, "index.html"), "utf8");
    expect(html).toContain(legacyName);
    expect(html).toContain("CSS.supports");
    expect(fs.readFileSync(path.join(assets, "app.css"), "utf8")).toBe(originalCss);

    // 幂等：再跑一次不插第二个脚本、不改产物名，也不把自己的产物当输入
    fs.writeFileSync(path.join(dir, "legacy-colors-deadbeef.css"), "stale", "utf8");
    generateIntoDist(dir, () => {});
    const again = fs.readFileSync(path.join(dir, "index.html"), "utf8");
    expect(again.match(/legacy-colors-[0-9a-f]{8}\.css/g)).toHaveLength(1);
    expect(fs.readFileSync(path.join(dir, legacyName), "utf8")).toBe(legacy);
    expect(fs.existsSync(path.join(dir, "legacy-colors-deadbeef.css"))).toBe(false);
  });
});
