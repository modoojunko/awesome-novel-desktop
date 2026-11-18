#!/usr/bin/env node
/**
 * 依赖许可证门禁（relicense-proprietary）：读 package-lock.json（v3），
 * 许可证串逐 token 解析（AND / OR / 逗号），token 全部命中白名单才绿，
 * OR 任一不在白名单即红（保守方向正确——宁红勿漏）。
 *
 * 白名单与 client/backend/scripts/check_py_licenses.py 同一立场（含 MPL-2.0/PSF-2.0）。
 * 首个误红请「补白名单」而非改脚本——补白名单是一次许可评审，改脚本等于拆门禁。
 */
import { readFileSync } from "node:fs";

const WHITELIST = new Set([
  "MIT",
  "MIT-0",
  "ISC",
  "Apache-2.0",
  "BSD-2-Clause",
  "BSD-3-Clause",
  "BlueOak-1.0.0",
  "CC0-1.0",
  "CC-BY-4.0",
  "MPL-2.0",
  "PSF-2.0",
  // 许可评审补录（2026-11-18，c-agent 线 dock 依赖树 @agentscope-ai/chat）：
  // - 0BSD（tslib，Microsoft）：无条件许可——LICENSE.txt 原文「Permission to use,
  //   copy, modify, and/or distribute...」无任何条件条款
  // - Unlicense（robust-predicates，Vladimir Agafonkin）：公有领域贡献——node_modules
  //   内 LICENSE 原文「free and unencumbered software released into the public domain」
  "0BSD",
  "Unlicense",
]);

// 人工评审豁免（package.json/lockfile 缺 license 字段，许可经上游证据核实）：
// 证据在案（评审日 2026-11-18），升级依赖若许可证变更则此表不再覆盖、门禁照红。
const REVIEWED_NO_METADATA = new Map([
  // format@0.2.2（Sami Samhuri）：npm registry + 上游 repo package.json 均 MIT
  ["node_modules/format", "MIT"],
  // khroma@2.1.0（fabiospampinato）：GitHub API license.spdx_id=MIT（repo package.json
  // 忘写 license 字段——上游已知疏漏）
  ["node_modules/khroma", "MIT"],
]);

const lock = JSON.parse(readFileSync(new URL("../package-lock.json", import.meta.url), "utf-8"));

/** 许可证串 → token 列表（AND/OR/逗号分隔，大小写不敏感；剥包裹括号；其余比较保留原大小写） */
function tokenize(license) {
  return license
    .split(/\s+(?:AND|OR)\s+|\s*,\s*/i)
    .map((t) => t.trim().replace(/^\(+/, "").replace(/\)+$/, ""))
    .filter(Boolean);
}

const violations = [];
for (const [key, entry] of Object.entries(lock.packages ?? {})) {
  // 根条目（key 为空串）无 license 字段——跳过
  if (key === "") continue;
  const lic = entry.license;
  if (lic == null || typeof lic !== "string" || !lic.trim()) {
    // 元数据缺失但已评审在案的包（REVIEWED_NO_METADATA）按评审结论放行
    if (REVIEWED_NO_METADATA.has(key)) continue;
    violations.push(`${key || "<root>"}: license 缺失（${JSON.stringify(lic)}）`);
    continue;
  }
  const tokens = tokenize(lic);
  if (!tokens.length) {
    violations.push(`${key}: license 空串`);
    continue;
  }
  const bad = tokens.filter((t) => !WHITELIST.has(t));
  if (bad.length) {
    violations.push(`${key}: ${lic}（白名单外: ${bad.join(", ")}）`);
  }
}

if (violations.length) {
  console.error("✗ 依赖许可证门禁未通过（白名单外/缺失）——补白名单请走许可评审，勿改本脚本：");
  for (const v of violations) console.error(`  - ${v}`);
  process.exit(1);
}
console.log("✓ 依赖许可证门禁通过（全部命中白名单）");
