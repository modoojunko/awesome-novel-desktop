## 1. 影响判定与基线

- [x] 1.1 双端影响判定 + 基线：C端 纯后端修复（`auth_local/deps.py`＋`zhuque/router.py`＋测试），唯一前端接触是 e2e 注释同步——design:lint/design:check/原型先行/design-cross 均不适用（无 UI/设计词汇/共享段改动）。基线：worktree `client/backend` 下 `python -m pytest tests/ -q` = **2069 passed, 1 skipped**（解释器用主检出 `.venv`；必须 cd 到 worktree 跑，防静默导主检出代码假绿）
- [x] 1.2 复现（先红）：隔离 TestClient，tier=pro、零大模型配置（`api_configs` 空＋`User.api_key=''`＋config.json 无兜底 Key）→ `PUT /api/v1/zhuque/config` **503**、`POST /api/v1/zhuque/test` **503**，detail 逐字＝`AI 服务未配置 — 请先在设置中填写 API Key`（与用户报障一致）；同场景免费档 → 403 `member_required`
- [x] 1.3 意图核对：`tier-plan-four-tiers` tasks 3.2 自述拦截范围＝免费/标准（只有档位门），实现却复用含 Key 判据的 `require_ai_access` → 越界；2026-10-08 用户拍板三条口径：①配置不分套餐权益（门禁落使用口）②使用口同换键自持门 ③**两个 Key 世界互不顶替**——没配大模型时用大模型的功能就要提示去配大模型，朱雀配不配不影响大模型功能（反向同理）

## 2. 实现

- [x] 2.1 `auth_local/deps.py`：抽 `_require_member_and_tier(user, request)`（会员＋档位两段，原第 0/1/1.5 步逐字迁移）；`require_ai_access` 保留原签名与文案＝两段＋`_check_writing_model_configured(user, db)`（第三段判据抽函数，抛错文案不变）
- [x] 2.2 `auth_local/deps.py`：新增 `require_tier_access(user, request)`（只到会员＋档位，不查大模型 Key）＋模块头注登记两门分工
- [x] 2.3 `zhuque/router.py` 配置域：`PUT/DELETE /config`、`POST /test` 撤掉 `ai_feature("ai-detect")` 与门依赖 → **只挂登录**（拍板①）
- [x] 2.4 `zhuque/router.py` 执行域：`zhuque-check` 门 `require_ai_access` → `require_tier_access`（标注保留）→ 未配朱雀 Key 时返回精确 503 `zhuque_not_configured`（拍板②）
- [x] 2.5 `auth_local/deps.py`：`_check_writing_model_configured` 由「自建一条不看 vendor/不解密的 ApiConfig 查询」改为**复用判定层 `user_has_ai_key`**（可解密口径＋排除 `vendor="zhuque"`；延迟导入防环）——朱雀行不再被当作「已配大模型 Key」；503 文案改 `尚未配置写作大模型 API Key — 去「模型配置 → 写作大模型」添加`（旧文案不区分 Key 归属）。顺带删掉因此不再使用的 `get_local_config` 导入
- [x] 2.6 验证：`grep -n "Depends(require" zhuque/router.py` 仅 1 处（check_chapter）；`require_ai_access` 在朱雀路由零引用、`ai_feature` 仅 1 处（同上）✓

## 3. 回归钉子（全部走真实门依赖，禁整段 override）

