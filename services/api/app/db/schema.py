"""Render a review-only initial MariaDB DDL proposal; no apply/drop command is provided."""

from sqlalchemy.dialects.mysql.mariadb import MariaDBDialect
from sqlalchemy.schema import CreateTable

from app.db.models import Base


def initial_schema_sql() -> str:
    dialect = MariaDBDialect()
    definitions = []
    for table in Base.metadata.sorted_tables:
        compiled = str(CreateTable(table).compile(dialect=dialect)).strip()
        definitions.append("\n".join(line.rstrip() for line in compiled.splitlines()) + ";")
    return (
        "-- REVIEW ONLY: no production connection or grants. Not applied.\n\n"
        + "\n\n".join(definitions)
        + "\n"
    )
