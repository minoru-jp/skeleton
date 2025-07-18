
import inspect
from typing import Callable, Mapping, MutableSequence, Optional, Protocol, runtime_checkable

from .. import subroutine as _act

from . import block as _block

@runtime_checkable
class CodeTemplate(Protocol):
    def generate_routine_code(self, type_: type, subs: Mapping[str, _act.Subroutine]) -> str:
        ...
    
    def generate_trial_routine_code(self, name: str, subs: Mapping[str, _act.Subroutine], mapper: _act.SecureNameMapper) -> str:
        ...

CALLER = "CallerProtocol"

FUNCTION = "FunctionProtocol"

def render_accessor_protocols(buffer: MutableSequence[str], subs: Mapping[str, _act.Subroutine]) ->  MutableSequence[str]:
    acc = _block.Block([
        "@runetime_checkable",
        f"class {CALLER}(Protocol):"
    ])
    raw = _block.Block([
        "@runtime_checkable",
        f"class {FUNCTION}(Protocol):"
    ])
    for name, sub in subs.items():
        async_ = inspect.iscoroutinefunction(sub)
        template = f"{"async " if async_ else ""}def {name}{{sig}} -> Any: ..."
        
        acc.add("@staticmethod")
        acc.add(template.format(sig = "()"))
        raw.add("@staticmethod")
        raw.add(template.format(sig = "(context: Context)"))
    
    acc.render(buffer)
    buffer.append("")
    raw.render(buffer)
    buffer.append("")
    buffer.append("")
    
    return buffer

def add_accessor_cast_process(parent_block: _block.Block):
    parent_block.add(f"caller = context.caller({CALLER})")
    parent_block.add(f"function = context.function({FUNCTION})")
    parent_block.add_blank()


