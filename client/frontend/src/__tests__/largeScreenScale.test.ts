// 大屏等比缩放（large-screen-scale）静态门禁。
//
// 桌面壳窗口 = 屏幕宽-80 / 高-60，大屏下 CSS 视口可到 2500~3800px；全站是 1440 基准的
// px 设计（几百处 font-size:Npx），靠 src/design/large-screen.css 的 --ui-zoom 整体等比
// 放大。而 zoom 会把 vh/vw 一起放大（实测 1.25 倍下 100vh 渲染成视口高的 1.25 倍），
// 所以「必须正好等于视口高度」的规则都要按 / var(--ui-zoom) 补偿——漏一处，大屏下壳层
// 就纵向溢出（工作台最明显：内容比视口高 28%，状态条被顶出屏幕）。
//
// 行为侧由 e2e/large-screen.spec.ts 在真浏览器里钉（2560 无溢出、状态条贴底、≤1920 恒不缩放）；
// 这里补静态侧：缩放层不许被改丢、阈值不许压到像素基线（1440/1920）以下、补偿清单不许少项。
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const FRONTEND = join(__dirname, "..", "..");
const SCALE_CSS = join(FRONTEND, "src", "design", "large-screen.css");
const MAIN_TSX = join(FRONTEND, "src", "main.tsx");

/** 像素基线的最大视口宽：design-parity 固定 1440×900，ui-spec-parity 跑 1440/1920 */
const BASELINE_MAX_VIEWPORT = 1920;

describe("大屏等比缩放层", () => {
  const css = readFileSync(SCALE_CSS, "utf8");

  it("main.tsx 最后引入（同选择器覆盖靠级联顺序，挪到前面即失效）", () => {
    const main = readFileSync(MAIN_TSX, "utf8");
    const imports = [...main.matchAll(/import\s+"(\.\/[^"]+\.css)"/g)].map((m) => m[1]);
    expect(imports.at(-1)).toBe("./design/large-screen.css");
    expect(imports.filter((p) => p === "./design/large-screen.css")).toHaveLength(1);
  });

  it("默认不缩放，且只在支持 zoom 的浏览器里启用（旧浏览器 --ui-zoom 保持 1＝本文件不存在）", () => {
    expect(css).toMatch(/--ui-zoom:\s*1\s*;/);
    expect(css).toMatch(/@supports\s*\(zoom:\s*1\)/);
    expect(css).toMatch(/html\s*\{\s*zoom:\s*var\(--ui-zoom\)/);
  });

  it("阈值不低于像素基线视口（压低到 1920 以下会让 parity/尺寸断言假红）", () => {
    const m = css.match(/@media\s*\(min-width:\s*(\d+)px\)/);
    expect(m, "缺 min-width 断点——大屏放大永远不生效").toBeTruthy();
    expect(Number(m![1])).toBeGreaterThan(BASELINE_MAX_VIEWPORT);
  });

  it("放大倍数有上限（防 5K/8K 上无限放大，字号大到一屏放不下几行）", () => {
    const m = css.match(/--ui-zoom:\s*clamp\(\s*1\s*,[^,]+,\s*([\d.]+)\s*\)/);
    expect(m, "--ui-zoom 必须是 clamp(1, <随宽度线性>, <上限>)").toBeTruthy();
    const cap = Number(m![1]);
    expect(cap).toBeGreaterThan(1);
    expect(cap).toBeLessThanOrEqual(2);
  });

  it("视口高度类规则全部按 / var(--ui-zoom) 补偿（漏一项＝大屏壳层溢出）", () => {
    // [规则选择器, 依据]：这些规则的高度必须正好等于视口高（或视口高减固定条高），
    // zoom 放大后不补偿就会渲染成 zoom 倍视口高
    const compensated = [
      ["body,", "body min-height（base.css 共享段原值 100vh）"],
      ["#root,", "#root/.app-shell min-height（index.css 原值 100vh）"],
      [".wb {", "工作台三栏壳 height（book.css 原值 100vh-26px）"],
      [".auth-wrap {", "落地页竖排容器 min-height（landing.css 原值 100vh-26px）"],
      [".acct-menu {", "账号菜单 max-height（index.css 原值 100vh-24px）"],
      [".modal .mcard {", "弹窗 max-height（base.css 共享段原值 100vh-48px）"],
      [".mcard.wb-style {", "弹窗变体 max-height（base.css 原值 86vh）"],
    ];
    for (const [selector, why] of compensated) {
      const at = css.indexOf(selector);
      expect(at, `补偿清单缺 ${selector}（${why}）`).toBeGreaterThan(-1);
      const block = css.slice(at, css.indexOf("}", at));
      expect(block, `${selector} 的补偿里没用到 var(--ui-zoom)（${why}）`).toContain("var(--ui-zoom)");
    }
    // 设定域两个 sticky 侧栏（角色列表 / 伏笔树）同批
    const sticky = css.match(/\.settings-v[\s\S]*?max-height:\s*calc\(100vh \/ var\(--ui-zoom\) - 56px\)/);
    expect(sticky, "设定域 sticky 侧栏的 max-height 补偿被改丢").toBeTruthy();
  });
});
