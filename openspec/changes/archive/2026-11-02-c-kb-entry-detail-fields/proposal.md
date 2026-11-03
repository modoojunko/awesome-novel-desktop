# Proposal: c-kb-entry-detail-fields

## Why

规格「知识库浏览界面」原文要求条目详情抽屉含**「字段、正反例、证据只读」**，实现漏了 payload——抽屉只渲染指令/正例/反例/证据四段。c-kb-library-once-migration 合入后 39 张角色卡进了知识库（payload 档案格逐格都在，实测刘望津 10 键），但点开只有一行指令＋来源书名，观感＝「那么多属性就剩一条」（boss 2026-11-02 实报）。

## What Changes

- 详情抽屉新增**通用「字段」段**：`payloadRows(payload)` 概念无关平铺——有值键按存储序出（键, 展示串），数组顿号连、套对象紧凑 JSON、空值跳过；**不做任何角色专用字段/标签**（boss 拍板：知识库不能为了角色单独搞字段显示，要通用的）。
- 键名原样 mono 展示（通用面不做中文标签映射）；角色库页仍走原生卡编辑器，互不影响。

## Impact

- specs: knowledge-base（MODIFIED 知识库浏览界面——补「详情抽屉平铺载荷字段」场景，把已要求的「字段」钉成 scenario）
- 代码：KnowledgeBasePage.tsx（+payloadRows 纯函数＋抽屉一段）
- 测试：knowledgeBasePage.test.tsx（payloadRows 平铺两钉＋抽屉渲染/退场两钉）
