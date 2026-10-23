# 查看器 vendor（图谱.html 内联依赖）

用途：`deconstruct/render.py` 在生成 `图谱.html` 时把下列四个文件按占位符内联进单文件，
保持离线、无 CDN。**升级必须同批更新本表 sha256、`THIRD-PARTY-NOTICES.txt` 四段声明，
及 `tests/test_deconstruct_render.py` 的 hash 断言**（后端测试会校验下表，防供应链漂移）。

| 文件 | 包@版本 | 来源 | sha256 |
|---|---|---|---|
| `cytoscape.min.js` | cytoscape@3.30.2 | https://unpkg.com/cytoscape@3.30.2/dist/cytoscape.min.js | `83e8c54a6bec655bfd81df07df605649c268af69aeca67a5ea2da54ea42dac81` |
| `layout-base.js` | layout-base@2.0.1 | https://unpkg.com/layout-base@2.0.1/layout-base.js | `ec15ab5df9af3f20708f4faab994accf91cda71848cd5bb10a23432cc50b6745` |
| `cose-base.js` | cose-base@2.2.0 | https://unpkg.com/cose-base@2.2.0/cose-base.js | `7cae9509bd36235a63a85e71c8d9fa2cd0bc1d0c1ecc5b5a737976f39d040ddf` |
| `cytoscape-fcose.js` | cytoscape-fcose@2.2.0 | https://unpkg.com/cytoscape-fcose@2.2.0/cytoscape-fcose.js | `4b1cab218d74996aa59cd8473f9239cc6398b8c1774d84d7e59ad9a68959cb57` |

许可（均 MIT，随包 LICENSE-*）：

- `LICENSE-cytoscape`（Copyright (c) 2016-2024, The Cytoscape Consortium）
- `LICENSE-layout-base`（Copyright (c) 2019 iVis@Bilkent）
- `LICENSE-cose-base`（Copyright (c) 2019 - present, iVis@Bilkent.）
- `LICENSE-cytoscape-fcose`（Copyright (c) 2018 - present, iVis-at-Bilkent.）

四段许可全文由 `render.py` 以 `__VENDOR_LICENSES__` 注释岛注入导出的 `图谱.html`
（单文件被单独拷走仍满足署名），应用分发包内 `THIRD-PARTY-NOTICES.txt` 同列、同源更新。
