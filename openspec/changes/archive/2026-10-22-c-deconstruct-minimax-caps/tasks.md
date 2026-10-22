## 1. 能力表登记

- [x] 1.1 `client/backend/deconstruct/capabilities.py::_VENDOR_KNOWN` 增
      `minimax-m3: ModelCaps(1_000_000, 32_768, source="known")`。上下文 1M 取官方公布值
      （platform.minimax.cn，2026-10-22 查证 M3.1-Flash／M3 均 1M）；输出上限官方未公布，
      取保守地板 32K。验证＝`caps_for(vendor="opencode-go-chat",
      model="minimax-m3.1-flash-free").source == "known"`。
- [x] 1.2 键收窄到 `minimax-m3`（不带代际号会把 M2 系一并放大）：三种 M3 写法（小写
      `minimax-m3.1-flash-free`／驼峰 `MiniMax-M3.1-Flash`／裸 `minimax-m3`）均命中同一条
      登记；M2 系（`MiniMax-M2`／`M2.5-highspeed`／`M2.7`）继续落保守默认。
      验证＝单测三组 M3 写法＋三组 M2 写法全过。

## 2. 中转候选清单

- [x] 2.1 `client/backend/api_configs/connection.py::VENDOR_MODEL_CANDIDATES` 的
      `opencode-go-chat` 增 `minimax-m3.1-flash-free`（OpenCode Go 官方清单 2026-10-22：
      id 带 `-free` 后缀，走通用/OpenAI 格式口）；`opencode-go-claude` 保持 `minimax-m3`
      （anthropic 口）——两口不混投。验证＝单测断言两口各留各的、Go·Claude 系不含 M3.1 id。

## 3. 回归

- [x] 3.1 新增两例：`test_vendor_caps_minimax_m31_flash`（三种 M3 写法均命中能力表＋归并
      预算 24,576＋输入预算 >300k＋卡批 12 章；另钉三种 M2 写法落 `conservative`／卡批 1）、
      `test_opencode_go_candidates_cover_minimax_m31_flash`。
- [x] 3.2 定向套件绿：`test_deconstruct_resilience.py`（30）／`test_modelconfig_gemini_go.py`（21）／
      `test_api_format.py`（89）／`test_deconstruct_api.py`＋`test_deconstruct_pipeline.py`＋
      `test_ai_layers.py`（138 passed, 10 skipped）。
- [x] 3.3 后端全量 **2385 passed / 0 failed**（296 skipped）＋ruff 全绿（改动四文件）。

## 5. 归档

- [x] 5.1 按仓库规矩（归档随实现 PR 走）移档 `openspec/changes/archive/2026-10-22-c-deconstruct-minimax-caps/`；
      `skip_specs: true` 无 delta 待 sync，能力表数据随 c-deconstruct-resilience 归档时进主 spec。

## 4. 待真机验证（不阻塞合入）

- [ ] 4.1 OpenCode Go·通用配置拉清单 → 选 `minimax-m3.1-flash-free` → 拆书创建页选中并探针通过。
- [ ] 4.2 跑一本真书，确认任务账 `caps_note` 显示 context_window=1000000、source=known，
      且归并维度不再因输出截断降级。
- [ ] 4.3 观察 M3.1 Flash 的思考耗时是否影响拆书节奏（思考与输出共用 max_tokens 的既有口径）。
