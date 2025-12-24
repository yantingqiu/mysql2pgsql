# mysql2pgsql

English | [中文](README.zh-CN.md)

A utility built on [sqlglot](https://github.com/tobymao/sqlglot) to convert **MySQL-dialect SQL** into **PostgreSQL-dialect SQL**.

> Note: This project focuses on dialect transpilation. For full-database `mysqldump` outputs (DDL/index/storage engine specifics), you may still need manual review or additional rules.

## Requirements

- Python 3.10+

## Install

```bash
pip3 install -r requirements.txt
```

To enable the faster tokenizer (optional Rust extension), follow the note in [requirements.txt](requirements.txt) and replace `sqlglot` with `sqlglot[rs]`.

## Usage

```bash
python mysql2pgsql.py --help
```

This tool supports two input modes (choose one):

- `--sql`: pass SQL text directly
- `--in-file`: read SQL text from a file (multiple statements supported; any file extension)

### 1) Single / multiple SQL statements (via --sql)

Print to terminal:

```bash
python mysql2pgsql.py --sql "SELECT IFNULL(a, 0) AS a FROM t;"
```

Write to a file (also supports `--output-file`):

```bash
python mysql2pgsql.py --sql "SELECT 1;" --out-file output.sql
```

### 2) Batch convert from file (multiple statements)

Input can be any file extension (e.g. `.sql`, `.txt`, or no extension). Use `--output-file` (or `--out-file`) to write results:

```bash
python mysql2pgsql.py --in-file input.sql --out-file output.sql
```

## Output

- Defaults to STDOUT
- If `--output-file` / `--out-file` is provided, writes to that file
- If a statement fails to convert, the tool emits a `-- ERROR: ...` comment to avoid producing invalid SQL

## DDL (CREATE TABLE)

To maximize the chance that generated DDL is **executable on PostgreSQL**, the tool applies extra rewrites for `CREATE TABLE`:

- Extract inline MySQL `KEY` / `INDEX` into standalone `CREATE INDEX`
- Keep `UNIQUE KEY` / `PRIMARY KEY` inside `CREATE TABLE` as constraints (`CONSTRAINT ... UNIQUE (...)` / `PRIMARY KEY (...)`)
- Drop MySQL-only table options (e.g. `ENGINE=...`, `DEFAULT CHARSET=...`, table-level `COLLATE`)
- Drop column-level `COLLATE ...` constraints (MySQL collation names usually don't exist in PostgreSQL)
- Convert `FULLTEXT KEY` into a PostgreSQL GIN index using `to_tsvector('simple', ...)` (you may want to customize the dictionary and expression)

## FAQ

### Q: Does it support multiple SQL statements in one file?

Yes. The tool parses multiple statements (usually separated by `;`) and transpiles them one by one.

### Q: Can sqlglot convert MySQL indexes/keys into 100% executable PostgreSQL DDL?

sqlglot can parse many index-related constructs (e.g. `CREATE INDEX`, `ALTER TABLE ... ADD INDEX/KEY`, and `KEY/UNIQUE KEY/FULLTEXT KEY` inside `CREATE TABLE`).

However, generating fully executable PostgreSQL DDL is not guaranteed for every MySQL feature (e.g. storage engine options, charsets, FULLTEXT semantics). Additional rewrite rules and/or manual review may still be required.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
