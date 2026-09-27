## 1. 阶段记账宽容化

- [x] 1.1 `workflow/engine.py` 新增 `advance_phase(project, new_phase)`（只进不退单源：同阶段幂等、
  合法迁移置位、非法回退跳过返 False）。验证＝单测覆盖三态
- [x] 1.2 `volumes/service.py create_volume` 阶段记账改走 `advance_phase`，`init` 行走前进捷径记
  `outline`。验证＝write/prompt 阶段建卷成功且阶段不回退；settings/archive 照常推进
- [x] 1.3 `write/router.py _advance_phase` 委托 `engine.advance_phase`（行为不变）。验证＝既有用例全绿

## 2. 回归测试

- [x] 2.1 `test_volume_chapter_crud`：write/prompt 保持阶段、init→outline、settings/archive→outline 四例
- [x] 2.2 `test_workflow_api`：API 级 write 阶段 `POST /volumes` 返 2xx（回归 500）＋ settings 正常推进一例
- [x] 2.3 红绿对拍：撤掉修复后新增用例红、恢复后绿

## 3. 门禁

- [x] 3.1 后端 pytest 全绿（记录用例数）；`ruff --select F401,F811,F841,F821` 触达路径无新增告警
