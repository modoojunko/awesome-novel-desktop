"""
write 路由契约测试（qa-night 2026-09-19 P1 回归守卫）：
  「AI 生成正文」端点必须注册在 POST /api/novels/{id}/chapters/{ref}/write——
  write/router.py 的 prefix 已以 /write 结尾，装饰器再写 "/write" 会拼成
  /write/write，前端（lib/ai.ts streamChapterWrite）调 /write 恒 404。
  该缺陷曾存活多版：test_write_regressions 把错误路径钉进了断言（已同批改正）。

  路由表断言走 openapi.json（公开稳定面）：Starlette 1.6 起 app.routes 顶层是
  _IncludedRouter 懒包装、不带 .path，直接遍历会漏（写本测试时的实测）。

用法：
    cd client/backend
    python -m pytest tests/test_write_routes_contract.py -v
"""

import pytest
from fastapi.testclient import TestClient

from main import app

WRITE = "/api/novels/{project_id}/chapters/{chapter_ref}/write"
WRITE_WRITE = WRITE + "/write"


@pytest.fixture(scope="module")
def openapi_paths() -> dict:
    with TestClient(app) as c:
        return c.get("/openapi.json").json()["paths"]


class TestWriteRouteContract:
    def test_generate_prose_registered_at_write(self, openapi_paths):
        """生成正文注册在 POST /write（与前端 streamChapterWrite 调用路径一致）。"""
        assert "post" in openapi_paths.get(WRITE, {}), (
            f"{WRITE} 未注册：AI 生成正文将 404"
        )

    def test_double_write_path_absent(self, openapi_paths):
        """prefix 拼接产生的 /write/write 不得存在（曾让前端恒 404 的病灶）。"""
        assert WRITE_WRITE not in openapi_paths, (
            f"{WRITE_WRITE} 仍在：装饰器路径又叠了 prefix 尾段"
        )

    def test_sibling_routes_unchanged(self, openapi_paths):
        """同族端点不受本修复影响（原本就因前缀拼接恰好正确）。"""
        for sub in ("/prompt", "/prompt/polish", "/quality-check", "/polish"):
            assert "post" in openapi_paths.get(WRITE + sub, {}) or "get" in openapi_paths.get(
                WRITE + sub, {}
            ), f"{WRITE + sub} 缺失"

    def test_continue_route_retired(self, openapi_paths):
        """c-retire-continue-writing：AI 续写端点已退役，防回潮。"""
        assert WRITE + "/continue" not in openapi_paths

    def test_selection_transform_routes_retired(self, openapi_paths):
        """c-retire-selection-transforms：场景扩写/压缩端点已退役，防回潮。"""
        assert WRITE + "/expand" not in openapi_paths
        assert WRITE + "/compress" not in openapi_paths
