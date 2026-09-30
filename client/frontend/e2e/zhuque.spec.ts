// 朱雀 AI 检测工作台 e2e（c-zhuque-ai-detect）。
// 运行前提（任务组8 全门禁）：隔离栈后端含 zhuque 模块，且 ZHUQUE_API_BASE 指向
// classify 桩（compose 环境变量）；未部署桩的环境本 spec 自动跳过——
// 探测 /api/v1/zhuque/config 不可达（非 JSON）即视为未部署。
// 锚点：rail-zhuque-check / zhuque-head-strip / zq-clear / zq-rerun /
//       zhuque-show-switch / zhuque-restale（见 tasks 8.1）。
import { expect, test } from "@playwright/test";

const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5174/";

test.describe("朱雀 AI 检测（工作台三处消费点）", () => {
  test("右栏检测行存在且与结果条联动", async ({ page }) => {
    const deployed = await page.request
      .get(`${ORIGIN}api/v1/zhuque/config`)
      .then((r) => r.status() !== 404)
      .catch(() => false);
    test.skip(!deployed, "隔离栈未部署 zhuque 模块——任务组8 换包后启用");

    await page.goto(ORIGIN);
    // 进入写作台正文页签（书架 → 首本书 → 写作视图由 seed 保证 1 卷 1 章）
    await page.getByText("沙漏之下").click();
    await page.getByRole("button", { name: "写作" }).first().click().catch(() => {});
    await page.getByRole("tab", { name: /正文/ }).click();

    // 就绪态行存在（MAX＋已配 Key 种子）
    const row = page.getByTestId("rail-zhuque-check");
    await expect(row).toBeVisible();

    // 点击发起检测（后端桩返回固定三占比＋段落标注）
    await row.click();
    const strip = page.getByTestId("zhuque-head-strip");
    await expect(strip).toBeVisible();
    await expect(strip).toContainText("人工");
    await expect(strip).toContainText("概率参考 · 非平台判定");

    // 正文行标注：疑似段黄底、行尾置信度章
    await expect(page.locator(".editor p.zq-warn").first()).toBeVisible();
    await expect(page.locator(".zq-mark").first()).toBeVisible();

    // 清除标注＝结果条与标注一并退场
    await page.getByTestId("zq-clear").click();
    await expect(strip).toBeHidden();
  });
});
