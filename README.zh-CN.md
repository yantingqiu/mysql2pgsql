# mysql2pgsql

[English](README.md) | 中文

一个基于 [sqlglot](https://github.com/tobymao/sqlglot) 的小工具，用于把 **MySQL 方言的 SQL** 转换为 **PostgreSQL 方言的 SQL**。

> 说明：本项目主要做“方言转译”。对于整库 `mysqldump` 的 DDL/索引/存储引擎等差异，可能仍需要人工检查或额外规则处理。

## 环境要求

- Python 3.10+

## 安装依赖

在项目目录执行：

```bash
pip3 install -r requirements.txt
```

如果你想启用更快的 tokenizer（可选 Rust 扩展），请按 [requirements.txt](requirements.txt) 里的注释把 `sqlglot` 替换为 `sqlglot[rs]`。

## 使用方式

```bash
python mysql2pgsql.py --help
```

本工具支持两种输入方式（二选一）：

- `--sql`：直接传入 SQL 文本
- `--in-file`：从文件读取（可包含多条语句；文件扩展名不限）

### 1) 单条/多条 SQL（参数传入）

将结果输出到控制台：

```bash
python mysql2pgsql.py --sql "SELECT IFNULL(a, 0) AS a FROM t;"
```

如果需要保存到文件，可以使用 `--out-file`（或使用 shell 重定向也可以）：

```bash
python mysql2pgsql.py --sql "SELECT 1;" --out-file output.sql
```

### 2) 文件批量转换（支持多语句）

输入文件可以是任意扩展名（例如 `.sql` / `.txt` / 无扩展名），输出文件路径由 `--output-file`（或 `--out-file`）指定：

```bash
python mysql2pgsql.py --in-file input.sql --out-file output.sql
```

## 输出说明

- 默认输出到终端（STDOUT）
- 如果指定 `--output-file` / `--out-file`，则写入文件
- 若某条语句转换失败，会输出一行 `-- ERROR: ...` 注释，避免生成不可执行的 SQL

## DDL（CREATE TABLE）说明

为尽量生成 **PostgreSQL 可直接执行** 的 DDL，本工具会对 `CREATE TABLE` 做额外处理：

- 将 MySQL 的内联 `KEY` / `INDEX` 提取为独立的 `CREATE INDEX`
- 保留 `UNIQUE KEY` / `PRIMARY KEY` 在 `CREATE TABLE` 中作为约束（`CONSTRAINT ... UNIQUE (...)` / `PRIMARY KEY (...)`）
- 移除 MySQL-only 的表选项（例如 `ENGINE=...`、`DEFAULT CHARSET=...`、表级 `COLLATE`）
- 移除列级 `COLLATE ...` 约束（MySQL collation 名称通常不能直接在 PostgreSQL 使用）
- 将 `FULLTEXT KEY` 转换为 PostgreSQL 的 GIN 索引（使用 `to_tsvector('simple', ...)`；你可能需要按业务调整词典与表达式）

## 常见问题

### Q: 一个文件里有多条 SQL 能处理吗？

可以。工具会解析输入文本中的多条语句（通常以 `;` 分隔），逐条转译并输出。

### Q: sqlglot 能不能把 MySQL 的索引/KEY 100% 转成 PostgreSQL 可执行 DDL？

sqlglot 可以解析很多索引相关语法（如 `CREATE INDEX`、`ALTER TABLE ... ADD INDEX/KEY`、以及 `CREATE TABLE` 内的 `KEY/UNIQUE KEY/FULLTEXT KEY`）。

但“直接生成可在 PostgreSQL 执行的完整 DDL”并不保证 100% 成功：例如 `ENGINE=InnoDB`、`DEFAULT CHARSET`、`FULLTEXT` 的实现方式在两边差异很大，通常需要额外的规则处理或人工校对。

## 许可证

本项目使用 MIT 许可证发布，详见 [LICENSE](LICENSE)。
