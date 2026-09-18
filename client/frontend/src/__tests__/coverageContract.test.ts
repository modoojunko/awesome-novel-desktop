// 覆盖率契约自检（PR #418 评审 P2 续）：
//   include 的**单一事实源**在 `src/coverage-contract.ts`（config import 它，本测试也读它），
//   所以"两份手写清单互相漂移"这条风险从流程上消失；这里把守三件事：
//   ① 契约文件都存在（重命名/删除必须同步）；
//   ② **目录完整性**——api-config 目录下每个 .tsx 都在契约里（防新增兄弟组件漏进契约，
//      这是"契约外长大"的高频形态）；
//   ③ 配置里的阈值四项 100 + perFile（防被悄悄下调）。
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { COVERAGE_CONTRACT_FILES as CONTRACT_FILES } from "@/coverage-contract";

const FRONTEND = join(__dirname, "..", "..");

/** 从配置文本里取 `include: [...]` 块（括号配对；单一源形态直接返回契约清单本身） */
function configIncludeBlock(): string[] {
  const cfg = readFileSync(join(FRONTEND, "vitest.config.ts"), "utf8");
  // 必须锚定 coverage 段：test.include 也是 `include: [...]`（glob 形态），先匹配会抓错块
  const covAt = cfg.indexOf("coverage: {");
  expect(covAt).toBeGreaterThan(-1);
  const start = cfg.indexOf("include: [", covAt);
  expect(start).toBeGreaterThan(covAt);
  const end = cfg.indexOf("]", start);
  const body = cfg.slice(start, end);
  if (body.includes("COVERAGE_CONTRACT_FILES")) return [...CONTRACT_FILES]; // 单一事实源形态
  return [...body.matchAll(/"(src\/[^"]+\.[cm]?tsx?)"/g)].map((m) => m[1]);
}

describe("覆盖率契约自检", () => {
  it("契约文件都存在（重命名/删除必须同步契约）", () => {
    const missing = CONTRACT_FILES.filter((f) => !existsSync(join(FRONTEND, f)));
    expect(missing).toEqual([]);
  });

  it("配置的 include 与单一事实源一致（config 走 import，不再手写两份清单）", () => {
    expect(configIncludeBlock()).toEqual([...CONTRACT_FILES]);
  });

  /** 目录完整性：该目录下每个 .tsx 都必须在契约里（防新增兄弟文件漏进契约） */
  function expectDirCovered(relDir: string) {
    const dir = join(FRONTEND, relDir);
    // 递归 + 同时收 .ts/.tsx：评审反证过"只扫顶层 .tsx"会漏掉 `pages/x.ts` 与 `pages/sub/x.tsx`
    const files = readdirSync(dir, { recursive: true, encoding: "utf8" })
      .filter((f) => f.endsWith(".tsx") || f.endsWith(".ts"))
      .map((f) => `${relDir}/${f}`);
    const missing = files.filter((f) => !(CONTRACT_FILES as readonly string[]).includes(f));
    expect(missing, `${relDir} 下未纳入契约的文件`).toEqual([]);
  }

  it("目录完整性：api-config 全部 .tsx 都在契约里", () => {
    expectDirCovered("src/components/api-config");
  });

  it("目录完整性：pages 全部 .tsx 都在契约里（批 1 收尾后 pages 已全量纳入）", () => {
    expectDirCovered("src/pages");
  });

  it("阈值四项全 100 且 perFile（语句/行/函数/分支）", () => {
    const cfg = readFileSync(join(FRONTEND, "vitest.config.ts"), "utf8");
    expect(cfg).toMatch(/perFile:\s*true/);
    for (const key of ["statements", "lines", "functions", "branches"]) {
      expect(cfg).toMatch(new RegExp(`${key}:\\s*100`));
    }
  });
});
