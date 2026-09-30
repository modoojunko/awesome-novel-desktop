"""Storage 门面——书数据全量入库后的唯一存储层（ADR-001/002/003）。

「LocalFileBackend 盘上文件存储」已退役（c-retire-local-file-storage）：
settings KV 与全部业务数据都住 DB，盘上不再承载书数据（获准的盘面读写
各自留在域内：备份导出/成稿下载/loginless 导出直写盘，novel-samples 读
书目录）。本模块只剩 get_storage() 单例门面，直接返回 DatabaseFileBackend；
非 settings 路由的路径读 `{}`、写静默 no-op（DatabaseFileBackend 自带口径）。
"""

from filesystem.db_storage import DatabaseFileBackend

_storage: DatabaseFileBackend | None = None


def get_storage() -> DatabaseFileBackend:
    global _storage
    if _storage is None:
        _storage = DatabaseFileBackend()
    return _storage
