// 鉴权不变量守卫（PR #414 评审结论）：C端 前端对本地后端的每个直接 HTTP 调用都必须
// 带 Authorization——后端 auth_local.get_current_user 无头即 401，而 e2e 全量打桩
// （page.route("**/api/**")）恰好把这类缺陷整片盖住（#409 下载成稿/备份/恢复三处裸
// fetch 就是这么溜过 154 条全绿 e2e 的）。
//
// 本测试源码级扫描 src/**，**禁止新增**未带鉴权的直接 fetch：新调用一律走 lib/api.ts
// 的 request()/api.*（自动注入 Bearer + 401/503 口径）。带白名单=已知合规例外。
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..");
const FRONTEND_ROOT = join(SRC, "..");

/** 已知合规例外（file 相对 client/frontend，reason 必须写清为什么安全） */
const ALLOWLIST: Array<{ file: string; reason: string }> = [
  {
    file: "src/lib/api.ts",
    reason: "统一封装本体：自身注入 Authorization（importParse 等上传端点自建 headers）",
  },
  {
    file: "src/lib/ai.ts",
    reason: "流式写作 fetch：init.headers 在上方构造并含 `Bearer ${token}`（:84-90）",
  },
];

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) {
      if (name === "__tests__" || name === "node_modules") continue;
      walk(p, out);
    } else if (name.endsWith(".ts") || name.endsWith(".tsx")) {
      out.push(p);
    }
  }
  return out;
}

/** 取 `fetch(` 起、到配平右括号的整段调用文本（粗略但足够覆盖 URL+init 形态） */
function callText(src: string, openParen: number): string {
  let depth = 0;
  for (let i = openParen; i < src.length; i++) {
    if (src[i] === "(") depth++;
    else if (src[i] === ")") {
      depth--;
      if (depth === 0) return src.slice(openParen, i + 1);
    }
  }
  return src.slice(openParen);
}

describe("鉴权不变量：src 内不得新增未带头部的 fetch", () => {
  it("每个直接 fetch 调用都带 Authorization/authHeaders，或在白名单内", () => {
    // 负向先行断言：排除 refetch(/registerRefetch(/.fetch( 这类同名函数
    const fetchCall = /(?<![A-Za-z0-9_$.])fetch\(/g;
    const allowed = new Set(ALLOWLIST.map((a) => a.file));
    const offenders: string[] = [];
    let scanned = 0;

    for (const abs of walk(SRC)) {
      const rel = relative(FRONTEND_ROOT, abs).split("\\").join("/");
      const src = readFileSync(abs, "utf8");
      for (const m of src.matchAll(fetchCall)) {
        scanned++;
        if (allowed.has(rel)) continue;
        const text = callText(src, m.index! + "fetch".length);
        const hasAuth = text.includes("Authorization") || text.includes("authHeaders");
        if (!hasAuth) {
          const line = src.slice(0, m.index!).split("\n").length;
          offenders.push(`${rel}:${line} :: ${text.replace(/\s+/g, " ").slice(0, 120)}`);
        }
      }
    }

    // 自检：扫到的调用数应大于 0（防 walk/正则失效导致的假绿）。
    // c-fetch-unify 后 src 裸 fetch 已收敛到个位数（SSE/FormData/文本下载等
    // request() 覆盖不了的形态），阈值同步下调——白名单本身仍受第 2 条守卫。
    expect(scanned).toBeGreaterThan(2);
    expect(offenders).toEqual([]);
  });

  it("白名单不超过 2 项（新增例外必须走评审，防止白名单变成后门）", () => {
    expect(ALLOWLIST.length).toBeLessThanOrEqual(2);
  });
});
