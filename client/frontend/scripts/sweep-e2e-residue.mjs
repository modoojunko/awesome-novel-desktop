#!/usr/bin/env node
/**
 * e2e 残留清理（用户 2026-09-10 拍板「可以」）。
 *
 * 为什么需要它：用例收尾的 teardown 走产品删除路径（软删除自己名下的书），
 * 但**失败/超时的用例**会漏——它的书是那个 e2e 会话建的，产品删除校验归属，
 * 事后连本机真账号也删不掉（实测 404）。加上软删除本身不释放磁盘，
 * 于是本地库会慢慢积：测试书行、盘上数据目录、e2e 建的 api_configs 与用户。
 *
 * 口径（全部按「测试命名约定」白名单式守卫，绝不碰真书名/真配置）：
 *   · 测试书 = 名字匹配 /[0-9]{1,8}$/ 或 ^(e2e|probe)[-_]
 *   · 只删测试名的行 + 它们的专属数据目录；孤儿目录（无对应书）也清
 *   · e2e 用户：只删 ^(e2e|probe)[-_] 且名下没有存活的书（不会孤立任何内容）
 *
 * 用法：
 *   node scripts/sweep-e2e-residue.mjs            # 预演：只报数，不动库
 *   node scripts/sweep-e2e-residue.mjs --apply    # 真删
 *   node scripts/sweep-e2e-residue.mjs --db <path>
 *
 * 也作为 Playwright 的 globalTeardown 被调用（见 e2e/global-teardown.ts，
 * 传 apply=true）。Node < 22.5 没有 node:sqlite → 跳过并提示，不让 e2e 变红。
 */

import fs from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

// ESM 里没有 require：node:sqlite 是内置模块，用 createRequire 做「有就加载、没有就算了」
const require = createRequire(import.meta.url);

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const DEFAULT_DB = path.resolve(HERE, "..", "..", "..", ".docker-data", "client", "novel.db");

/** e2e 会话注册出来的用户（前缀即 spec 的 session 名）。 */
const TEST_USER_RE = /^(e2e|probe|mm|shot)[-_]/;

/** 测试命名约定（与 e2e/helpers.ts::isTestBookName 同口径）。 */
export function isTestName(name) {
  const n = name || "";
  return /[0-9]{1,8}$/.test(n) || /^(e2e|probe)[-_]/.test(n);
}

function loadSqlite() {
  try {
    // Node ≥ 22.5 内置；更早的版本没有，直接跳过（CI 用 Node 20）
    return require("node:sqlite");
  } catch {
    return null;
  }
}

/** 数据根目录（DB 同级的每个子目录＝一本书的资产目录）。 */
function dataRootOf(dbPath) {
  return path.dirname(dbPath);
}

/** 这些顶层项永远不动（设备会话、密钥、库文件本体）。 */
const PROTECTED = new Set(["config.json", ".fernet_key"]);

/**
 * 扫描（不写库）：返回各类残留清单。
 * @param {string} dbPath
 */
export function scanResidue(dbPath) {
  const sqlite = loadSqlite();
  if (!sqlite) return { skipped: "node:sqlite 不可用（需要 Node ≥ 22.5）", };

  const { DatabaseSync } = sqlite;
  const db = new DatabaseSync(dbPath, { readOnly: true });
  try {
    const novels = db.prepare("SELECT id, name, root_path, status FROM novels").all();
    const testBooks = novels.filter((n) => isTestName(n.name));
    const keepBooks = novels.filter((n) => !isTestName(n.name));
    const aliveNames = new Set(keepBooks.map((n) => n.name));

    const configs = db.prepare("SELECT id, name FROM api_configs").all();
    const staleConfigs = configs.filter((c) => isTestName(c.name));

    // C端 users 的「用户名」就是主键 id（如 e2e_md_...、modoojunko）
    const users = db.prepare("SELECT id FROM users").all();
    const aliveBookUsers = new Set(
      novels.filter((n) => n.status !== "deleted" && isTestName(n.name)).map((n) => n.user_id),
    );
    const staleUsers = users.filter(
      (u) => TEST_USER_RE.test(u.id || "") && !aliveBookUsers.has(u.id),
    );

    // 孤儿目录：数据根下没有对应「存活书」的目录（书名即 slug）
    const root = dataRootOf(dbPath);
    const dirs = fs.existsSync(root)
      ? fs
          .readdirSync(root, { withFileTypes: true })
          .filter((d) => d.isDirectory())
          .map((d) => d.name)
          .filter((name) => !PROTECTED.has(name) && !aliveNames.has(name))
      : [];

    return { testBooks, keepBooks, staleConfigs, staleUsers, orphanDirs: dirs, dbPath };
  } finally {
    db.close();
  }
}

