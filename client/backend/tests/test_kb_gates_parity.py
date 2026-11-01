"""回声闸基线 parity 钉（c-kb-write-block B2）：kb/gates._ECHO_BASELINES 是
write/chapter_writer.py 固定文案的字面副本（kb SHALL NOT import write）——
真源改动时本钉必红提醒同步副本。"""

from write.chapter_writer import WRITE_CLOSING_LINE, refill_instruction


def test_回声基线_收尾行parity():
    from kb.gates import _ECHO_BASELINES

    assert _ECHO_BASELINES[0] == WRITE_CLOSING_LINE


def test_回声基线_分量定性行parity():
    from kb.gates import _ECHO_BASELINES

    # 分量行的固定定性段（to_user_material 内 f-string 的字面尾段）
    assert _ECHO_BASELINES[1] == (
        "动作有回应、局面有推进，这场没写完不进下一场，不得一场两三句带过。"
    )


def test_回声基线_续写指令骨架parity():
    from kb.gates import _ECHO_BASELINES

    line = refill_instruction(1000, 2500, 2250)
    assert _ECHO_BASELINES[2] in line  # 骨架段是续写指令行的固定尾段


def test_回声闸_撞句拒收_改写放行():
    from kb.gates import _check_echo, check_gates

    hit = _check_echo("落点之后不写一个字，收束章停在落点本身别拖。")
    assert hit is not None and "撞句" in hit
    clean = _check_echo("交手先让三招，再借力摔他个措手不及。")
    assert clean is None

    gate = check_gates(concept="手法", instruction="落点之后不写一个字，收束章停在落点本身。", payload={"instruction": "x", "scene": "日常"})
    assert gate.ok is False and "instruction" in gate.errors
