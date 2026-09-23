"""s-db-migrate-pipeline — 迁移链治理测试

- 单头断言：多头时 startup `upgrade head` 必抛 MultipleHeads（曾因 fail-open 被掩盖，
  sqlite 路径迁移链从未执行过）
- fresh sqlite `upgrade head` 后 schema 与 ORM 元数据逐表逐列一致：
  a001_users_surrogate 整表重建 users/codes/device_grants/device_registry（显式列清单），
  本测试钉住「重建不得吞并后加的列」（注销四列/refund_requested/token_version/challenge）
- pg_schema.REQUIRED 与 ORM 元数据对拍：模型有而清单无即红（豁免须显式登记）
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from alembic import command


def _cfg() -> Config:
    server_dir = Path(__file__).parent.parent
    cfg = Config()
    cfg.set_main_option("script_location", str(server_dir / "alembic"))
    return cfg


def test_migration_chain_single_head():
    heads = ScriptDirectory.from_config(_cfg()).get_heads()
    assert len(heads) == 1, f"alembic 迁移链出现多头：{heads}——startup upgrade head 必抛 MultipleHeads"


def test_upgrade_head_matches_orm_metadata(tmp_path, monkeypatch):
    fresh = create_engine(f"sqlite:///{tmp_path / 'mig.db'}")
    import app.models.base as base_mod

    # env.py 在线模式用 app.models.base.engine——换成本测试的 virgin 引擎，
    # 使迁移跑在空库上（不受同进程其他测试的 create_all 影响）
    monkeypatch.setattr(base_mod, "engine", fresh)
    command.upgrade(_cfg(), "head")

    insp = inspect(fresh)
    from app.models import Base

    missing: list[str] = []
    for table_name, table in Base.metadata.tables.items():
        if not insp.has_table(table_name):
            missing.append(f"{table_name}:整表缺失")
            continue
        actual = {c["name"] for c in insp.get_columns(table_name)}
        missing += [f"{table_name}.{col.name}" for col in table.columns if col.name not in actual]
    assert not missing, "迁移后 schema 与 ORM 元数据不一致（重建吃列/漏列）：" + ", ".join(missing)


def test_required_schema_list_covers_orm_metadata():
    from app.infrastructure.pg_schema import REQUIRED
    from app.models import Base

    # 登记制豁免：确不进生产必需清单的「表.列」在此登记（注明理由），默认全覆盖
    # - tiers.entitlement / users.agreement_version：pg_http 仓储不读写（dev/sqlite-only
    #   字段），生产门禁不探测——避免对现网手工 DDL 的实际形态误拦
    EXEMPTED: set[str] = {
        "tiers.entitlement",
        "users.agreement_version",
    }
    gaps: list[str] = []
    for table_name, table in Base.metadata.tables.items():
        if table_name not in REQUIRED:
            gaps.append(f"{table_name}:整表未登记")
            continue
        req = {name for name, _ in REQUIRED[table_name]}
        gaps += [
            f"{table_name}.{col.name}"
            for col in table.columns
            if col.name not in req and f"{table_name}.{col.name}" not in EXEMPTED
        ]
    assert not gaps, "pg_schema.REQUIRED 与 ORM 元数据漂移（模型有而清单无，缺失项在部署门禁下不可见）：" + ", ".join(gaps)