/**
 * 执行清理。
 * @param {{dbPath?: string, apply?: boolean, log?: (s: string) => void}} opts
 */
export function sweepResidue({ dbPath = DEFAULT_DB, apply = false, log = console.log } = {}) {
  const sqlite = loadSqlite();
  if (!sqlite) {
    log("· 跳过残留清理：当前 Node 没有 node:sqlite（需 ≥ 22.5）");
    return { skipped: true };
  }
  if (!fs.existsSync(dbPath)) {
    log(`· 跳过残留清理：找不到 ${dbPath}`);
    return { skipped: true };
  }

  const plan = scanResidue(dbPath);
  log(
    `残留扫描：测试书 ${plan.testBooks.length} 本 · 孤儿目录 ${plan.orphanDirs.length} 个 · ` +
      `e2e 配置 ${plan.staleConfigs.length} 条 · e2e 用户 ${plan.staleUsers.length} 个 · ` +
      `（保留 ${plan.keepBooks.length} 本真书：${plan.keepBooks.map((b) => b.name).join("、") || "无"}）`,
  );
  if (!apply) {
    if (plan.testBooks.length) {
      log(`  预演示例：${plan.testBooks.slice(0, 3).map((b) => b.name).join("、")} …`);
    }
    log("（预演模式：加 --apply 才真删）");
    return { applied: false, ...plan };
  }

  const { DatabaseSync } = loadSqlite();
  const db = new DatabaseSync(dbPath);
  try {
    db.exec("PRAGMA foreign_keys = ON");
    db.exec("BEGIN");
    // token_log 是 NO ACTION，必须先删；其余靠 novels 的 CASCADE 清干净
    const delTokenLog = db.prepare("DELETE FROM token_log WHERE novel_id = ?");
    const delSettings = db.prepare("DELETE FROM project_settings WHERE root_path = ?");
    const delNovel = db.prepare("DELETE FROM novels WHERE id = ?");
    for (const b of plan.testBooks) {
      delTokenLog.run(b.id);
      if (b.root_path) delSettings.run(b.root_path);
      delNovel.run(b.id);
    }
    // e2e 用户：先清其 token_log（NO ACTION），再删用户（api_configs/审计日志 CASCADE）
    const delUserTokenLog = db.prepare("DELETE FROM token_log WHERE user_id = ?");
    const delUser = db.prepare("DELETE FROM users WHERE id = ?");
    for (const u of plan.staleUsers) {
      delUserTokenLog.run(u.id);
      delUser.run(u.id);
    }
    // 陈旧 e2e 配置（书的 ai_config_id 是 SET NULL，不会连带删书）
    const delConfig = db.prepare("DELETE FROM api_configs WHERE id = ?");
    for (const c of plan.staleConfigs) delConfig.run(c.id);
    db.exec("COMMIT");
  } catch (e) {
    try {
      db.exec("ROLLBACK");
    } catch {
      /* 回滚失败不掩盖原错 */
    }
    log(`· 残留清理失败（已回滚）：${e.message}`);
    return { skipped: true, error: String(e) };
  } finally {
    db.close();
  }

  // 目录清理放在事务之后：库先干净，目录再对齐（删不掉只影响磁盘）
  let dirsRemoved = 0;
  const root = dataRootOf(dbPath);
  for (const name of plan.orphanDirs) {
    if (PROTECTED.has(name) || PROTECTED.has(name.replace(/^\./, "."))) continue;
    try {
      fs.rmSync(path.join(root, name), { recursive: true, force: true });
      dirsRemoved += 1;
    } catch {
      /* 单个目录失败继续 */
    }
  }
  log(
    `· 已清理：测试书 ${plan.testBooks.length} 本 · e2e 用户 ${plan.staleUsers.length} 个 · ` +
      `e2e 配置 ${plan.staleConfigs.length} 条 · 目录 ${dirsRemoved} 个`,
  );
  return { applied: true, dirsRemoved, ...plan };
}

// CLI
if (import.meta.url === `file://${process.argv[1]}`) {
  const args = process.argv.slice(2);
  const dbIdx = args.indexOf("--db");
  sweepResidue({
    dbPath: dbIdx >= 0 ? path.resolve(args[dbIdx + 1]) : DEFAULT_DB,
    apply: args.includes("--apply"),
  });
}
