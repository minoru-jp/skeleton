
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
    def action1(self, context: Context[str]) -> Any: ...
    def action2(self, context: Context[str]) -> Any: ...

def circuit(context: Context[str]):
    actions = context.caller(Acc)
    

handle = make_skeleton_handle(str)

handle.append_action(piyo)
handle.append_action(puyo) # wrong type action

print(handle.code_on_trial(code_template)) # generates routine code for static definition with copy&paste

# print(handle.code_on_trial(code_template))

# handle.trial(code_template) # excutes generated routine by CodeTemplate


