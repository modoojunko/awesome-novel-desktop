"""migration — 旧库迁入引擎（db-generation PR1）。

六步＋第 0 步预检（specs：旧库迁入引擎）：
0. 磁盘与安全预检（空间≥源×2、候选≠当前活跃库、可读）
1. 暂存三件套拷贝（源文件此后零接触——含不做 checkpoint）
2. 副本整备（checkpoint TRUNCATE + integrity_check）
3. 列交集计划（NOT NULL 无默认无回填列的表整表跳过并预告）
4. ATTACH ro 副本逐表 INSERT OR IGNORE（FK OFF；app_meta 永不搬；
   预置种子表 PK 幂等）
5. foreign_key_check 只报不删＋书计数对拍
6. 收尾写 migration.* 键（绑定候选身份指纹）＋删暂存

preview 与 result 同构（报告 v:1）；源库在任何失败/中断下字节无损。
"""
