from dataclasses import dataclass
import time
import anthropic
from config import AgentConfig
from tools import BASE_TOOLS, PROBE_TOOL, TOOL_FUNCS, execute_tool
from enum import StrEnum

import logging
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",)
logging.getLogger("httpx2").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


MODEL = "claude-haiku-4-5-20251001"

API_MAX_RETRIES = 3
TIME_OUTS = 30  #seconds 后面需要进行测量调整！
client = anthropic.Anthropic(max_retries=API_MAX_RETRIES, timeout=TIME_OUTS)


SYSTEM_PROMPT = "You are a sqlite3 database analytical assistant. " \
                "Return the result of SQL query questions in plain english. " \
                "Start by exploring the database schema using tools provided, " \
                "and then create SQL query and execute it to get the results."

class Status(StrEnum):
    OK = "ok"
    API_ERROR = "api_error"
    UNEXPECTED_STOP = "unexpected_stop"
    EMPTY_RESPONSE = "empty_response"
    MAX_TOKENS_REACHED = "max_tokens_reached"
    SELF_CORRECTION_OFF = "self_correction_off"
    RETRIES_EXHAUSTED = "retries_exhausted"
    MAX_TURNS_REACHED = "max_turns_reached"

@dataclass
class AgentResult:
    answer: str         # 给用户看的
    status: Status      # 给程序看的：
    sql_error_count: int  # 给开发者看的


def ask(question: str, config: AgentConfig | None = None) -> AgentResult:
    config = config or AgentConfig()
    logger.info(f"{config}")

    messages = [{"role": "user", "content": question}]

    in_tokens = out_tokens = turns = 0
    start_time = time.perf_counter()
    tools = BASE_TOOLS + ([PROBE_TOOL] if config.enable_value_probe else [])   

    sql_error_count = 0

    try:
        for turn in range(config.max_turns):
            turn_start_time = time.perf_counter()
            try:
                resp = client.messages.create(
                    model=MODEL,
                    max_tokens=1024,
                    system=SYSTEM_PROMPT,
                    tools=tools,
                    messages=messages,
                )
                turn_end_time = time.perf_counter()
            except anthropic.APIError as e:
                logger.error(f"[turn {turn}] Error type: {type(e).__name__}, Error message: {e}")
                return AgentResult(
                            answer=f"Failed to get a response due to an API error",
                            status=Status.API_ERROR,
                            sql_error_count=sql_error_count,
                        )

        
            messages.append({"role": "assistant", "content": resp.content})

            in_tokens += resp.usage.input_tokens
            out_tokens += resp.usage.output_tokens
            turns += 1

            print(f"[turn {turn}] stop_reason = {resp.stop_reason} | " 
                f"in={resp.usage.input_tokens} out={resp.usage.output_tokens} | " 
                f"used {turn_end_time - turn_start_time:.2f}s")

            if resp.stop_reason == "end_turn":
                for block in resp.content:
                    if block.type == "text":
                        return AgentResult(
                            answer=block.text,
                            status=Status.OK,
                            sql_error_count=sql_error_count,
                        )
                logger.warning(
    f"end_turn without text block, content types: {[b.type for b in resp.content]}"
)
                return AgentResult(
                            answer="Sorry, no answer was returned, Please try again.",
                            status=Status.EMPTY_RESPONSE,
                            sql_error_count=sql_error_count,
                        )
            elif resp.stop_reason == "max_tokens":
                return AgentResult(
                    answer="Failed to get a response due to max tokens reached.",
                    status=Status.MAX_TOKENS_REACHED,
                    sql_error_count=sql_error_count,
                )
            elif resp.stop_reason != "tool_use":
                logger.warning(f"Unexpected stop_reason: {resp.stop_reason}")
                return AgentResult(
                            answer=f"Unexpected stop_reason",
                            status=Status.UNEXPECTED_STOP,
                            sql_error_count=sql_error_count,
                        )

            tool_results = []
            for block in resp.content:
                if block.type == "tool_use":
                    result, is_error = execute_tool(block.name, block.input)
                    # 看看模型是怎么一步步探索数据库的
                    print(f"[turn {turn}] is_error = {is_error} | {block.name}({block.input}) -> {result[:300]}")

                    if block.name == "run_sql" and is_error:
                        sql_error_count += 1
                        logger.warning(f"SQL error #{sql_error_count}: {result}")

                        if not config.enable_self_correction:
                            # 关： 第一次出错就停，模型没有机会改
                            return AgentResult(
                                answer="Sorry, Can't answer due to SQL error.",
                                status=Status.SELF_CORRECTION_OFF,
                                sql_error_count=sql_error_count,
                            )
                        if sql_error_count > config.max_sql_retries:
                            # 开，但重试次数用完了
                            return AgentResult(
                                answer="Sorry, Can't answer due to SQL errors and max retries reached.",
                                status=Status.RETRIES_EXHAUSTED,
                                sql_error_count=sql_error_count,
                            )
                        

                    tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                            "is_error": is_error
                        }) 

            messages.append({"role": "user","content": tool_results})
        
        return AgentResult(
            answer="Sorry, Can't finish query after max turns.",
            status=Status.MAX_TURNS_REACHED,
            sql_error_count=sql_error_count,
        )
    finally:
        print(f"[total] {turns} turns | in={in_tokens} out={out_tokens} | used {time.perf_counter() - start_time:.2f}s")



from dataclasses import replace

if __name__ == "__main__":  
    question = "How many hip hop tracks are there?"
    base = AgentConfig()
    configs = {
        "probe_on": base,
        "probe_off": replace(base, enable_value_probe=False),
    }
    for name, cfg in configs.items():
        for i in range(3):
            r = ask(question, cfg)
            print(f"### {name} run{i}: status={r.status} errors={r.sql_error_count}")