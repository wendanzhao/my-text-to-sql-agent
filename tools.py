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



def list_tables() -> str:
    with closing(get_conn()) as conn:
        rows = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                        ).fetchall()
        return ", ".join([row[0] for row in rows])


def get_schema(table: str) -> str:
    ddl = None
    with closing(get_conn()) as conn:
        ddl = conn.execute(
                        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                        (table,)).fetchone()
    if ddl is None:
        raise ValueError(f"Table '{table}' does not exist. Available tables: {list_tables()}")
    
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
TOOLS = [
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

# 给代码看的查找表，工具名到函数的映射
TOOL_FUNCS = {
    "list_tables": list_tables,
    "get_schema": get_schema,
    "run_sql": run_sql,
}


if __name__ == "__main__":
    # tests = [
    #     "SELECT * FROM Artist LIMIT 3",
    #     "SELEC * FROM Artist",
    #     "DELETE FROM Artist WHERE ArtistId = 1",
    #     "SELECT COUNT(*) FROM Track a, Track b, Track c",
    # ]
    # for q in tests:
    #     result, is_error = execute_tool("run_sql", {"query": q})
    #     print(f"is_error={is_error} | {q}\n  -> {result[:200]}\n")
    result = run_sql("SELECT * FROM Track")
    print(len(result))        # 应该从 299889 降到一万左右
    print(result[-150:])      # 最后一行应该是截断提示，中间没有一长串空格

    print(run_sql("SELECT * FROM Artist LIMIT 5"))  # 最后一行还是 (5 rows)
