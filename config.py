from dataclasses import dataclass

@dataclass(frozen=True)
class AgentConfig:
    enable_self_correction: bool = True
    enable_value_probe: bool = True
    max_sql_retries: int = 2
    max_turns: int = 8