"""novel-deconstruct-sdk 一期：知识映射＋载荷校验＋树索引（纯核心零应用层依赖）。"""

from .mapping import EntryData, genre_from_products, map_deconstruct_products
from .taxonomy import TaxonomyIndex

__all__ = [
    "EntryData",
    "TaxonomyIndex",
    "genre_from_products",
    "map_deconstruct_products",
]
