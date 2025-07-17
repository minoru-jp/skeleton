
from typing import Any, Generic, Protocol, TypeVar
from skeleton import make_skeleton_handle

from skeleton.codegen.linearloop import LinearLoop
from skeleton.context import Context
from skeleton.skeleton import SkeletonHandle

code_template = LinearLoop()
code_template.param_name =  'test_code_generation'
code_template.param_use_pauser = False

def piyo(context: Context[str]):
    pass

async def puyo(context: Context[str]):
    pass

class Acc(Protocol):
    def sburoutine1(self, context: Context[str]) -> Any: ...
    def subroutine2(self, context: Context[str]) -> Any: ...

def circuit(context: Context[str]):
    subroutines = context.caller(Acc)
    

handle = make_skeleton_handle(str)

handle.append_subroutine(piyo)
handle.append_subroutine(puyo) 

print(handle.code_on_trial(code_template))

