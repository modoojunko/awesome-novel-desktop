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
 * ⚠️ **外部进程写库必须让后端重开库**（2026-09-10 事故）：
 * 本脚本以读写方式打开正在被后端使用的 SQLite 库，关闭时 SQLite 会做
 * checkpoint 并**删掉 -wal 文件**；而后端进程仍握着那个「已删除」inode 的句柄，
 * 它从那一刻起的写入全部落进幽灵 WAL——**任何新读者都看不到，重启即丢**。
 * 用户实测症状：「简介/题材点了确认完成，回书架再进来状态没了」。
 * 因此：脚本在收尾时做一次 `wal_checkpoint(TRUNCATE)`，并**重启 C端 后端**
 * （docker compose restart client-backend；`--no-restart` 可关闭，但那就请手动重启）。
 *
 * 用法：
 *   node scripts/sweep-e2e-residue.mjs            # 预演：只报数，不动库
 *   node scripts/sweep-e2e-residue.mjs --apply    # 真删（收尾重启后端）
 *   node scripts/sweep-e2e-residue.mjs --db <path> [--no-restart]
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
export const DEFAULT_DATA_DIR =
  process.env.E2E_SWEEP_DATA_DIR || path.resolve(HERE, "..", "..", "..", ".docker-data", "client");
// E2E_SWEEP_DATA_DIR：会话私有栈必须显式指过来（判例 10-08：默认指向共享
// .docker-data/client——私有栈跑完 teardown 会清共享目录并重启共享容器，踩隔离红线）

/** 库文件名＝C端版本（c-db-per-version）：`novel-v{版本}.db`，dev/PR 构建＝`novel-dev.db`。
 *  旧的固定名 `novel.db` 只作兜底（本 change 之前的落地形态）。多个候选取最新一个。 */
export function resolveDbPath(dataDir = DEFAULT_DATA_DIR) {
  let names = [];
  try {
    names = fs.readdirSync(dataDir);
  } catch {
    return path.join(dataDir, "novel.db");
  }
  const cands = names.filter((n) => /^novel-v[A-Za-z0-9._-]+\.db$/.test(n) || n === "novel-dev.db");
  if (!cands.length) return path.join(dataDir, "novel.db");
  const newest = cands
    .map((n) => ({ n, t: fs.statSync(path.join(dataDir, n)).mtimeMs }))
    .sort((a, b) => b.t - a.t)[0];
  return path.join(dataDir, newest.n);
}

export const DEFAULT_DB = resolveDbPath();

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
 * 在 C端 容器内执行删除（**唯一**允许写这个库的进程＝容器里的应用自身）。
 *
 * 为什么不在宿主删：SQLite 的 WAL 由「打开它的进程」持有，宿主进程写一遍会让容器内
 * 应用的连接读到坏页（实测 `disk I/O error` → `database disk image is malformed`，
 * 且 PRAGMA integrity_check 仍报 ok——只有应用侧炸）。宿主只做两件安全事：
 * **只读扫描**（readOnly 打开）与**删数据目录**（纯 FS）。
 */
function applyInContainer(plan, log, dbPath) {
  const { execFileSync } = require("node:child_process");
  const container = process.env.E2E_CLIENT_BACKEND_CONTAINER || "ai-novel-client-backend";
  const payload = JSON.stringify({
    db: path.basename(dbPath), // 库名随版本变（novel-v{版本}.db / novel-dev.db），按宿主同名取
    novels: plan.testBooks.map((b) => ({ id: b.id, root_path: b.root_path || "" })),
    users: plan.staleUsers.map((u) => u.id),
    configs: plan.staleConfigs.map((c) => c.id),
  });
  const py = [
    "import json, sqlite3, sys",
    "p = json.loads(sys.argv[1])",
    'c = sqlite3.connect("/app/data/" + p["db"])',
    'c.execute("PRAGMA foreign_keys = ON")',
    'c.execute("BEGIN")',
    'for b in p["novels"]:',
    '    c.execute("DELETE FROM token_log WHERE novel_id = ?", (b["id"],))',
    '    if b["root_path"]:',
    '        c.execute("DELETE FROM project_settings WHERE root_path = ?", (b["root_path"],))',
    '    c.execute("DELETE FROM novels WHERE id = ?", (b["id"],))',
    'for uid in p["users"]:',
    '    c.execute("DELETE FROM token_log WHERE user_id = ?", (uid,))',
    '    c.execute("DELETE FROM users WHERE id = ?", (uid,))',
    'for cid in p["configs"]:',
    '    c.execute("DELETE FROM api_configs WHERE id = ?", (cid,))',
    'c.execute("COMMIT")',
    "c.close()",
    'print(json.dumps({"ok": True}))',
  ].join("\n");
  try {
    const out = execFileSync("docker", ["exec", container, "python3", "-c", py, payload], {
      stdio: ["ignore", "pipe", "pipe"],
      timeout: 60_000,
    });
    return JSON.parse(String(out).trim().split("\n").pop() || "{}").ok === true;
  } catch (e) {
    log(`  （容器内删除失败：${String(e.message).split("\n")[0]}）`);
    return false;
  }
}

