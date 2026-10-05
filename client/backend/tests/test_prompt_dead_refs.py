"""c-prompt-dead-refs-cleanup 防回归闸门。

两处死代码不得回流：
1. backfill_outlines 的 {settings}/{chapters}——_call_ai 纯 --- 拼接从不 format，
   占位符只能以字面量随文发出（评审拍板删标签而非补 format）；断言走 load_layers
   的 user 段＝真实读取面，且头注释已剥（changelog 提及占位符不误红）。
2. settings/ai_router.py 的 _arc_material 不得再注入 name_rules——prompts/ 已无
   {name_rules} 占位符，注入即死代码回流；inspect.getsource 钉函数（不调用、免 DB
   mock、函数搬家跟着走），不用整文件 grep（未来合法命名会误红）。
"""

import inspect

from prompts import load_layers


def test_backfill_outlines_no_dead_placeholders():
    sys_seg, user_seg = load_layers("backfill_outlines")
    assert isinstance((sys_seg, user_seg), tuple)
    assert user_seg.strip(), "backfill_outlines user 段不应为空"
    assert "settings" not in user_seg and "chapters" not in user_seg, (
        "backfill_outlines 出现 {settings}/{chapters} 类占位符——_call_ai 不 format，"
        "占位符会以字面量发给模型（c-prompt-dead-refs-cleanup）"
    )


def test_arc_material_has_no_name_rules():
    from settings import ai_router

    src = inspect.getsource(ai_router._arc_material)
    # 断言钉字典键字面量 '"name_rules"'——注入只可能是这个形态；注释/其他命名不误红
    assert '"name_rules"' not in src, (
        "_arc_material 又注入该死键——prompts/ 已无对应占位符，注入即死代码"
        "（专名口径规则现状＝arc_* 三模板 system 段内联，见 name_canon.prompt 头注释）"
    )
