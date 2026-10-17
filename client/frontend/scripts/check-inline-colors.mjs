/*
 * 内联样式颜色函数闸门（c-legacy-color-fallback）
 *
 * 旧内核兼容表只覆盖样式表；内联样式里的 oklch()/color-mix() 无法被构建期
 * 编译（Chromium <111 会把整条声明判无效），必须改用设计令牌，或走
 * src/lib/color.ts 的运行时助手。此脚本在 build 前扫描 src 下的 .ts/.tsx。
 */
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const COLOR_FN_RE = /\b(?:oklch|color-mix)\s*\(/;
const SKIP_DIRS = new Set(["node_modules", "__tests__", "coverage", "dist", "e2e"]);

export function stripComments(text) {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:])\/\/.*$/gm, "$1");
}

export function scanForInlineColors(dir) {
  const findings = [];
  const walk = (current) => {
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const full = path.join(current, entry.name);
      if (entry.isDirectory()) {
        if (!SKIP_DIRS.has(entry.name)) walk(full);
        continue;
      }
      if (!/\.(ts|tsx)$/.test(entry.name) || /\.test\.[jt]sx?$/.test(entry.name)) continue;
      const lines = stripComments(fs.readFileSync(full, "utf8")).split("\n");
      lines.forEach((line, idx) => {
        if (COLOR_FN_RE.test(line)) findings.push(`${full}:${idx + 1}: ${line.trim()}`);
      });
    }
  };
  walk(dir);
  return findings;
}

const isCli = process.argv[1] && pathToFileURL(path.resolve(process.argv[1])).href === import.meta.url;
if (isCli) {
  const dir = process.argv[2] ?? "src";
  const findings = scanForInlineColors(dir);
  if (findings.length > 0) {
    console.error(
      "内联样式不得直接写 oklch()/color-mix()（旧内核兼容表只覆盖样式表）。" +
        "请改用设计令牌，或 src/lib/color.ts 的 withAlpha：\n" +
        findings.join("\n"),
    );
    process.exitCode = 1;
  } else {
    console.log(`inline colors: ${dir} 无颜色函数 ✓`);
  }
}
