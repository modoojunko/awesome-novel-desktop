/**
 * Playwright global teardown：跑完全量后清一次 e2e 残留（2026-09-10）。
 *
 * 用例级的 teardown（各 spec 的 restore → cleanupSessionNovels）走产品删除路径，
 * 只能清**成功跑完**的用例自建的书；失败/超时的那本会漏（会话已结束，产品删除
 * 校验归属，事后谁也删不掉），软删除也不释放磁盘。这里在整轮结束后按「测试命名
 * 约定」扫一遍：测试书行 + 孤儿目录 + e2e 建的 api_configs 与用户。
 *
 * 真书/真配置按名字白名单守卫，不会误删；Node < 22.5 没有 node:sqlite → 跳过提示，
 * 绝不让 e2e 因为清理而变红。
 */
export default async function globalTeardown() {
  try {
    const { sweepResidue } = await import("../scripts/sweep-e2e-residue.mjs");
    // E2E_SWEEP_DATA_DIR 缺省时扫共享 .docker-data/client——私有栈（E2E_BASE_URL 非
    // 5174）而未设此变量时**跳过清理**，宁可残留也不碰别人的数据目录（隔离红线）
    const privateStack = !!process.env.E2E_BASE_URL && !process.env.E2E_BASE_URL.includes(":5174");
    if (privateStack && !process.env.E2E_SWEEP_DATA_DIR) {
      console.log("[e2e-cleanup] 跳过：私有栈未设 E2E_SWEEP_DATA_DIR（防误清共享目录）");
      return;
    }
    sweepResidue({ apply: true, log: (s: string) => console.log(`[e2e-cleanup] ${s}`) });
  } catch (e) {
    console.log(`[e2e-cleanup] 跳过：${(e as Error).message}`);
  }
}
