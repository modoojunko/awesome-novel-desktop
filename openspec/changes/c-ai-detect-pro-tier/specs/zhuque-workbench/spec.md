## MODIFIED Requirements

### Requirement: 右栏检测行四态

- 「正文」页签 AI 助手卡动作清单末行 SHALL 新增「朱雀 AI 检测 · 查AI味」行（整行可点），行形态 SHALL 随权益与配置四变：
  - 无 ai-detect 权益（免费/试用，快照无该 key）：锁定态——行降透明、名称旁挂「PRO 专属」徽章、描述一句话说明解锁所得与前置条件（「PRO 会员权益 · 升级后整章送腾讯朱雀检测（需自备腾讯云 Key）」），点击走统一升级出口，SHALL NOT 各自弹窗、SHALL NOT 隐藏入口；锁定行 SHALL 保持可点（SHALL NOT 用 disabled 实现——disabled 会吞掉点击，无法走升级出口）。免费档的锁定由既有整卡锁定机制承载（整卡降透明、guard 拦截点击走升级出口），行级锁定变体仅在卡为可交互态时生效（试用档：卡 ready 但无 ai-detect key）。
  - 有权益未配 Key：引导态——虚线行、描述指路（「未配置 Key · 点击去模型配置朱雀页签」），点击跳 `/config?tab=zhuque`。
  - 有权益已配：就绪态，点击发起整章检测；检测中该行呈运行态（边框强调＋转圈占位＋「检测中…」），在途重复点击 SHALL 被防抖。
- 行态判定 SHALL 读 S端 entitlement 快照的 `ai-detect` key（快照单源）：快照存在时 enabled=快照 features 含该 key；快照缺失时按静态注册表兜底（memberOnly ⇒ 未授权，锁定）。权益同步失败时沿用最后已知快照的判定结果（既有机制行为）。权益异常降级态（entitlementDegraded）下锁定行 SHALL 切降级文案变体（「权益状态确认中 · 请稍后重试或联系客服」），SHALL NOT 对已付费作者显示「升级后可用」话术。工作台显示开关为关时，检测行 SHALL 整行不渲染，卡片副行注明「朱雀检测已关闭 · 其余可用」。
- 运行检测期间既有动作行的整卡禁用行为 SHALL 保持（检测为只读测量，秒级返回为常态，不阻塞恢复）。

#### Scenario: 非会员见锁定入口

- Given 免费/试用作者在正文页签右栏
- When 查看动作清单
- Then 检测行可见但降透明、带「PRO 专属」章与一句话说明（含需自备腾讯云 Key 的前置披露）；点击弹统一升级提示，不发任何请求

#### Scenario: MAX 未配 Key 点击跳配置

- Given 有 ai-detect 权益的作者尚未配置朱雀 Key
- When 点击检测行
- Then 跳转模型配置页并落在朱雀页签

#### Scenario: 显示开关关闭时行不渲染

- Given 开关为关
- When 查看右栏
- Then 检测行不存在，其余动作行不受影响

#### Scenario: 快照降级时一律锁定

- Given entitlement 快照缺失或处于降级态（含已发放权益的付费用户）
- When 查看检测行
- Then 呈锁定态（SHALL NOT 因「作者实际有权益」而放行）
