# c-window-origin-topleft · 任务

## 1. 影响判定

- [x] 1.1 界面影响判定：无 React 屏改动、无应用内文案（OS 级窗口初始坐标），
      依据 proposal「Design Impact」免原型先行；在 change 目录记录判定结论。

## 2. 壳层（client/packaging/build/pywebview_app.py）

- [x] 2.1 新增 `_window_origin(screen) -> tuple[int, int]`：screen 有 `x`/`y` 属性
      （pywebview 6.x）→ 返回 `(int(screen.x), int(screen.y))`；仅 `resolution`
      元组（5.x）或任何异常 → 返回 `(0, 0)`，不外抛。验证：三臂单测通过。
- [x] 2.2 main() 尺寸块接线：try 块内 `win_x, win_y = _window_origin(screen)`，
      except 分支补 `win_x, win_y = 0, 0`；`create_window` 传 `x=win_x, y=win_y`。
      验证：`create_window` 传参形状断言（`x=win_x`／`y=win_y`／`_window_origin(`
      三串在场）通过。

## 3. 测试（client/backend/tests/test_packaging_shell_apply.py）

- [x] 3.1 `_window_origin` 三臂：假 screen（`x=120, y=80` 属性）→ `(120, 80)`；
      仅 `resolution=(2560, 1440)` 假对象 → `(0, 0)`；属性访问即抛的假对象 →
      `(0, 0)` 且不外抛。
- [x] 3.2 `create_window` 形状断言：源内含 `x=win_x`、`y=win_y`、`_window_origin(`
      三串；存量用例保绿不改钉。

## 4. 回归

- [x] 4.1 后端全量：`cd client/backend && venv/bin/python -m pytest tests/ -q
      --timeout=30`（CI 同口径）退出码 0，记录通过数。
- [x] 4.2 门禁结论登记：未触 `client/frontend`，design:lint/design:check/tsc/
      design-cross 不涉；ruff 闸内（tests 文件）全绿；壳层文件 A/B 对拍无新增账。
      落 change 目录 verification.md。

## 5. 发版与真机验收

- [ ] 5.1 Windows 真机（灰度或晋升后的下一跳/冷启）：新窗落主屏左上角，不再右下角
      级联漂移；记录截图或坐标。
- [ ] 5.2 macOS 冷启：窗口锚定左上角且标题栏不被菜单栏遮挡（若遮挡 → darwin 侧
      `win_y += 28` 平替并在 design.md 记录实测结论）。
- [x] 5.3 OpenSpec 归档随实现 PR：sync `client-shell-startup` ADDED delta 到主 spec，
      change 移入 `openspec/changes/archive/`，`openspec validate --strict` 通过并记录。
