from dotenv import load_dotenv

load_dotenv()

import sqlite3

DB_PATH = "chinook.db"

def list_tables() -> str:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
    conn.close()
    return ", ".join([row[0] for row in rows])


def get_schema(table: str) -> str:
    conn = sqlite3.connect(DB_PATH)

    ddl = conn.execute(
                      "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                      (table,)).fetchone()[0]
    
    conn.close()
    return ddl

def run_sql(query: str) -> str:
    # try:
    #     ...
    # except Exception as e:
    #     return f"Error: {e}"
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(query)
    columns = [des[0] for des in cur.description]
    
    rows = cur.fetchall()
    header = " | ".join(columns)
    body = [" | ".join([str(v) if v is not None else "NULL" for v in row]) for row in rows]
    lines = [header, *body, f"({len(rows)} rows)"]
  
    conn.close()
    return "\n".join(lines)

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
    print(list_tables())
    print(get_schema("Album"))
    print(run_sql("SELECT * FROM Artist LIMIT 3"))
    print(run_sql("SELECT * FROM Artist WHERE Name = 'Nobody'"))
    print(run_sql("SELECT TrackId, Composer FROM Track WHERE Composer IS NULL LIMIT 3"))