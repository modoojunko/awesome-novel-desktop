# c-kb-view-unify · 角色设定页签并入统一实例行列表——档案柜视图退役

## Why

boss 真机走查拍板（2026-11-07）：「这页还是没改的！就用统一的 tab 和行就行了」——角色设定页签
此前特殊切换为档案柜卡片视图（c-charlib-into-kb 时代形态），与统一实例行列表并存两套交互；
新模型下角色实例就是实例（有实例名、字段、归属），统一页签＋行即可表达。

## What Changes

- 角色设定页签与其它类别同构：实例侧来源 → 实例行列表；官方精选/已隐藏 → 知识行回退臂
- CharacterInstanceView（档案柜卡片视图）从知识库页退役并删除（含 4 个专属测试文件）
- 深链 ?concept=角色设定 与 /tools/characters 重定向行为不变（仍预选角色设定页签）

## Impact

- 前端：KnowledgeBasePage（viewMode 门控删除）、CharacterInstanceView.tsx 删除
- spec：knowledge-base「知识库浏览界面」——角色设定视角 bullet 退役