/**
 * 执行清理。
 * @param {{dbPath?: string, apply?: boolean, log?: (s: string) => void}} opts
 */
export function sweepResidue({
  dbPath = DEFAULT_DB,
  apply = false,
  restartBackend = true,
  log = console.log,
} = {}) {
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

  // 首选：容器内删（宿主写库会写坏容器里活着的库——本会话两次实锤）；失败才回退宿主直连
  let removedInContainer = false;
  try {
    removedInContainer = applyInContainer(plan, log, dbPath);
  } catch {
    removedInContainer = false;
  }
  if (!removedInContainer) {
    log("· ⚠️ 未能在容器内清理，回退宿主直连（可能让运行中的应用读到坏页，建议随后重启后端）");
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
      // 关闭前把 WAL 内容并回主库：这样即使后端此刻正握着旧句柄，
      // 主库也是完整的（后端重启后读到的就是这份）
      try {
        db.exec("PRAGMA wal_checkpoint(TRUNCATE)");
      } catch {
        /* checkpoint 失败不影响已提交的数据 */
      }
      db.close();
    }
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

  if (!restartBackend) {
    log("· ⚠️ 已跳过重启：应用可能仍握着旧句柄（后续请求或读到已删行）——正式流程请让它重启");
  }
  if (restartBackend) {
    const ok = tryRestartBackend(log);
    log(
      ok
        ? "· 已重启 C端 后端（清库后让它重开库，避免旧句柄读到已删行）"
        : "· ⚠️ 未能重启 C端 后端：请手动 `docker restart ai-novel-client-backend`，" +
          "否则后端持有已删除的 WAL、后续写入重启后会丢",
    );
  }
  return { applied: true, dirsRemoved, ...plan };
}

/**
 * 重启 C端 后端（best-effort；在容器里没有 docker 就安静放弃）。
 *
 * 按**容器名**重启而非 `docker compose restart`（#440 收尾复盘）：compose 会按 cwd
 * 解析项目，worktree/并行栈场景下解析到错误项目，曾把另一套栈的容器改名/重建搅局
 * （全量 e2e 中途 123 秒挂的根因）。容器名与被扫的 DEFAULT_DB 数据目录恒同源
 * （compose 的 container_name 硬编码），docker restart 只动这一个容器，不可能波及
 * 别的项目；容器名可用 E2E_CLIENT_BACKEND_CONTAINER 覆盖（真正并行的隔离栈场景）。
 */
function tryRestartBackend(log) {
  try {
    const { execFileSync } = require("node:child_process");
    const container =
      process.env.E2E_CLIENT_BACKEND_CONTAINER || "ai-novel-client-backend";
    execFileSync("docker", ["restart", container], {
      stdio: "pipe",
      timeout: 60_000,
    });
    return true;
  } catch (e) {
    log(`  （重启失败：${e.message.split("\n")[0]}）`);
    return false;
  }
}

// CLI
if (import.meta.url === `file://${process.argv[1]}`) {
  const args = process.argv.slice(2);
  const dbIdx = args.indexOf("--db");
  sweepResidue({
    dbPath: dbIdx >= 0 ? path.resolve(args[dbIdx + 1]) : DEFAULT_DB,
    apply: args.includes("--apply"),
    restartBackend: !args.includes("--no-restart"),
  });
}
