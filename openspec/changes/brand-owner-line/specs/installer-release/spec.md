# installer-release Delta

## ADDED Requirements

### Requirement: Windows 发布者元数据署名经营主体

Windows 分发物的发布者展示面 SHALL 署名经营主体（取值与 `brand/brand.json` 的 `company` 键同源）：① 桌面 exe 的 Windows 版本资源——文件属性「详细信息」的公司/版权字段与任务管理器「发布者」列显示主体名，`ProductName`/`FileDescription` 取品牌源（`name`/`name`+`nameEn`），文件版本与同次构建的安装包版本同源（tag 去 `v` 前缀）；② Inno 安装器 `AppPublisher`——「设置 → 应用」与控制面板卸载列表的发布者列、安装器自身版本资源显示主体名。打包流程在品牌源缺少 `company` 键时 MUST 显式失败并给出可定位的报错，MUST NOT 静默产出「发布者: 未知」的安装包。版本资源文件为构建期生成产物，MUST NOT 提交仓库。边界：UAC 提升与首次运行 SmartScreen 弹窗展示的发布者由 Authenticode 证书主体决定，不在本 Requirement 范围内。

#### Scenario: exe 属性页署名主体

- **WHEN** 用户在 Windows 右键安装后的 exe 查看属性「详细信息」，或在任务管理器「详细信息」页查看发布者列
- **THEN** 公司/发布者显示「星纬（海口）投资有限公司」，产品名称为「爱小说」，文件版本与该包 tag 版本一致

#### Scenario: 卸载列表署名主体

- **WHEN** 用户安装后在「设置 → 应用」列表查看该应用
- **THEN** 发布者显示「星纬（海口）投资有限公司」

#### Scenario: 缺主体名拒绝构建

- **WHEN** 品牌源缺失 `company` 键或其为空白串时执行打包
- **THEN** 打包流程以明确报错终止（指出缺失字段与补救方式），不产出任何安装包产物
