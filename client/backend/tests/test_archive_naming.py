"""归档命名单源与安全字符集（c-archive-filename-safety）。

规则源：archive/naming.py（slugify / archive_filename / parse_archive_filename）。
实证四行（proposal 表）+ 截断边界反例（评审 P0）+ 普通标题零漂移，全部锁死。
"""

from pathlib import Path

import pytest

from archive.naming import archive_filename, parse_archive_filename, slugify

REF = "vol-1-ch-1"


class TestSlugifyTable:
    @pytest.mark.parametrize(
        "title,expect",
        [
            ("上/下", "上-下"),          # 路径分隔符 → 连字符
            ("a\\b", "a-b"),            # 反斜杠同款
            ("上/../下", "上-.-下"),      # 分隔符 + 连续点收敛
            ("第1..2章", "第1.2章"),      # 连续点收敛（parse 拒 `..` 子串）
            (".x", "x"),                # 剥首点
            ("第1章.", "第1章"),          # 剥尾点
            ("a" * 49 + ".", "a" * 49),          # 截断边界：尾点剥除（修复前全名出 `..`）
            ("a" * 49 + ".bcdef", "a" * 49),     # 截断后尾点剥除
            ("", ""),
            ("   ", "---"),             # 与旧实现一致（空格换连字符，非空）
            ("第一章 试手", "第一章-试手"),     # 普通标题零漂移
            ("AB CD", "ab-cd"),         # 大小写归一不变
            ("x" * 60, "x" * 50),       # 50 字窗口不变
        ],
    )
    def test_table(self, title, expect):
        assert slugify(title) == expect


class TestFullNameInvariants:
    @pytest.mark.parametrize(
        "title",
        ["上/下", "上/../下", "第1..2章", ".x", "第1章.", "a" * 49 + ".", "a" * 49 + ".bcdef", "", "   ", "a\\b"],
    )
    def test_name_is_safe_and_parsable(self, title):
        name = archive_filename(REF, title)
        # 无路径分隔符、无 `..` 子串（含截断边界）、无独立 `..` 路径段
        assert "/" not in name
        assert "\\" not in name
        assert ".." not in name
        assert ".." not in Path(name).parts
        assert len(Path(name).parts) == 1
        # 与解析器自洽（GET /archives/{filename} 的规范地址恒可寻址）
        parsed = parse_archive_filename(name)
        assert parsed is not None, name
        assert parsed[0] == REF

    def test_normal_titles_byte_identical(self):
        """不含危险字符的标题命名与旧实现（replace(' '→'-')、lower、[:50]）逐字节一致。"""
        def legacy(title: str) -> str:
            return f"{REF}-{(title or '').replace(' ', '-').lower()[:50]}.md"

        for title in ["第一章 试手", "AB CD", "x" * 60, "标题", ""]:
            assert archive_filename(REF, title) == legacy(title), title
