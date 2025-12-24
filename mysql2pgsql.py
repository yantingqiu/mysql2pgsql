from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import sys
from typing import Iterable, List, Optional

import sqlglot
from sqlglot import exp


@dataclass(frozen=True)
class ConversionResult:
    postgres_sql: Optional[str]
    error: Optional[str] = None


_DEFINER_RE = re.compile(
    r"\bDEFINER\s*=\s*`[^`]+`\s*@\s*`[^`]+`\s*",
    flags=re.IGNORECASE,
)


def _preprocess_mysql_sql(sql_text: str) -> str:
    """Best-effort cleanup of MySQL-only clauses before parsing."""
    # MySQL view/proc definer clause has no direct PG equivalent.
    sql_text = _DEFINER_RE.sub("", sql_text)
    return sql_text


def _is_collate_column_constraint(column_constraint: exp.Expression) -> bool:
    kind = getattr(column_constraint, "args", {}).get("kind")
    return kind is not None and kind.__class__.__name__ == "CollateColumnConstraint"


def _is_on_update_column_constraint(column_constraint: exp.Expression) -> bool:
    kind = getattr(column_constraint, "args", {}).get("kind")
    return kind is not None and kind.__class__.__name__ == "OnUpdateColumnConstraint"


def _is_auto_increment_column_constraint(column_constraint: exp.Expression) -> bool:
    kind = getattr(column_constraint, "args", {}).get("kind")
    return kind is not None and kind.__class__.__name__ == "AutoIncrementColumnConstraint"


def _strip_column_collations(schema: exp.Schema) -> None:
    for element in list(schema.expressions or []):
        if not isinstance(element, exp.ColumnDef):
            continue
        constraints = list(element.args.get("constraints") or [])
        if not constraints:
            continue
        filtered = [c for c in constraints if not _is_collate_column_constraint(c)]
        if filtered != constraints:
            element.set("constraints", filtered)


def _strip_on_update_constraints(schema: exp.Schema) -> List[str]:
    """Remove MySQL ON UPDATE column constraints and return TODO messages."""
    todos: List[str] = []

    for element in list(schema.expressions or []):
        if not isinstance(element, exp.ColumnDef):
            continue
        constraints = list(element.args.get("constraints") or [])
        if not constraints:
            continue

        had_on_update = any(_is_on_update_column_constraint(c) for c in constraints)
        if not had_on_update:
            continue

        filtered = [c for c in constraints if not _is_on_update_column_constraint(c)]
        element.set("constraints", filtered)

        col_name = element.this.sql(dialect="postgres")
        todos.append(
            f"-- TODO: column {col_name} used MySQL 'ON UPDATE CURRENT_TIMESTAMP'; implement via trigger in PostgreSQL"
        )

    return todos


def _rewrite_auto_increment_to_identity(schema: exp.Schema) -> None:
    """Rewrite MySQL AUTO_INCREMENT into PostgreSQL IDENTITY."""
    for element in list(schema.expressions or []):
        if not isinstance(element, exp.ColumnDef):
            continue
        constraints = list(element.args.get("constraints") or [])
        if not constraints:
            continue

        if not any(_is_auto_increment_column_constraint(c) for c in constraints):
            continue

        filtered = [c for c in constraints if not _is_auto_increment_column_constraint(c)]
        filtered.append(exp.ColumnConstraint(kind=exp.GeneratedAsIdentityColumnConstraint()))
        element.set("constraints", filtered)


def _rewrite_unsigned_integer_types(schema: exp.Schema) -> None:
    """Rewrite MySQL UNSIGNED integer pseudo-types to PostgreSQL-valid types.

    sqlglot may emit UINT/UBIGINT which PostgreSQL doesn't support as native types.
    We map:
      - UINT -> BIGINT
      - UBIGINT -> NUMERIC(20, 0)
    """
    for element in list(schema.expressions or []):
        if not isinstance(element, exp.ColumnDef):
            continue
        kind = element.args.get("kind")
        if not isinstance(kind, exp.DataType):
            continue

        dt = kind
        if dt.this == exp.DataType.Type.UINT:
            element.set("kind", exp.DataType.build("BIGINT"))
        elif dt.this == exp.DataType.Type.UBIGINT:
            element.set("kind", exp.DataType.build("NUMERIC(20, 0)"))


