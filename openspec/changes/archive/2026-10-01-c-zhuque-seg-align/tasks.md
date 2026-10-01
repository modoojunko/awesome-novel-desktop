# Tasks：c-zhuque-seg-align

## 1. 后端对齐制

- [x] 1.1 `zhuque/segmentation.py` 新增 `align_segments(paragraphs, seg_labels)`：各段 `text` 按序拼接校验
      （不等 → `ValueError("segment_mismatch")`）；段落归属＝字符区间起点所在上游段（两指针）；
      返回 `[{"paragraph_index","label","confidence"}]` 逐非空段一条
- [x] 1.2 `zhuque/service.py` `check_chapter` 接线：撤「段数比对」改调 `align_segments`；错误映射表零改动

## 2. 测试

- [x] 2.1 `_stub_classify` 桩重写：按请求文本构造合并分段（`merge_every=2` 默认，模拟真实上游合并）；
      各既有调用点适配
- [x] 2.2 用例更新：成功映射（合并后仍逐段 3 条）；「段数不符」改「text 拼接不等」（截断样本 → segment_mismatch）；
      新增「合并段共享 label/conf」断言；全量 pytest 绿

## 3. 验收

- [x] 3.1 `openspec validate --strict` 过
- [x] 3.2 真实章节（vol-1-ch-3 投名状，1512 字 34 段）导入新代码打真实上游：
      200、34 条段落级标注、无 uncovered
