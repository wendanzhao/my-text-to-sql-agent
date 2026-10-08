import time

from dotenv import load_dotenv
from contextlib import closing

load_dotenv()

import sqlite3

DB_PATH = "chinook.db"
QUERY_TIMEOUT_SECONDS = 5  # seconds
QUERY_TIMEOUT_MESSAGE = (f"Query timed out after {QUERY_TIMEOUT_SECONDS} seconds and was cancelled. " 
                        "Most likely cause: a join without a correct ON condition, which multiplies rows. " 
                        "Rewrite the query: give every joined table an explicit JOIN ... ON condition, "
                        "and apply WHERE filters as early as possible. " 
                        "Do not retry the same query.")
MAX_ROWS = 100
TRUNCATED_MESSAGE = (f"(The results have been truncated after {MAX_ROWS} rows, " 
                     "it is not the total number of rows, you can use COUNT or SUM to get the total.)")

PROBE_LIMIT = 50

def list_tables() -> str:
    return ", ".join(get_table_names())
      
def get_table_names() -> list[str]:
    with closing(get_conn()) as conn:
        rows = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                        ).fetchall()
        return [row[0] for row in rows]

def get_schema(table: str) -> str:
    table = validate_table(table)

    with closing(get_conn()) as conn:
        ddl = conn.execute(
                        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                        (table,)).fetchone()
        return ddl[0]

def run_sql(query: str) -> str:
    with closing(get_conn()) as conn:
        try:
            cur = conn.execute(query)
            columns = [des[0] for des in cur.description]
            rows = cur.fetchmany(MAX_ROWS + 1)
            truncated = len(rows) > MAX_ROWS
            last_line = f"({len(rows)} rows)"
            if truncated:
                rows = rows[:MAX_ROWS]
                last_line = TRUNCATED_MESSAGE   
            header = " | ".join(columns)
            body = [" | ".join([str(v) if v is not None else "NULL" for v in row]) for row in rows]
            lines = [header, *body, last_line]
            return "\n".join(lines)     
        except sqlite3.OperationalError as e:
            if str(e) == "interrupted":
                raise TimeoutError(QUERY_TIMEOUT_MESSAGE) from e
            raise 

def get_distinct_values(table: str, column: str) -> str:
    real_table = validate_table(table)

    with closing(get_conn()) as conn:
        rows = conn.execute(f"PRAGMA table_info(\"{real_table}\")").fetchall()
        column_names = {row[1].lower() : row[1] for row in rows}
        if column.lower() not in column_names:
            raise ValueError(f"Column '{column}' does not exist in table '{real_table}'. Available columns: {', '.join(column_names.values())}")

        real_column = column_names[column.lower()]
        distinct_values = conn.execute(
            f'SELECT DISTINCT "{real_column}" FROM "{real_table}" LIMIT {PROBE_LIMIT}'
        ).fetchall()
        total_count = conn.execute(
            f'SELECT COUNT(DISTINCT "{real_column}") FROM "{real_table}"'
        ).fetchone()[0]

        truncated = total_count > PROBE_LIMIT
        values_str = ", ".join(_format_value(row[0]) for row in distinct_values)
        if truncated:
            values_str += f" (showing {PROBE_LIMIT} of {total_count} distinct values)"
        return values_str

def _format_value(value) -> str:  
    if value is None:
        return "NULL"
    if isinstance(value, str):
        value = value.replace("'", "''")
        return f"'{value}'"
    return str(value)

# 不区分大小写，验证表名是否存在于数据库中，并返回真实的表名
def validate_table(table: str) -> str:
    table_names = get_table_names()
    tables = {t.lower() : t for t in table_names}
    if table.lower() not in tables:
        raise ValueError(f"Table '{table}' does not exist. Available tables: {', '.join(tables.values())}")
    return tables[table.lower()]
    

# 执行工具的函数，返回 (result, is_error)
def execute_tool(name: str, tool_input: dict) -> tuple[str, bool]:
    func = TOOL_FUNCS.get(name)
    if func is None:
        return f"Error: Tool '{name}' not found. Available tools: {', '.join(TOOL_FUNCS.keys())}", True
    try:
        result = func(**tool_input)
        return result, False
    except Exception as e:
        result = f"Error type: {type(e).__name__}, Error message: {e}"
        return result, True

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)

    start_time = time.perf_counter()

    def timeout_handler():
        elapsed = time.perf_counter() - start_time
        if elapsed > QUERY_TIMEOUT_SECONDS:
            return 1
        return 0


    conn.set_progress_handler(timeout_handler, 10000)
    return conn


# 给模型看的说明书（JSON schema), 告诉它有哪些工具、参数长什么样
BASE_TOOLS = [
    {
        "name": "get_schema",
        "description": "Return the CREATE TABLE statement for a given table.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table": {"type": "string", "description": "Table name"}
            },
            "required": ["table"],
        },
    },
    {
        "name": "list_tables",
        "description": "Return a comma-separated list of all tables in the database.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "run_sql",
        "description": "Execute a SQL query and return the result as a formatted string.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "SQL query to execute"}
            },
            "required": ["query"],
        }
    }
]

PROBE_TOOL= {
    "name": "get_distinct_values",
    "description": ("Return the distinct values actually stored in a column "
                    f"(up to {PROBE_LIMIT}, with the total count if truncated). "
                    "Call this before filtering with a string literal in a WHERE clause "
                    "when you are not sure of the exact spelling or casing used in the database "
                    "(e.g. 'USA' vs 'United States'). "
                    "A wrong value does not cause an error; it silently returns zero rows."),
    "input_schema": {
        "type": "object",
        "properties": {
            "table": {"type": "string", "description": "Table name"},
            "column": {"type": "string", "description": "Column name"}
        },
        "required": ["table", "column"],
    }
}

# 给代码看的查找表，工具名到函数的映射
TOOL_FUNCS = {
    "list_tables": list_tables,
    "get_schema": get_schema,
    "run_sql": run_sql,
    "get_distinct_values": get_distinct_values,
}


if __name__ == "__main__":
    print(_format_value("O'Brien"))   