- [x] 3.1 `test_zhuque.py` 新增 `local_tier` fixture（隔离 config.json 设档；用完还原路径＋`_reset_config_cache`）与 `_client_real_gate()`（只 override 登录）
- [x] 3.2 `test_config_domain_open_for_all_tiers`：free/standard/pro/trial 四档 × 保存 200（`configured=True`）＋测试 200（`ok=True`）＋删除 200 —— 配置不分套餐权益 ✓
- [x] 3.3 `test_detect_endpoint_gate_keeps_tier`：使用口——free/standard 403、PRO（只配朱雀 Key、零写作模型）200 —— 档位门不因配置域撤门而松 ✓
- [x] 3.4 `test_detect_endpoint_missing_zhuque_key_is_not_generic_503`：PRO、任何 Key 都没有 → 503 且 `reason=zhuque_not_configured`、文案指向朱雀（通用「AI 服务未配置」退役）✓
- [x] 3.5 `test_ai_feature_matrix.py` 增键自持门两用例：`test_tier_only_gate_ignores_missing_key`（pro/trial 无 Key 放行）、`test_tier_only_gate_keeps_tier_blocks`（free/standard 403 两种 reason）✓
- [x] 3.6 `test_zhuque.py` 的 `_client()` 门覆盖补 `require_tier_access`（旧版只绕过 `require_ai_access`；实现期实测漏补即 2 条存量用例被真门拦成 403 而红）✓
- [x] 3.7 `test_ai_feature_matrix.py` 增 `test_zhuque_key_is_not_a_writing_model_key`：只配朱雀（PRO、无写作大模型）→ `require_ai_access` 503 且文案含「大模型」（两个 Key 世界互不顶替）✓
- [x] 3.8 `test_detect_endpoint_missing_zhuque_key_is_not_generic_503` 扩为两段：(a) 任何 Key 都没有 (b) 只配了写作大模型 Key → 均返回 `zhuque_not_configured`（大模型不能顶朱雀）✓
- [x] 3.11 提示词面板（口径④）：`prompt-router` 四端点＋`write/router` 的 `GET /prompt` 换 `require_tier_access`（`ai_feature("prompt-panel")` 保留）；`test_ai_feature_http.py` 增真实 HTTP 门序钉 5 条（free/standard 403；pro/trial 过门进业务 404；生成端点未配 Key 仍 503 且文案含「大模型」）✓
- [x] 3.12 e2e 重写＋**带栈复跑**：`workbench-features.spec.ts` ④b 由「弹窗即报错＋生成键置灰」改为「弹窗照常展示提示词＋生成键可用 → 点生成就地 toast 提示写作大模型 → 不整页跳」——自建隔离栈（zqgate-e2e：C端 8029/5179、S端 19029、本机 classify 桩 45899）实测 **1 passed** ✓
- [x] 3.13 存量用例门覆盖随换门更新（提示词族三文件：`test_prompt_store_db.py`／`test_prompt_summary_batch.py`／`test_export_db_zip.py`）✓
- [x] 3.9 存量用例修正：`test_check_endpoint_free_tier_403` 的覆盖对象由 `require_ai_access` 改为 `require_tier_access`——检测端点换门后旧覆盖不再生效，真门会按运行期 config.json 判档（假绿/假红两可，实测 matrix 先跑时 401 假红）✓
- [x] 3.10 **变异检查**：把任一改动 sed 回原状即红——`zhuque-check` 门回 `require_ai_access` → 3.4 红（通用 503 复现）；实测另一向：把配置域门加回去（`require_ai_access`）→ 3.2 红 ✓

## 4. 门禁与验证

- [x] 4.1 `test_ai_feature_registry.py` 守卫扩为双门（`_has_ai_gate` 认 `require_ai_access` 与 `require_tier_access`）＋头注同步；跑该件全绿（含「扫描器非空转」自检）✓
- [x] 4.2 相关套件：`test_zhuque.py`（22）＋`test_ai_feature_matrix.py`（24）＋`test_ai_feature_registry.py`＋`test_ai_member_gate.py`＋`test_ai_feature_http.py`＋`test_ai_layers.py`＋`test_key_crypto_selfcontained.py` = **162 passed**（门禁/密钥判据相关面全绿）✓
- [x] 4.3 全量后端套件：本分支口径 **2080 passed, 1 skipped**（对拍 1.1 基线 2069/1，差值＝本次新增用例）；**rebase 到最新 main 后复跑 2072 passed, 1 skipped** 零红（下行差值＝#754「提示词 AI 润色全链退役」删除的用例）✓
- [x] 4.10 前端：`npx tsc --noEmit` 通过（e2e 改写后类型面）；vitest 面零 src 改动（仅 e2e spec）✓
- [x] 4.9 顺序无关性（顺带修存量隐患）：`test_zhuque.py` 增 autouse `_own_local_config` 逐用例认领 `CONFIG_FILE`——该全局按**首个 import 者**的 DATA_ROOT 定型、又会被别的模块的 `_seed` 在运行期改指（实测 `pytest tests/test_ai_feature_matrix.py tests/test_zhuque.py` 在**未改动的 main 上本就假红**：只配朱雀的用例读到别人写的 tier=pro＋占位 Key）；认领后 matrix→zhuque／zhuque→matrix 双向 **44 passed** ✓
- [x] 4.8 三条口径的钉子全覆盖：配置域无门（3.2）／使用口键自持门（3.3、3.4）／两个 Key 世界互不顶替（3.7、3.8）；**变异检查三向**（配置域加回门→3.2 红；检测门回旧门→3.4 红；Key 判据换回旧宽松查询→3.7 红）✓
- [x] 4.4 lint：`ruff check --extend-select F811,F821,F841`（CI 钉 ruff==0.16.3 口径）对 `zhuque/router.py`、`auth_local/deps.py`、三个测试文件 → All checks passed ✓
- [x] 4.5 `openspec validate c-zhuque-config-keyless --strict` 通过 ✓
- [x] 4.12 rebase 后复验：最新 main（含 #754 润色全链退役，动过我改的 `workbench-features.spec.ts` 与弹窗源码）rebase 零冲突；栈按 rebase 后代码重建（容器内自证：`polish_write_prompt` 已 0 命中＋本改动特征串在场）后，`zhuque.spec.ts` **2 passed**、`workbench-features ④b` **1 passed** ✓
- [x] 4.11 **真栈真 HTTP 四口径验证**（自建隔离栈跑本分支构建；容器内 grep 特征串自证代码归属）：①免费档 PUT `/zhuque/config` 200（configured=true）＋`/zhuque/test` 200 ok=true＋台账计入 123 tokens，同账号跑检测 403 `member_required`（档位门在使用口）；②PRO＋零写作模型 Key：配置/测试/检测全 200（检测回 3 段、占比 0.66/0.34/0）；③提示词预览 200 有内容、保存 200，点生成 503「尚未配置写作大模型 API Key — 去「模型配置 → 写作大模型」添加」✓
- [x] 4.6 e2e 接触面同步：`zhuque.spec.ts` 模型配置种子注释改为「历史绕行／判据已撤／种子非必需」，种子保留（本机无栈，不做未验证删除）✓
- [x] 4.7 在途 spec 修正：`tier-plan-four-tiers`（未归档）zhuque-config delta 的「配置端点挂 ai-detect 门／非会员 403」段与其 zhuque-detection delta 的「通用 503 先行」注，均按 2026-10-08 拍板就地改正（避免该 change 归档时把相反契约写回主 spec）✓