def _rewrite_unique_constraints(schema: exp.Schema) -> None:
    """Rewrite MySQL-style UNIQUE KEY syntax into PostgreSQL CONSTRAINT UNIQUE syntax.

    sqlglot may render MySQL unique keys as `UNIQUE "name" (col)` inside CREATE TABLE,
    which is not valid PostgreSQL. PostgreSQL expects `CONSTRAINT name UNIQUE (col)`.
    """
    rewritten: List[exp.Expression] = []

    for element in list(schema.expressions or []):
        if isinstance(element, exp.UniqueColumnConstraint) and isinstance(element.this, exp.Schema):
            unique_schema = element.this
            constraint_name = unique_schema.this
            cols = list(unique_schema.expressions or [])

            inner = exp.UniqueColumnConstraint(this=exp.Schema(expressions=cols))
            rewritten.append(exp.Constraint(this=constraint_name, expressions=[inner]))
        else:
            rewritten.append(element)

    schema.set("expressions", rewritten)


def _index_column_sql(expression: exp.Expression) -> str:
    # sqlglot represents index columns as Ordered(...) and may include NULLS FIRST.
    # PostgreSQL requires ASC/DESC to use NULLS FIRST/LAST, so we drop NULLS ordering.
    if isinstance(expression, exp.Ordered):
        base = expression.this.sql(dialect="postgres")
        if expression.args.get("desc"):
            return f"{base} DESC"
        if expression.args.get("asc"):
            return f"{base} ASC"
        return base
    return expression.sql(dialect="postgres")


def _format_identifier_or_column_for_tsvector(expr: exp.Expression) -> str:
    # Expect Identifier/Column; fall back to expression SQL.
    base = expr.sql(dialect="postgres")
    return f"COALESCE({base}::text, '')"


def _fulltext_gin_expression(columns: List[exp.Expression]) -> str:
    # Concatenate columns with spaces to approximate MySQL FULLTEXT behavior.
    if not columns:
        return "''"
    if len(columns) == 1:
        return _format_identifier_or_column_for_tsvector(columns[0])
    parts = [f"{_format_identifier_or_column_for_tsvector(c)}" for c in columns]
    return " || ' ' || ".join(parts)


def _commented_sql_block(todo: str, original_sql: str) -> str:
    lines = [f"-- TODO: {todo}"]
    for line in original_sql.strip().splitlines():
        lines.append(f"-- {line}")
    return "\n".join(lines).rstrip() + "\n"


def _convert_create_table_to_postgres_executable(create: exp.Create) -> str:
    schema = create.this
    if not isinstance(schema, exp.Schema):
        return create.sql(dialect="postgres") + ";\n"

    # Remove MySQL-only table properties (ENGINE/CHARSET/COLLATE...)
    create = create.copy()
    create.set("properties", None)

    schema = create.this
    assert isinstance(schema, exp.Schema)
    table_sql = schema.this.sql(dialect="postgres")

    # Extract inline indexes into standalone CREATE INDEX statements.
    # Keep PRIMARY KEY and UNIQUE KEY in the CREATE TABLE as constraints.
    extracted_indexes: List[exp.IndexColumnConstraint] = []
    retained: List[exp.Expression] = []
    for element in list(schema.expressions or []):
        if isinstance(element, exp.IndexColumnConstraint):
            extracted_indexes.append(element)
        else:
            retained.append(element)
    schema.set("expressions", retained)

    # Drop column-level COLLATE constraints (often MySQL-specific names).
    _strip_column_collations(schema)

    # Make MySQL column modifiers executable in PostgreSQL.
    on_update_todos = _strip_on_update_constraints(schema)
    _rewrite_auto_increment_to_identity(schema)
    _rewrite_unsigned_integer_types(schema)

    # Rewrite UNIQUE KEY into CONSTRAINT ... UNIQUE (...)
    _rewrite_unique_constraints(schema)

    statements: List[str] = []
    statements.append(create.sql(dialect="postgres").rstrip() + ";")
    statements.extend(on_update_todos)

    for index in extracted_indexes:
        idx_kind = index.args.get("kind")
        if idx_kind == "FULLTEXT":
            idx_name = getattr(index.this, "this", "")
            cols = list(index.args.get("expressions") or [])
            col_exprs: List[exp.Expression] = []
            for c in cols:
                if isinstance(c, exp.Ordered):
                    col_exprs.append(c.this)
                else:
                    col_exprs.append(c)

            idx_name_sql = exp.to_identifier(str(idx_name), quoted=True).sql(dialect="postgres")
            gin_expr = _fulltext_gin_expression(col_exprs)
            # Default to 'simple'. Users can adjust language based on needs.
            statements.append(
                f"CREATE INDEX {idx_name_sql} ON {table_sql} USING GIN (to_tsvector('simple', {gin_expr}));"
            )
            continue

        idx_name = getattr(index.this, "this", None) or index.this.sql(dialect="mysql")
        idx_name_sql = exp.to_identifier(str(idx_name), quoted=True).sql(dialect="postgres")

        cols = list(index.args.get("expressions") or [])
        cols_sql = ", ".join(_index_column_sql(c) for c in cols)

        using_clause = ""
        index_type = index.args.get("index_type")
        if isinstance(index_type, exp.Expression):
            index_type = index_type.sql(dialect="postgres")
        if isinstance(index_type, str) and index_type and index_type.upper() == "HASH":
            using_clause = " USING hash"

        # Some MySQL syntax like `USING HASH` is stored in options rather than index_type.
        for opt in list(index.args.get("options") or []):
            using = getattr(opt, "args", {}).get("using")
            if isinstance(using, str) and using.upper() == "HASH":
                using_clause = " USING hash"

        statements.append(f"CREATE INDEX {idx_name_sql} ON {table_sql}{using_clause} ({cols_sql});")

    return "\n".join(statements).rstrip() + "\n"


