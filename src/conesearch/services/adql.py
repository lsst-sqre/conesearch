"""ADQL query builder."""

from dataclasses import dataclass, field
from typing import Self


@dataclass(slots=True)
class ADQLQuery:
    """Builds an ADQL SELECT query.

    Columns and WHERE clauses are added as chained calls to
    `select` and `where`, then rendered to a query string with `render`.

    Parameters
    ----------
    table
        Fully qualified table name (e.g. ``dp1.Object``).
    select_columns
        Column expressions to include in the SELECT list.
    where_clauses
        Predicate strings joined with AND in the WHERE clause.
    """

    table: str
    select_columns: list[str] = field(default_factory=list)
    where_clauses: list[str] = field(default_factory=list)

    def select(self, *columns: str) -> Self:
        """Append columns to the SELECT list.

        Parameters
        ----------
        *columns
            One or more column expressions (bare names or ``*``).

        Returns
        -------
        Self
            The same instance, for method chaining.
        """
        self.select_columns.extend(columns)
        return self

    def where(self, *clauses: str | None) -> Self:
        """Append predicates to the WHERE clause.

        Parameters
        ----------
        *clauses
            Boolean SQL expressions. ``None`` or empty strings are
            silently ignored.

        Returns
        -------
        Self
            The same instance, for method chaining.
        """
        self.where_clauses.extend(c for c in clauses if c)
        return self

    def render(self) -> str:
        """Render the query to an ADQL string.

        Returns
        -------
        str
            A complete ADQL SELECT statement. Falls back to ``SELECT *``
            if no columns have been added.
        """
        select_sql = ", ".join(self.select_columns) or "*"

        lines = [
            f"SELECT {select_sql}",
            f"FROM {self.table}",
        ]

        if self.where_clauses:
            lines.append("WHERE")
            lines.append("  " + "\n  AND ".join(self.where_clauses))

        return "\n".join(lines)