## 5. 遗留与挂号

- [x] 5.1（带栈）e2e 清理：`e2e-zq-model` 种子已删——`zhuque.spec.ts` 现为「零大模型配置＋朱雀 Key」的真实回归网，带栈复跑 **2 passed** ✓
- [x] 5.2 提示词面板档位口径：**PRO 专属不放松**（2026-10-08 用户口径：不是 PRO 就不能用）——口径④只撤「已配写作大模型 Key」判据，档位门未动；端点级钉子两条（standard → 403 `feature_required`(pro)、pro → 放行）✓
- [ ] 5.3 真机冒烟（随发版）：不配任何写作大模型的 PRO 账号 → 朱雀页签粘贴 Key「保存并测试」应拿到连通结论（不再 503）；免费档账号同页签亦应可保存（不再 403）；随后工作台检测一次

## 6. 评审整改（2026-10-08 review-agent）

- [x] 6.1 **变更档自相矛盾（P2）**：口径④与 e2e 种子清理只回填了 proposal/tasks/specs，design.md 留有相反陈述（Non-Goals「不动 prompt-panel 五端点」、Open Questions「维持现状…Key 判据保留」、Risks/Non-Goals「种子未删」）＋`tasks.md` 4.6 与 5.1／5.2 与 3.11 互相打架＋PR body 仍写「本机无栈未跑」——已全部按实况重写（design.md Context/Goals/Non-Goals/Decisions/Risks/Open Questions，tasks 4.6／5.2 去重），PR 描述同步更新 ✓
- [x] 6.2 **守卫放宽（P3）**：`test_ai_feature_registry` 改为**按 key 分型**——LLM 类 key 只认 `require_ai_access`，键自持门仅白名单 `KEYLESS_GATE_KEYS＝{ai-detect, prompt-panel}` 可用；新增「白名单非空且 ∈ 词汇表」自检场景；变异检查实测：把生成端点错挂键自持门 → 守卫红并点名 `/api/novels/{id}/chapters/{ref}/write -> ai-generate` ✓；`tier-access` delta 同步（错挂门型／白名单失效两场景）
- [x] 6.3 **fixture 全局还原（评审残留项）**：`test_zhuque.py` 的逐用例 `CONFIG_FILE` 认领改为「逐用例认领＋**模块级退出还原**」——不再把本模块的空档位基线留给后续测试文件；复跑双向顺序（matrix↔zhuque）46 passed ✓
- [x] 6.4 整改后门禁复跑：全量 **2073 passed, 1 skipped** 零红（含新增「白名单自检」用例）；ruff All checks passed；`openspec validate --strict` 通过 ✓
