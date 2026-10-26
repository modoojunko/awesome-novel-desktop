"""update_channel：灰度渠道覆盖文件解析矩阵（c-update-staging-channel）。"""

import update_channel as upc

STAGING_MAIN = upc.STAGING_UPDATE_URL
STAGING_FB = upc.STAGING_UPDATE_URL_FALLBACK


def test_missing_file_is_prod(tmp_path, monkeypatch):
    """不建文件＝无覆盖：候选空、渠道 prod，行为与历史一致。"""
    monkeypatch.setattr(upc, "_CHANNEL_PATH", tmp_path / "update-channel.yaml")
    assert upc.read_override() == {}
    assert upc.override_candidates() == []
    assert upc.channel_name() == "prod"


def test_staging_switch(tmp_path, monkeypatch):
    path = tmp_path / "update-channel.yaml"
    monkeypatch.setattr(upc, "_CHANNEL_PATH", path)
    path.write_text("channel: staging\n", encoding="utf-8")
    assert upc.override_candidates() == [STAGING_MAIN, STAGING_FB]
    assert upc.channel_name() == "staging"


def test_prod_explicit_equals_absent(tmp_path, monkeypatch):
    path = tmp_path / "update-channel.yaml"
    monkeypatch.setattr(upc, "_CHANNEL_PATH", path)
    path.write_text("channel: prod\n", encoding="utf-8")
    assert upc.override_candidates() == []
    assert upc.channel_name() == "prod"


def test_custom_url(tmp_path, monkeypatch):
    path = tmp_path / "update-channel.yaml"
    monkeypatch.setattr(upc, "_CHANNEL_PATH", path)
    path.write_text("update_url: https://example.com/x/latest.json\n", encoding="utf-8")
    assert upc.override_candidates() == ["https://example.com/x/latest.json"]
    assert upc.channel_name() == "custom"


def test_channel_wins_over_update_url(tmp_path, monkeypatch):
    path = tmp_path / "update-channel.yaml"
    monkeypatch.setattr(upc, "_CHANNEL_PATH", path)
    path.write_text("channel: staging\nupdate_url: https://example.com/x.json\n",
                    encoding="utf-8")
    assert upc.override_candidates() == [STAGING_MAIN, STAGING_FB]
    assert upc.channel_name() == "staging"


def test_unknown_channel_beats_update_url(tmp_path, monkeypatch):
    """channel 在场但不认识＝整个覆盖文件不可信，update_url 连带忽略。"""
    path = tmp_path / "update-channel.yaml"
    monkeypatch.setattr(upc, "_CHANNEL_PATH", path)
    path.write_text("channel: beta\nupdate_url: https://example.com/x.json\n",
                    encoding="utf-8")
    assert upc.override_candidates() == []
    assert upc.channel_name() == "prod"


def test_smart_quotes_and_spaces_tolerated(tmp_path, monkeypatch):
    """中文输入法弯引号＋多余空白也认（手打文件容错核心臂）。"""
    path = tmp_path / "update-channel.yaml"
    monkeypatch.setattr(upc, "_CHANNEL_PATH", path)
    path.write_text("channel:  “ Staging ”  \n", encoding="utf-8")
    assert upc.override_candidates() == [STAGING_MAIN, STAGING_FB]
    assert upc.channel_name() == "staging"


def test_bom_tolerated(tmp_path, monkeypatch):
    path = tmp_path / "update-channel.yaml"
    monkeypatch.setattr(upc, "_CHANNEL_PATH", path)
    path.write_bytes("channel: staging\n".encode("utf-8-sig"))
    assert upc.channel_name() == "staging"


def test_bad_yaml_falls_back_to_prod(tmp_path, monkeypatch, caplog):
    path = tmp_path / "update-channel.yaml"
    monkeypatch.setattr(upc, "_CHANNEL_PATH", path)
    path.write_text("channel: [staging\n", encoding="utf-8")
    assert upc.override_candidates() == []
    assert upc.channel_name() == "prod"
    assert any("解析失败" in r.message for r in caplog.records)


def test_unknown_channel_warns(tmp_path, monkeypatch, caplog):
    path = tmp_path / "update-channel.yaml"
    monkeypatch.setattr(upc, "_CHANNEL_PATH", path)
    path.write_text("channel: canary\n", encoding="utf-8")
    assert upc.override_candidates() == []
    assert upc.channel_name() == "prod"
    assert any("未知 channel" in r.message for r in caplog.records)


def test_empty_and_comments_file_is_noop(tmp_path, monkeypatch):
    path = tmp_path / "update-channel.yaml"
    monkeypatch.setattr(upc, "_CHANNEL_PATH", path)
    path.write_text("# 只是注释，未设键\n", encoding="utf-8")
    assert upc.read_override() == {}
    assert upc.override_candidates() == []
    assert upc.channel_name() == "prod"


def test_non_dict_scalar_file_ignored(tmp_path, monkeypatch, caplog):
    path = tmp_path / "update-channel.yaml"
    monkeypatch.setattr(upc, "_CHANNEL_PATH", path)
    path.write_text("just-a-bare-string\n", encoding="utf-8")
    assert upc.override_candidates() == []
    assert upc.channel_name() == "prod"
    assert any("键值形态" in r.message for r in caplog.records)
