# Tasks — c-nuitka-full

## 1. 清单单源与死条目清理

- [x] 1.1 新建 `bundle_manifest.py`：`DATAS`/`HIDDEN_IMPORTS` 从 build.spec 抽出（release.json 可选项带标记）；build.spec 改消费单源；验证＝python 导入无错＋build.spec 语法自检
- [x] 1.2 清理死条目 `filesystem.composite_storage`、`threads`（PyInstaller 容忍/Nuitka FATAL 的漂移源）；验证＝全清单逐条存在性检查脚本绿
- [x] 1.3 parity 测试：build_nuitka 组装的 include/data 集合 ⊆／⊇ 单源断言；验证＝pytest 新用例绿

## 2. build_nuitka.py 产品化

- [x] 2.1 spike 脚本转正 `build_nuitka.py`：清单走单源、release.json 条件烘焙、Windows 分支（icon/version-file/exe 名）、输出目录 rename `AI Novel`、`build-engine.json` 指纹落资源根；验证＝macOS 本地出包成功＋指纹文件在产物内
- [ ] 2.2 `build.bat`/`build_mac.sh` 加 `BUILD_ENGINE` 开关（默认 pyinstaller）；`requirements.txt` 增 nuitka/ordered-set；验证＝两引擎本地各出一包
- [ ] 2.3 macOS 冒烟：dist 产物启动（启动页→后端就绪→AI 一条链→退出干净）；验证＝冒烟清单逐项过＋启动耗时与 PyInstaller 版对拍记录
  （进度 10-07：启动→后端就绪→退出已过【存活 30s＋loaded×2/ready×2＋隔离 DATA_ROOT 建库】；AI 一条链待登录态补跑。编译耗时对拍：冷 7m38s（991% CPU）/ccache 热 2m24s——CI 分钟数预算依据）

## 3. 扫描门与原生化兼容

- [ ] 3.1 `compile_native.py --scan` 引擎参数分语义：Nuitka 模式＝整树零 .py/.pyc/.pyo＋NATIVE 扩展在位＋特征串；验证＝双引擎各跑 scan 一绿一红样例（红样例人工投放字节码验证闸门会响）
- [ ] 3.2 NATIVE 三模块在 Nuitka 前编译后收进 dist 的验证（.so 被 Nuitka 当 extension 收，不丢）；验证＝产物内三扩展在位＋运行期解密路径通

## 4. Windows 链与安装器

- [ ] 4.1 Windows 首编译演练（build.bat --engine nuitka）：pywebview Windows 后端（pythonnet/clr）缺件消化；验证＝Windows onedir 产物在真机启动
- [ ] 4.2 installer.iss 消费 Nuitka 产物打出安装包＋真机安装冒烟（含 Inno SignTool 签名链）；验证＝安装包装完可启动、卸载干净
- [ ] 4.3 **Windows 真机启动全冒烟（发版硬门槛）**：启动页→后端就绪→提示词包同步→AI 功能一条链→退出干净；验证＝判读表三行＋双日志归因无异常

## 5. CI 灰度与发版演练

- [ ] 5.1 client-package.yml 读 `BUILD_ENGINE`（仓库 Variable，默认空=pyinstaller）；tag 构建灰度启用；验证＝PR 构建仍走 PyInstaller、dispatch 演练一轮全绿
- [ ] 5.2 打包既有门禁双引擎回归：零提示词断言、release.json 八键烘焙断言、验签公钥烘焙断言；验证＝双引擎各跑一轮全绿
- [ ] 5.3 回滚演练：`BUILD_ENGINE=pyinstaller` 一键回退出一版合格产物；验证＝演练记录留档（发版可回退是硬承诺）
