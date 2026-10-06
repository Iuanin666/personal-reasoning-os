# 系统架构

Personal OS 使用 Markdown 作为唯一长期真实源。本地 SQLite、FTS5、Embedding 和 chunk 都是可以重建的派生索引。写入使用原子替换与 CAS；分析默认只读。
