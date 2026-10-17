import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { scanForInlineColors } from "./check-inline-colors.mjs";

describe("内联颜色扫描闸门", () => {
  it("命中内联样式里的颜色函数", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "inline-colors-"));
    fs.writeFileSync(
      path.join(dir, "a.tsx"),
      'export const x = { background: "color-mix(in oklch, var(--a), transparent)" };\n',
      "utf8",
    );
    const findings = scanForInlineColors(dir);
    expect(findings).toHaveLength(1);
    expect(findings[0]).toContain("a.tsx:1");
  });

  it("注释里的提及不算（避免误报）", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "inline-colors-"));
    fs.writeFileSync(
      path.join(dir, "a.ts"),
      "// color-mix(in oklch, red, blue) 只是注释\nexport const x = 1;\n",
      "utf8",
    );
    expect(scanForInlineColors(dir)).toEqual([]);
  });

  it("真实 src 不含内联颜色函数", () => {
    expect(scanForInlineColors("src")).toEqual([]);
  });
});
