
import duckdb

source_db = "data/bank_data.db"
output_csv = "output/transaction_fact.csv"

con = duckdb.connect(source_db, read_only=True)

con.execute(
    f"""
    COPY (
        SELECT *
        FROM transaction_fact
    )
    TO '{output_csv}'
    (HEADER, DELIMITER ',')
    """
)

con.close()

print(f"Export completed: {output_csv}")
