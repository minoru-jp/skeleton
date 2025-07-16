"""
This module collects code snippets that may appear unrelated,
but all of them are intended to be used in the context of `skeleton.routine.RoutineTool`.
They illustrate the expected or recommended usage patterns when working with the RoutineTool.
"""

ARG = 'context'
TYPE = 'Context{type_}'
SIGNATURE = f"({ARG}{{arg_type}})"

ROUTINE_DEFINITIION = "async def {name}{signature}:"


FUNCS = f"caller"
RAW_FUNCS = f"function"

DEPLOY_FUNC = f"{{name}} = {FUNCS}.{{name}}"
DEPLOY_RAW_FUNC = f"{{name}} = {RAW_FUNCS}.{{name}}"



TRIAL_FUNCS = f"{ARG}.caller"
TRIAL_RAW_FUNCS = f"{ARG}.function"

DEPLOY_TRIAL_FUNC = f"{{name}} = {TRIAL_FUNCS}.{{name}}"
DEPLOY_TRIAL_RAW_FUNC = f"{{name}} = {TRIAL_RAW_FUNCS}.{{name}}"



CALL_SYNC = "{name}()"
CALL_ASYNC = "await {name}()"


SIGNAL = "signal"
BREAK = "Break"
CONTINUE = "Continue"
ALL_SIGNALS = (BREAK, CONTINUE)

DEPLOY_SIGNAL = f"{{signal}} = {ARG}.{SIGNAL}.{{signal}}"




PAUSE = "pauser"

DEPLOY_PAUSE = f"{PAUSE} = {ARG}.{PAUSE}"

CONSUME_PAUSE = "consume_on_pause_requested"
CONSUME_RESUME = "consume_resumed_flag"

PAUSER_IMPL = [
    f"{PAUSE}.{CONSUME_PAUSE}(s = {{super_}}, n = {{normal}})",
    f"{PAUSE}.{CONSUME_RESUME}(s = {{super_}}, n = {{normal}})",
    f"await {PAUSE}.wait_resume()",
]




