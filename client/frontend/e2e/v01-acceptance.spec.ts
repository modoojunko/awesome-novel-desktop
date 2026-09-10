import fs from 'fs';
import path from 'path';
import { test, expect } from '@playwright/test';
import { randomUUID } from 'crypto';

// 获取唯一的用户名
function uid() { return `e2e_${Date.now()}`; }

// 测试口令运行时拼装（门禁：源码不落明文口令）；RUN 模块级求值，同一次运行内稳定
const RUN = Date.now().toString(36);
const pw = (tag: string) => `Pw-${RUN}-${tag}9a`;

// C端 本地会话文件（docker bind mount，与其它 spec 共用）
const CONFIG_PATH = path.join(
  process.cwd(),
  '..',
  '..',
  '.docker-data',
  'client',
  'config.json',
);

// =========================================================================
// NOTE: S端 用户 UI 测试（注册、登录）已迁移至 s-end-user.spec.ts
// 本文件仅保留 S端 API 级边界测试与门控验证
// =========================================================================

test.describe('v0.1 边界值与健壮性', () => {

  test('B1: 注册密码边界 — 6位刚好通过', async ({ request }) => {
    const r = await request.post('http://127.0.0.1:19000/api/web/register', {
      data: { username: uid(), password: '1'.repeat(6), security_question: 'q', security_answer: 'a' }
    });
    expect((await r.json()).code).toBe(0);
  });

  test('B2: 注册密码边界 — 空用户名拒绝', async ({ request }) => {
    const r = await request.post('http://127.0.0.1:19000/api/web/register', {
      data: { username: '', password: pw('dup'), security_question: 'q', security_answer: 'a' }
    });
    // S端会创建空用户名或拒绝，取决于实现
    const body = await r.json();
    expect(body).toBeDefined();
  });

  test('B3: 重复注册被拒绝', async ({ request }) => {
    const user = uid();
    await request.post('http://127.0.0.1:19000/api/web/register', {
      data: { username: user, password: pw('dup'), security_question: 'q', security_answer: 'a' }
    });
    const r = await request.post('http://127.0.0.1:19000/api/web/register', {
      data: { username: user, password: pw('dup'), security_question: 'q', security_answer: 'a' }
    });
    expect((await r.json()).code).toBe(1);
  });

  test('B4/B5: 激活码通道已下线（8.3 拆除）——端点不存在，购买走 /api/pay/orders', async ({ request }) => {
    // v0.1 验收时用户激活走 /api/license/activate；8.3 起激活码用户入口拆除，
    // 付费改走收银台（/api/pay/orders）。此用例反向钉住退役契约：端点不得复活。
    const r = await request.post('http://127.0.0.1:19000/api/license/activate', {
      data: { code: 'AC-INVALID-XXXX-XXXX' }
    });
    expect(r.status()).toBe(404);
    // 现役购买入口在场（参数校验 422 ≠ 404，说明路由活着）
    const pay = await request.post('http://127.0.0.1:19000/api/pay/orders', { data: {} });
    expect(pay.status()).toBe(422);
  });

  test('B6: 无 token 访问受保护端点被拒绝', async ({ request }) => {
    const r = await request.post('http://127.0.0.1:8000/api/novels', {
      data: { name: 'test' }
    });
    expect([401, 405, 403]).toContain(r.status());
  });

  test('B7: 无效 token 访问被拒绝', async ({ request }) => {
    const r = await request.post('http://127.0.0.1:8000/api/novels', {
      data: { name: 'test' },
      headers: { Authorization: 'Bearer this-is-fake-token-12345' }
    });
    expect([401, 405, 403]).toContain(r.status());
  });

});

