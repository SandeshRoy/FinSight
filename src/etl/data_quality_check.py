
from pathlib import Path
import duckdb
import csv

# Project paths
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data" / "bank_data.db"
OUTPUT_DIR = PROJECT_ROOT / "output"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def main():
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found: {DB_PATH}"
        )

    con = duckdb.connect(str(DB_PATH), read_only=True)

    try:
        tables = con.execute(
            "SHOW TABLES"
        ).fetchall()

        results = []

        print("\n========== FINSIGHT DATA QUALITY REPORT ==========\n")

        for (table_name,) in tables:
            # Table names come from the database metadata.
            quoted_table = '"' + table_name.replace('"', '""') + '"'

            row_count = con.execute(
                f"SELECT COUNT(*) FROM {quoted_table}"
            ).fetchone()[0]

            columns = con.execute(
                f"DESCRIBE SELECT * FROM {quoted_table}"
            ).fetchall()

            null_count = 0
            null_columns = []

            for column in columns:
                column_name = column[0]
                quoted_column = '"' + column_name.replace('"', '""') + '"'

                count = con.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM {quoted_table}
                    WHERE {quoted_column} IS NULL
                    """
                ).fetchone()[0]

                null_count += count

                if count > 0:
                    null_columns.append(
                        f"{column_name}: {count}"
                    )

            result = {
                "table": table_name,
                "row_count": row_count,
                "column_count": len(columns),
                "total_null_cells": null_count,
                "columns_with_nulls": "; ".join(null_columns),
            }

            results.append(result)

            print(f"Table: {table_name}")
            print(f"Rows: {row_count:,}")
            print(f"Columns: {len(columns)}")
            print(f"Null cells: {null_count:,}")

            if null_columns:
                print("Columns containing NULL values:")
                for item in null_columns:
                    print(f"  - {item}")
            else:
                print("No NULL values found.")

            print("-" * 55)

        report_path = OUTPUT_DIR / "data_quality_report.csv"

        with report_path.open(
            "w", newline="", encoding="utf-8"
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=[
                    "table",
                    "row_count",
                    "column_count",
                    "total_null_cells",
                    "columns_with_nulls",
                ],
            )
            writer.writeheader()
            writer.writerows(results)

        print("\nValidation summary")
        print(f"Tables inspected: {len(results)}")
        print(f"Report saved to: {report_path}")

    finally:
        con.close()


if __name__ == "__main__":
    main()
