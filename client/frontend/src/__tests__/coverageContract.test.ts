// 覆盖率契约自检（PR #418 评审 P2）：`vitest.config.ts` 的 include 是**手写清单**——
// 文件被重命名/删除时契约会静默缩小（跑起来仍 100%，只是分母变少）。这里把清单钉住：
// 改 include 必须同步本文件，删/改文件必须同步两处。
import { readFileSync } from "node:fs";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const FRONTEND = join(__dirname, "..", "..");

/** 与 vitest.config.ts 的 coverage.include 一一对应（本次交付触及的 5 个文件） */
const CONTRACT_FILES = [
  "src/lib/api.ts",
  "src/lib/nodeTitle.ts",
  "src/components/novel/workbench/ManuscriptDownloadModal.tsx",
  "src/components/RestoreModal.tsx",
  "src/components/AcctMenu.tsx",
];

describe("覆盖率契约自检", () => {
  it("5 个契约文件都存在（重命名/删除必须同步契约）", () => {
    const missing = CONTRACT_FILES.filter((f) => !existsSync(join(FRONTEND, f)));
    expect(missing).toEqual([]);
  });

  it("vitest.config.ts 的 include 与自检清单一致（防静默扩/缩分母）", () => {
    const cfg = readFileSync(join(FRONTEND, "vitest.config.ts"), "utf8");
    const listed = [...cfg.matchAll(/"(src\/[^"]+\.tsx?)"/g)].map((m) => m[1]);
    expect(listed.sort()).toEqual([...CONTRACT_FILES].sort());
  });

  it("阈值四项全 100（语句/行/函数/分支）", () => {
    const cfg = readFileSync(join(FRONTEND, "vitest.config.ts"), "utf8");
    const m = cfg.match(/thresholds:\s*\{([^}]*)\}/);
    expect(m).toBeTruthy();
    for (const key of ["statements", "lines", "functions", "branches"]) {
      expect(m![1]).toContain(`${key}: 100`);
    }
  });
});
