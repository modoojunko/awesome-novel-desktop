# Tasks: s-prompt-pack-delivery（C端 半）

> 前置门槛：用户拍板 5 项产品决策（免费口径/MAX v1/trial/lifetime/迁移节奏）＋S端 半
> （awesome-novel-server 同名 change）端点契约冻结。以下任务在门槛过后按序执行。

- [ ] 0. Design freeze：5 项拍板落档；与 S端 半对齐 key 端点契约（/api/prompt-pack/key
  信封/错误码 401·403·404·429 语义）；latest.json v1 schema 定稿（含 min_pack_version
  召回底线——事后补字段无效）。
- [ ] 1. 原型先行：§5 状态行＋prototypes/book.html 锁定卡四态＋ADJUSTMENTS 登记＋
  design-vocab.mjs 新词两端同批（「写作能力」入 §13）。
- [ ] 2. 后端 loader 改造：receipt 解析序＋min_client_version 拒载＋PromptPackMissing
  ＋读时校验（prompts/__init__.py 收敛点；测试：冻结/开发双态）。
- [ ] 3. 同步器模块：四钩子＋七道校验＋原子安装＋换钥降档重试＋SSRF 防线；
  /auth/verify 挂包状态。
- [ ] 4. 枚举同批扩：AI_STATES/AiState/BLOCK_TEXT 新值＋api.ts 503 白名单。
- [ ] 5. UI：锁定卡四态＋AcctMenu 包版本/诊断串＋手动检查入口。
- [ ] 6. 打包断言反转：build.spec/client-package.yml/build_release.ps1（⏳ 按拍板 5 定
  直切或双源过渡）。
- [ ] 7. e2e：强制包模式钩子＋测试钥夹具＋假 CDN 最小场景组＋存量回归。
- [ ] 8. 回归门禁回填：pytest/vitest/tsc/e2e/design:check（新状态屏）＋发布冒烟
  （下载→验签→装载→test_prompt_layering 同款模板回归）。
