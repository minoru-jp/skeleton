
import inspect
from typing import Callable, Mapping, Optional

from .. import subroutine as _act

from . import snippet as _snip

def indent(depth: int = 1) -> str:
    return ' ' * depth

def get_routine_func_definition(type_: Optional[type], name: str):
    type_str = f" :{_snip.TYPE.format(type_ = f"[{type_.__name__}]")}" if type_ else ""
    return _snip.ROUTINE_DEFINITIION.format(
        name = name,
        signature = _snip.SIGNATURE.format(arg_type = type_str)
    )

def deploy_subroutines(actions: Mapping[str, _act.Subroutine], trial: bool) -> list[str]:
    deploy_buffer = []
    template = _snip.DEPLOY_FUNC if not trial else _snip.DEPLOY_TRIAL_FUNC
    for name in actions.keys():
        deploy_buffer.append(template.format(name = name))
    
    return deploy_buffer

def deploy_pause() -> str:
    return _snip.DEPLOY_PAUSE

def deploy_signal(signal: str) -> str:
    if signal not in _snip.ALL_SIGNALS:
        raise ValueError(f"No such signal '{signal}'")
    return _snip.DEPLOY_SIGNAL.format(signal = signal)

def deploy_all_signals() -> list[str]:
    deploy_buffer = []
    for signal in _snip.ALL_SIGNALS:
        deploy_buffer.append(deploy_signal(signal))
    return deploy_buffer

def get_call(name: str, fn: Callable) -> str:
    call = _snip.CALL_ASYNC if inspect.iscoroutinefunction(fn) else _snip.CALL_SYNC
    return call.format(name = name)

def get_pauer_impl(
        super_pause: str, normal_pause: str,
        super_resume: str, normal_resume: str
    ) -> list[str]:
    buffer = []
    buffer.append(_snip.PAUSER_IMPL[0].format(super_ = super_pause, normal = normal_pause))
    buffer.append(_snip.PAUSER_IMPL[1].format(super_ = super_resume, normal = normal_resume))
    return buffer