def convert_mysql_to_postgres(mysql_sql_text: str) -> List[ConversionResult]:
    """Convert MySQL SQL text (possibly multiple statements) into PostgreSQL.

    Returns a list of statement-level results.
    """
    mysql_sql_text = _preprocess_mysql_sql(mysql_sql_text)
    expressions = sqlglot.parse(mysql_sql_text, read="mysql")
    results: List[ConversionResult] = []

    for expression in expressions:
        try:
            # sqlglot may fall back to Command for unsupported syntax. Do not emit raw MySQL.
            if isinstance(expression, exp.Command):
                raw = expression.sql(dialect="mysql")
                results.append(
                    ConversionResult(
                        postgres_sql=_commented_sql_block(
                            "Unsupported MySQL-specific syntax; manual rewrite required", raw
                        )
                    )
                )
                continue

            if isinstance(expression, exp.Create) and expression.args.get("kind") == "TABLE":
                postgres_sql = _convert_create_table_to_postgres_executable(expression)
            elif isinstance(expression, exp.Delete) and expression.args.get("limit") is not None:
                # Rewrite DELETE ... LIMIT N into ctid-based delete, which is executable in PG.
                delete = expression
                table = delete.this.sql(dialect="postgres")
                where = delete.args.get("where")
                where_sql = (
                    where.this.sql(dialect="postgres")
                    if isinstance(where, exp.Where) and where.this is not None
                    else "TRUE"
                )
                limit = delete.args.get("limit")
                limit_sql = (
                    limit.expression.sql(dialect="postgres")
                    if isinstance(limit, exp.Limit) and limit.expression is not None
                    else "0"
                )
                order = delete.args.get("order")
                order_sql = order.sql(dialect="postgres") if order is not None else ""
                if order_sql:
                    order_sql = " " + order_sql
                postgres_sql = (
                    f"DELETE FROM {table} WHERE ctid IN ("
                    f"SELECT ctid FROM {table} WHERE {where_sql}{order_sql} LIMIT {limit_sql}"
                    f");\n"
                )
            elif isinstance(expression, exp.Update) and isinstance(expression.this, exp.Table):
                # Rewrite MySQL UPDATE ... JOIN ... SET ... to PostgreSQL UPDATE ... SET ... FROM ... WHERE ...
                update = expression.copy()
                target = update.this
                joins = list(getattr(target, "args", {}).get("joins") or [])
                if joins:
                    target_alias = None
                    alias = target.args.get("alias")
                    if alias is not None and getattr(alias, "this", None) is not None:
                        target_alias = alias.this.this

                    # Remove joins from target.
                    target.set("joins", None)

                    from_tables: List[str] = []
                    conditions: List[str] = []
                    for j in joins:
                        from_tables.append(j.this.sql(dialect="postgres"))
                        on = j.args.get("on")
                        if on is not None:
                            conditions.append(on.sql(dialect="postgres"))

                    # Include additional WHERE if present (rare for this MySQL form)
                    where = update.args.get("where")
                    if isinstance(where, exp.Where) and where.this is not None:
                        conditions.append(where.this.sql(dialect="postgres"))

                    # Strip target alias from SET columns (PG doesn't allow u.col in SET)
                    rewritten_sets: List[str] = []
                    for assignment in list(update.expressions or []):
                        a = assignment.copy()
                        if isinstance(a, exp.EQ) and isinstance(a.this, exp.Column):
                            if target_alias and a.this.table and a.this.table == target_alias:
                                a.this.set("table", None)
                        rewritten_sets.append(a.sql(dialect="postgres"))

                    from_sql = ", ".join(from_tables)
                    where_sql = " AND ".join(conditions) if conditions else "TRUE"
                    postgres_sql = (
                        f"UPDATE {target.sql(dialect='postgres')} SET {', '.join(rewritten_sets)} "
                        f"FROM {from_sql} WHERE {where_sql};\n"
                    )
                else:
                    postgres_sql = update.sql(dialect="postgres").rstrip() + ";\n"
            elif isinstance(expression, exp.Insert) and bool(expression.args.get("ignore")):
                # MySQL INSERT IGNORE ~= PostgreSQL ON CONFLICT DO NOTHING
                insert = expression.copy()
                insert.set("ignore", None)
                postgres_sql = insert.sql(dialect="postgres").rstrip()
                # Ensure it ends with ON CONFLICT DO NOTHING.
                if "ON CONFLICT" not in postgres_sql.upper():
                    postgres_sql = postgres_sql.rstrip(";") + " ON CONFLICT DO NOTHING"
                postgres_sql = postgres_sql.rstrip() + ";\n"
            else:
                # If sqlglot can transpile, use it.
                postgres_sql = expression.sql(dialect="postgres").rstrip() + ";\n"

                # Rewrite UNIX_TIMESTAMP() (MySQL) to EXTRACT(EPOCH FROM ...) (PostgreSQL)
                if "UNIX_TIMESTAMP" in expression.sql(dialect="mysql").upper():
                    def _unix_ts_rewrite(node: exp.Expression) -> exp.Expression:
                        if isinstance(node, exp.Anonymous) and node.name.upper() == "UNIX_TIMESTAMP":
                            args = list(node.expressions or [])
                            inner = args[0] if args else exp.CurrentTimestamp()
                            return exp.Cast(
                                this=exp.Extract(this="EPOCH", expression=inner),
                                to=exp.DataType.build("BIGINT"),
                            )
                        return node

                    rewritten = expression.copy().transform(_unix_ts_rewrite)
                    postgres_sql = rewritten.sql(dialect="postgres").rstrip() + ";\n"

                # Detect constructs that often require schema knowledge (REPLACE, ON DUPLICATE KEY UPDATE)
                upper_mysql = expression.sql(dialect="mysql").upper()
                if "ON DUPLICATE KEY" in upper_mysql or upper_mysql.startswith("REPLACE "):
                    postgres_sql = _commented_sql_block(
                        "Cannot reliably convert without knowing conflict target/constraints; consider ON CONFLICT",
                        expression.sql(dialect="mysql").rstrip(";") + ";",
                    )

            results.append(ConversionResult(postgres_sql=postgres_sql))
        except Exception as exc:  # noqa: BLE001 - surface error message to user
            results.append(
                ConversionResult(
                    postgres_sql=None,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )

    return results


def format_plain_sql_output(results: Iterable[ConversionResult]) -> str:
    """Format conversion results as plain PostgreSQL SQL statements.

    - Successful statements are emitted as SQL (each ends with ';').
    - Failed statements emit a comment with the error.
    """
    lines: List[str] = []
    for result in results:
        if result.postgres_sql is not None:
            lines.append(result.postgres_sql.rstrip())
        else:
            lines.append(f"-- ERROR: {result.error or 'Unknown error'}")
    return "\n\n".join(lines).rstrip() + "\n"


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mysql2pgsql",
        description="Convert MySQL SQL to PostgreSQL SQL using sqlglot.",
    )

    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--sql", help="A MySQL SQL string to convert.")
    source_group.add_argument(
        "--in-file",
        type=Path,
        help="Input file containing MySQL SQL (one or more statements).",
    )

    parser.add_argument(
        "--out-file",
        "--output-file",
        type=Path,
        help="Output file path. If omitted, prints to STDOUT.",
    )

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    if args.sql is not None:
        sql_text = args.sql
        if not sql_text.strip():
            sys.stderr.write("No SQL provided.\n")
            return 2

        results = convert_mysql_to_postgres(sql_text)
        output_text = format_plain_sql_output(results)
        if args.out_file is not None:
            args.out_file.write_text(output_text, encoding="utf-8")
        else:
            sys.stdout.write(output_text)
        return 0

    # File mode
    input_path: Path = args.in_file
    if not input_path.exists():
        sys.stderr.write(f"Input file not found: {input_path}\n")
        return 2

    # Use utf-8-sig to gracefully handle UTF-8 BOM (common in Windows/PowerShell outputs)
    mysql_text = input_path.read_text(encoding="utf-8-sig")
    results = convert_mysql_to_postgres(mysql_text)
    output_text = format_plain_sql_output(results)

    if args.out_file is not None:
        args.out_file.write_text(output_text, encoding="utf-8")
    else:
        sys.stdout.write(output_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



