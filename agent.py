import anthropic
from tools import TOOLS, TOOL_FUNCS

client = anthropic.Anthropic()
MAX_TURNS = 5
MODEL = "claude-haiku-4-5-20251001"


SYSTEM_PROMPT = "You are a sqlite3 database analytical assistant. " \
                "Return the result of SQL query questions in plain english. " \
                "Start by exploring the database schema using tools provided, and then create SQL query and execute it to get the results."

def ask(question: str) -> str:
    messages = [{"role": "user", "content": question}]

    for turn in range(MAX_TURNS):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason != "tool_use":
            for block in resp.content:
                if block.type == "text":
                    return block.text

        tool_results = []
        for block in resp.content:
            if block.type == "tool_use":
                func = TOOL_FUNCS.get(block.name)
                result = func(**block.input)
                # 看看模型是怎么一步步探索数据库的
                print(f"[turn {turn}] {block.name}({block.input}) -> {result[:300]}")

                tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    }) 

        messages.append({"role": "user","content": tool_results})
        
    return "Can't finish after max turns"

if __name__ == "__main__":
    print(ask("who has the most albums?"))