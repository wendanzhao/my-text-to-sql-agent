import time

import anthropic
from tools import TOOLS, TOOL_FUNCS, execute_tool

MAX_TURNS = 5
MODEL = "claude-haiku-4-5-20251001"

MAX_RETRIES = 3
TIME_OUTS = 30  #seconds 后面需要进行测量调整！
client = anthropic.Anthropic(max_retries=MAX_RETRIES, timeout=TIME_OUTS)


SYSTEM_PROMPT = "You are a sqlite3 database analytical assistant. " \
                "Return the result of SQL query questions in plain english. " \
                "Start by exploring the database schema using tools provided, " \
                "and then create SQL query and execute it to get the results."

def ask(question: str) -> str:
    messages = [{"role": "user", "content": question}]

    in_tokens = out_tokens = turns = 0
    start_time = time.perf_counter()
    try:
        for turn in range(MAX_TURNS):
            turn_start_time = time.perf_counter()
            try:
                resp = client.messages.create(
                    model=MODEL,
                    max_tokens=1024,
                    system=SYSTEM_PROMPT,
                    tools=TOOLS,
                    messages=messages,
                )
                turn_end_time = time.perf_counter()
            except anthropic.APIError as e:
                print(f"[turn {turn}] Error type: {type(e).__name__}, Error message: {e}")
                return f"Failed to get a response due to an API error: Error type: {type(e).__name__}, Error message: {e}"

        
            messages.append({"role": "assistant", "content": resp.content})

            in_tokens += resp.usage.input_tokens
            out_tokens += resp.usage.output_tokens
            turns += 1

            print(f"[turn {turn}] stop_reason = {resp.stop_reason} | " 
                f"in={resp.usage.input_tokens} out={resp.usage.output_tokens} | " 
                f"used {turn_end_time - turn_start_time:.2f}s")

            if resp.stop_reason != "tool_use":
                for block in resp.content:
                    if block.type == "text":
                        return block.text
                return f"can't obtain a valid response. stop_reason = {resp.stop_reason}"


            tool_results = []
            for block in resp.content:
                if block.type == "tool_use":
                    result, is_error = execute_tool(block.name, block.input)
                    # 看看模型是怎么一步步探索数据库的
                    print(f"[turn {turn}] is_error = {is_error} | {block.name}({block.input}) -> {result[:300]}")

                    tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                            "is_error": is_error
                        }) 

            messages.append({"role": "user","content": tool_results})
        
        return "Can't finish after max turns"
    finally:
        print(f"[total] {turns} turns | in={in_tokens} out={out_tokens} | used {time.perf_counter() - start_time:.2f}s")




if __name__ == "__main__":
    print(ask("list all the songs' names?"))
    # print(execute_tool("get_schema", {"table": "NotATable"}))   # 表不存在
    # print(execute_tool("run_sql", {"query": "SELEC *"}))        # SQL 错误
    # print(execute_tool("no_such_tool", {}))                     # 工具不存在
    # print(execute_tool("list_tables", {}))                      # 正常情况
    # result, is_error = execute_tool("list_tables", {})
    # assert is_error is False, "正常调用不应该标记为出错"

    # result, is_error = execute_tool("run_sql", {"query": "SELEC *"})
    # assert is_error is True, "SQL 错误应该标记为出错"

    # result, is_error = execute_tool("get_schema", {"table": "NotATable"})
    # assert is_error is True, "表不存在应该标记为出错"

    # result, is_error = execute_tool("no_such_tool", {})
    # assert is_error is True, "工具不存在应该标记为出错"
    # print("all tests passed")

