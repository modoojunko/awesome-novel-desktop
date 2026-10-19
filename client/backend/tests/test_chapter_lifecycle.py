"""生命期谓词与全书章号。"""

from types import SimpleNamespace

from chapters.lifecycle import (
    counts_toward_completion,
    is_historical,
    is_imported_archived,
)
from chapters.numbering import global_number_map


def _ch(status, origin="authored", ref="vol-1-ch-1", no=1):
    return SimpleNamespace(status=status, origin=origin, ref=ref, chapter_no=no)


def test_lifecycle_matrix():
    assert is_historical(_ch("draft", "import"))
    assert is_historical(_ch("confirmed", "import"))
    assert not is_historical(_ch("archived", "import"))
    assert is_imported_archived(_ch("archived", "import"))
    assert counts_toward_completion(_ch("archived", "authored"))
    assert not counts_toward_completion(_ch("archived", "import"))
    assert not counts_toward_completion(_ch("draft", "authored"))


def test_global_number_map_two_volumes():
    rows = [
        _ch("draft", ref="vol-2-ch-1", no=1),
        _ch("draft", ref="vol-1-ch-1", no=1),
        _ch("draft", ref="vol-1-ch-2", no=2),
    ]
    m = global_number_map(rows)
    assert m["vol-1-ch-1"] == 1
    assert m["vol-1-ch-2"] == 2
    assert m["vol-2-ch-1"] == 3