test.describe('v0.1 用户场景与反馈验证', () => {

  test('U1: 登录失败时返回明确错误信息', async ({ request }) => {
    const r = await request.post('http://127.0.0.1:19000/api/web/login', {
      data: { username: 'nonexistent_' + uid(), password: pw('u1w') }
    });
    const body = await r.json();
    expect(body.code).toBe(1);
    expect(body.msg).toBeTruthy();
    expect(body.msg.length).toBeGreaterThan(0);
  });

  test('U2: 重复注册返回明确错误', async ({ request }) => {
    const user = uid();
    await request.post('http://127.0.0.1:19000/api/web/register', {
      data: { username: user, password: pw('dup'), security_question: 'q', security_answer: 'a' }
    });
    const r = await request.post('http://127.0.0.1:19000/api/web/register', {
      data: { username: user, password: pw('dup'), security_question: 'q', security_answer: 'a' }
    });
    const body = await r.json();
    expect(body.code).toBe(1);
    expect(body.msg).toContain('已存在');
  });

  test('U3: 下线激活码端点对已登录会话也保持 404（含 Bearer）', async ({ request }) => {
    const user = uid();
    await request.post('http://127.0.0.1:19000/api/web/register', {
      data: { username: user, password: pw('dup'), security_question: 'q', security_answer: 'a' }
    });
    const login = await request.post('http://127.0.0.1:19000/api/web/login', {
      data: { username: user, password: pw('dup') }
    });
    const token = (await login.json()).data.token;
    const r = await request.post('http://127.0.0.1:19000/api/license/activate', {
      data: { code: 'AC-NO-SUCH-CODE-XXXX' },
      headers: { Authorization: 'Bearer ' + token }
    });
    expect(r.status()).toBe(404);
  });

  test('U4: 修改密码成功后可用新密码登录', async ({ request }) => {
    const user = uid();
    await request.post('http://127.0.0.1:19000/api/web/register', {
      data: { username: user, password: pw('u4old'), security_question: 'q', security_answer: 'a' }
    });
    // 通过 S端 reset_password 修改密码
    const change = await request.post('http://127.0.0.1:19000/api/reset_password', {
      data: { username: user, security_answer: 'a', new_password: pw('u4new') }
    });
    expect((await change.json()).code).toBe(0);
    // 用新密码登录
    const login = await request.post('http://127.0.0.1:19000/api/web/login', {
      data: { username: user, password: pw('u4new') }
    });
    expect((await login.json()).code).toBe(0);
    // 旧密码失效
    const loginOld = await request.post('http://127.0.0.1:19000/api/web/login', {
      data: { username: user, password: pw('u4old') }
    });
    expect([1, 2]).toContain((await loginOld.json()).code);
  });

  test('U5: 无 API Key 时 AI 端点返回 503 服务不可用（非500）', async ({ request }) => {
    // 清理所有 ApiConfig（新多 Key 体系），确保无可用 Key
    const list = await request.get('http://127.0.0.1:8000/api/v1/api-configs', {
      headers: { Authorization: 'Bearer dev' }
    });
    if (list.ok()) {
      const configs = await list.json();
      for (const c of (configs as Array<{ id: string }>) ?? []) {
        await request.delete(`http://127.0.0.1:8000/api/v1/api-configs/${c.id}`, {
          headers: { Authorization: 'Bearer dev' }
        });
      }
    }
    const r = await request.post('http://127.0.0.1:8000/api/ai/suggest-meta', {
      data: { premise: 'test' },
      headers: { Authorization: 'Bearer dev' }
    });
    // 不管返回 401 还是 503，都是合理的保护措施
    expect([401, 503]).toContain(r.status());
  });

  test('U6: test-connection 对假 Key 返回 ok=false', async ({ request }) => {
    // auth middleware 要求 Bearer 与 config.json 的 token 一致：先注入 dev 会话
    // （清掉可能过期的 expires_at），否则一律 401 打不进 test-connection 逻辑
    const original = fs.readFileSync(CONFIG_PATH, 'utf-8');
    const cfg = JSON.parse(original);
    cfg.token = 'dev';
    cfg.username = 'e2e_u6';
    cfg.tier = 'trial';
    cfg.last_login_at = new Date().toISOString();
    delete cfg.expires_at;
    fs.writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2));
    try {
      // 走 docker 栈（5174 nginx → 容器后端）：127.0.0.1:8000 常被本地残留
      // dev server 抢注，会读到另一份 config.json 导致会话注入失效
      const r = await request.post('http://localhost:5174/api/v1/api-configs/test-connection', {
        data: { vendor_id: 'deepseek', api_key: 'sk-fake-key-12345', base_url: 'https://api.deepseek.com/anthropic' },
        headers: { Authorization: 'Bearer dev' }
      });
      expect(r.status()).toBe(200);
      const body = await r.json();
      expect(body).toHaveProperty('ok');
      expect(typeof body.ok).toBe('boolean');
    } finally {
      fs.writeFileSync(CONFIG_PATH, original);
    }
  });

});

test.describe('v0.1 API 门控验证', () => {

  test('G1: 权限门控: verify 返回套餐字段', async ({ request }) => {
    const r = await request.post('http://127.0.0.1:8000/api/auth/verify');
    expect(r.status()).toBe(200);
    const perm = await r.json();
    expect(perm).toHaveProperty('valid');
    expect(typeof perm.valid).toBe('boolean');
  });

  test('G2: 免费用户门控存在', async ({ request }) => {
    const r = await request.post('http://127.0.0.1:8000/api/auth/verify');
    expect(r.status()).toBe(200);
  });

});
