
from __future__ import annotations

from typing import Mapping, Optional

from ..subroutine import Subroutine, SecureNameMapper

from . import util as _util
from . import snippet as _snip
from . import protocol as _prot
from . import block as _block

class LinearLoop(_prot.CodeTemplate):
    __slots__ = (
        'param_name', 'param_use_pauser',
        'param_super_pause', 'param_pause',
        'param_super_resume', 'param_resume')

    def __init__(self):
        self.param_name: str = "liner_loop"
        self.param_use_pauser: bool = True
        
        self.param_super_pause: Optional[str] = None
        self.param_pause: Optional[str] = None
        self.param_super_resume: Optional[str] = None
        self.param_resume: Optional[str] = None

    def _internal_generate_routine_code(
            self,
            func: _block.Block,
            subs: _prot.Mapping[str, Subroutine],
            spa: str,
            pa: str,
            sra: str,
            ra: str,
        ) -> _block.Block:

        use_pauser = self.param_use_pauser

        if self.param_use_pauser:
            func.add(_util.deploy_pause())
        func.add(_util.deploy_signal(_snip.BREAK))

        try_ = func.add_block(_block.Block("try:"))
        while_ = try_.add_block(_block.Block("while True:"))
        do = while_
        if use_pauser:
            while_.add(f"await pauser.consume_on_pause_requested(s = {spa}, n = {pa})")
            while_.blank()
            if_ = while_.add_block(_block.Block("if pauser.current_mode is pauser.RUNNING:"))
            do = if_
        for name, sub in subs.items():
            do.add(_util.get_call(name, sub))
        do.blank()
        if use_pauser:
            while_.add(f"await pauser.consume_resumed_flag(s = {sra}, n = {ra})")
            while_.blank()
            if_ = while_.add_block(_block.Block("if pauser.current_mode is not pauser.RUNNING:"))
            if_.add("await pauser.wait_resume()")
        
        try_.set_tail("except Break:")

        # if self.param_use_pauser:
        #     while_.add(_util.get_pauer_impl(spa, pa, sra, ra))

        #func.render(buffer)

        return func
    
    def generate_routine_code(self, type_: type, subs: Mapping[str, Subroutine]) -> str:
        buffer = []
        _prot.render_accessor_protocols(buffer, subs)
        routine = _block.Block(_util.get_routine_func_definition(type_, self.param_name))
        _prot.add_accessor_cast_process(routine)
        routine.add(_util.deploy_subroutines(subs, trial = False))
        self._internal_generate_routine_code(
            routine,
            subs,
            spa = str(self.param_super_pause),
            pa = str(self.param_pause),
            sra = str(self.param_super_resume),
            ra = str(self.param_resume)
        )
        return "\n".join(routine.render(buffer))
    
    def generate_trial_routine_code(self, name: str, subs: Mapping[str, Subroutine], mapper: SecureNameMapper) -> str:
        buffer = []
        routine = _block.Block(_util.get_routine_func_definition(None, name))
        routine.add(_util.deploy_subroutines(subs, trial = True))
        self._internal_generate_routine_code(
            routine,
            subs,
            spa = str(mapper(self.param_super_pause)),
            pa = str(mapper(self.param_pause)),
            sra = str(mapper(self.param_super_resume)),
            ra = str(mapper(self.param_resume))
        )
        return "\n".join(routine.render(buffer))