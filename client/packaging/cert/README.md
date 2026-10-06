# 内测自签证书（`cert.pfx`）——给测试同学的说明

这个目录是**内测用**的自签代码签名证书。它的作用只有一个：让**导入过我们根证书的机器**
在安装/查看安装包时，把「发布者」显示成名字（`Awesome Novel (Dev)`），而不是「发布者未知」。

> 对外发布仍然必须用买来的公共 CA 证书——自签证书**不解除** SmartScreen「Windows 已保护
> 你的电脑」，对没导入根证书的机器（也就是所有外部用户）也**仍然显示「发布者未知」**。
> 完整原因与采购选项见 [`docs/ops/client-code-signing.md`](../../../docs/ops/client-code-signing.md)。

## 测试同学：三步

1. **先导入根证书**：右键 `install_cert.bat` → 「以管理员身份运行」（看到「证书安装成功」即可；
   证书密码 `ainovel123` 写在脚本里，不用手输）。
2. **再安装测试包**：发布同学用 `-DevSign` 打出来的 `AwesomeNovel_Setup_v*.exe`。
3. **验一下**（任选其一）：
   - 安装时的 UAC 弹窗里，「发布者」显示 **Awesome Novel (Dev)**（未导入根证书的机器这里是「未知」）；
   - 安装包上右键 → 属性 → **数字签名**页签有签名；
   - 装完后「设置 → 应用 → 已安装的应用」里发布者显示公司名。

**SmartScreen 仍然会拦**（这是预期的，别当成失败）：右键安装包 → 属性 → 底部勾「解除锁定」→ 确定，
再双击安装就不会拦了（去掉「来自互联网」标记）。

## 发布同学：怎么打出这个签名的包

```powershell
cd client\packaging\build
powershell -ExecutionPolicy Bypass -File build_release.ps1 0.27 -DevSign
```

`-DevSign` ＝ 用本目录的 `cert.pfx` 签名（等价于设 `$env:AINOVEL_SIGN_DEV_CERT='1'`）：
程序本体、安装器、卸载器一起签，出包后脚本会校验签名。**别忘了这一步只对导入过根证书的机器有效**。

## 证书本身

- 主体：`CN=Awesome Novel (Dev)`；密码：`ainovel123`；有效期 5 年。
- 重新生成：`python make_dev_cert.py`（用后端 venv 的 Python，需要 `cryptography`）——
  换证书后测试同学要**重跑一次** `install_cert.bat`。
- 这把证书和密码是**公开的内测件**，不用于对外发布；正式签名请走
  `docs/ops/client-code-signing.md` 里的云签名 / USB token 路线。
