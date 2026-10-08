# c-relay-vendor-entry — 任务

## 1. 前端入口

- [ ] 1.1 `types/api-config.ts` VendorId 加 `relay`；ProviderIcon VENDORS/VENDOR_LABELS 加「中转站 API」（插 Ollama 与 OpenAI 兼容之间）；icons.tsx 加 relay 转发图形
- [ ] 1.2 ApiConfigForm：relay 选中态 cf-hint 中转站口径引导（/v1 填法＋站方令牌＋403 分组权限手填模型 id）；「OpenAI 兼容」hint 反代句改指向中转站按钮
- [ ] 1.3 保存链：relay 选中时保存负载附 `vendor_override: "relay"`（ApiKeyConfigPage.handleFormSubmit / addConfig）
- [ ] 1.4 model-config.css `.vgrid` 桌面 4 列改 3 列（3×3）；窄屏 2 列维持
- [ ] 1.5 前端用例：apiConfigForm（relay 引导可见＋提交带 vendor_override＋OpenAI 兼容 hint 指向句）；apiVendorDefaults（relay 无预填）

## 2. 后端身份登记

- [ ] 2.1 `vendor.py` resolve_vendor 覆写分支展示名映射（relay＝中转站 API、openai-compat＝OpenAI 兼容）
- [ ] 2.2 后端用例：vendor_override=relay 创建 → vendor/展示名落库正确；探测 vendor_id=relay 走 openai 同径（无特例）

## 3. 原型与门禁

- [ ] 3.1 原型 model-config.html 网格补「中转站 API」格＋列数调整；ADJUSTMENTS.md 登记
- [ ] 3.2 门禁：后端 pytest＋ruff；前端 vitest；openspec validate change --strict；design:lint/design:check（基线受扰则重录并登记）
- [ ] 3.3 config-page e2e 补 relay 引导用例（随 scheduled 栈跑）
- [ ] 3.4 真机冒烟：中转站按钮全链（填 lunarfox 地址＋Key→引导可见→保存→卡片展示「中转站 API」→测试/生成）
