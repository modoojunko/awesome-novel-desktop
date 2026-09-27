"""产物归属单源测试（chapter-rewrite 前置能力）。

- belongs_to_ref：边界感知（主线 ref 不得吞 `-r{8hex}` 旧稿产物）。

原 classify_drift 三分类用例（指纹一致/纯新增/破坏性）随「代内就地补列」退役
删除（c-db-per-version：形状不符不再分类处理，一律分流 `.mismatch-*` 且可作候选
带回，见 tests/test_db_lifecycle.py::test_v3_shape_mismatch_bringable）。
"""


from backup.format import belongs_to_ref


class TestBelongsToList:
    def test_boundary_rewrite_ghost_not_swallowed(self):
        assert belongs_to_ref("vol-1-ch-2-note.md", "vol-1-ch-2") is True
        # 旧稿产物（余段 r{8hex}-）不属于主线 ref
        assert belongs_to_ref("vol-1-ch-2-rabcd1234-note.md", "vol-1-ch-2") is False
        # 但属于旧稿自身 ref
        assert belongs_to_ref("vol-1-ch-2-rabcd1234-note.md", "vol-1-ch-2-rabcd1234") is True

    def test_prefix_collision(self):
        # 第 1 章不得吞第 12 章产物（前缀带边界）
        assert belongs_to_ref("vol-1-ch-12-note.md", "vol-1-ch-1") is False
        assert belongs_to_ref("vol-1-ch-1-note.md", "vol-1-ch-1") is True

    def test_archive_naming(self):
        assert belongs_to_ref("vol-1-ch-1-标题-2026.md", "vol-1-ch-1") is True
        assert (
            belongs_to_ref("vol-1-ch-1-rdeadbeef-标题.md", "vol-1-ch-1") is False
        )
