# 任务：退役提示词预览弹窗与死右栏（c-retire-prose-aimodal）

- [x] 1.1 前端删死件：AiModal 组件＋测试；Rail/AiAssistPanel/WriteBlockPanel＋连带测试与覆盖契约条目；lib/promptSources.ts；写法块前端回调链（onWriteBlock/WriteBlockPayload/write_block 解析）
- [x] 1.2 RailChapterData 迁 workbench/railData.ts（OgStats 同迁；去 writeBlock/promptSavedSignal 死字段），更新 NovelWorkspace/ChapterWorkspace 导入
- [x] 1.3 后端删 GET /write/prompt 端点；assemble_write_prompt 单源与文档落点措辞更新
- [x] 2.1 验证：tsc 清零；前端全量 vitest 2284 过；后端 ruff 清零＋相关套件 71 过；openspec validate
- [ ] 2.2 挂账：e2e 旧弹窗用例（prompt-pipeline/workbench-features 里 ai-confirm 段）随入口退役已失效，待真机走查时按新链路重写
