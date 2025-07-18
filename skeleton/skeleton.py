
from __future__ import annotations

import asyncio
import inspect
import logging
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Generic, Optional, Protocol, Type, runtime_checkable

from . import state as mod_state
from . import log as mod_log
from . import event as mod_event
from . import context as mod_context
from . import subroutine as mod_sub
from . import control as mod_control
from . import codegen as mod_codegen
from . import message as mod_report
from . import result as mod_result
from . import record as mod_record
from . import engine as mod_engine
from . import routine as mod_routine

if TYPE_CHECKING:
    from .state import UsageStateFull
    from .log import LogFull, Log
    from .event import EventFull, EventHandler
    from .context import ContextFull
    from .subroutine import Subroutine, SubroutineFull
    from .control import ControlFull
    from .message import MessageFull, Message, Messenger
    from .routine import Routine
    from .result import ResultFull, ResultReader, ResultHandler
    from .record import ProcessRecordFull
    from .codegen import CodeTemplate
    from .engine import ExceptionMarker


@runtime_checkable
class SkeletonBaseHandle(Protocol, Generic[mod_context.T]): # type: ignore
    @property
    def log(_) -> Log:
        ...
    
    @staticmethod
    def set_role(role: str) -> None:
        ...
    
    @staticmethod
    def set_logger(logger: logging.Logger) -> None:
        ...
    
    @staticmethod
    def set_field(field: mod_context.T) -> None:
        ...
    
    @staticmethod
    def set_on_start(handler: EventHandler) -> None:
        ...
    @staticmethod
    def set_on_redo(handler: EventHandler) -> None:
        ...
    @staticmethod
    def set_on_end(handler: EventHandler) -> None:
        ...
    @staticmethod
    def set_on_cancel(handler: EventHandler) -> None:
        ...
    @staticmethod
    def set_on_close(handler: EventHandler) -> None:
        ...
    
    @property
    def request(_) -> mod_control.ControlRequest:
        ...
    
    @property
    def environment(_) -> Messenger:
        ...
    
    @staticmethod
    def append_subroutine(fn: Subroutine[mod_context.T], name: Optional[str] = None) -> None:
        ...
    
    @property
    def state_observer(_) -> mod_state.UsageStateObserver:
        ...

    @property
    def running_observer(_) -> mod_control.RunningObserver:
        ...

    @staticmethod
    def code(ct: CodeTemplate) -> str:
        ...

    @staticmethod
    def code_on_trial(ct: CodeTemplate) -> str:
        ...

@runtime_checkable
class _InnerSkeletonHandle(Protocol, Generic[mod_context.T], SkeletonBaseHandle): # type: ignore
    @staticmethod
    def set_routine(routine: Routine[mod_context.T]) -> None:
        ...

    @staticmethod
    def set_field_type(field_type: Type[mod_context.T]) -> None:
        ...

    @staticmethod
    def start() -> asyncio.Task:
        ...
    
    @staticmethod
    def trial(ct: mod_codegen.CodeTemplate) -> asyncio.Task:
        ...


@runtime_checkable
class SkeletonHandle(Protocol, Generic[mod_context.T], SkeletonBaseHandle): # type: ignore
    @staticmethod
    def start():
        ...

@runtime_checkable
class TrialSkeletonHandle(Protocol, Generic[mod_context.T]): # type: ignore
    @staticmethod
    def trial(ct: CodeTemplate):
        ...


def _make_inner_skeleton_handle(type_hint: Routine[mod_context.T] | Type[mod_context.T]) -> _InnerSkeletonHandle[mod_context.T]:

    async def _engine(
            state: UsageStateFull,
            log_full: LogFull,
            exception_marker: ExceptionMarker,
            event_full: EventFull,
            routine: Routine,
            context_full: ContextFull,
            pauser_full: ControlFull,
            ev_proc_record: ProcessRecordFull,
            sub_proc_record: ProcessRecordFull,
            result_full: ResultFull,
            ) -> None:
        try:
            async_routine = inspect.iscoroutinefunction(routine)

            if async_routine:
                event_processor = event_full.setup_event_processor()
            else:
                event_processor = event_full.setup_event_processor(dedicated = ('on_redo', 'on_end'))
                for p in (event_processor.on_redo, event_processor.on_end):
                    if inspect.iscoroutinefunction(p):
                        # on_redo and on_end async handlers are supposed to be rejected before the engine starts.
                        raise RuntimeError("An unexpected asynchronous handler was found.")
                    
            log = log_full.get_reader()
            
            log.logger.debug(f"[{log.role}] engine start")
            await event_processor.on_start()
            
            context = context_full.setup_context()
            context_full.load_context_caller_accessors()

            if async_routine:
                await mod_engine.boot_async_routine(
                    routine,
                    exception_marker,
                    log,
                    context,
                    result_full,
                    pauser_full,
                    event_processor.on_redo,
                    event_processor.on_end
                )
            else:
                mod_engine.boot_sync_routine_with_thread(
                    routine,
                    exception_marker,
                    log,
                    context,
                    result_full,
                    event_processor.on_redo,
                    event_processor.on_end
                )
            result_full.set_event_process_record(ev_proc_record.get_reader())
            result_full.set_routine_process_record(sub_proc_record.get_reader())
            
            await event_processor.on_close()

        except Exception as e:
            log.logger.critical(f"[{log.role}] Internal error: {e.__class__.__name__}")
            result_full.set_error(e)
        finally:
            # TODO:cleanup
            try:
                state.transit_state(state.TERMINATED)
            except state.InvalidStateError as e:
                if state.current_state is not state.TERMINATED:
                    raise
            try:
                rethrow = result_full.call_result_handler()
            except Exception as e:
                raise exception_marker.ResultHandlerError('result handler', e)
            error = result_full.get_reader().error
            if error and rethrow:
                raise error


    
    def _start_engine(routine) -> asyncio.Task:

        if not isinstance(routine, Routine):
            raise RuntimeError("Routine is missing")
        
        task = asyncio.create_task(
            _engine(
                _state_full,
                _log_full,
                _exception_marker,
                _event_full,
                routine,
                _context_full,
                _control_full,
                _ev_proc_record_full,
                _sub_proc_record_full,
                _result_full,
            )
        )
        
        return task

    _routine = None
    _field_type = None

    _state_full = mod_state.setup_UsageStateFull()
    _log_full = mod_log.setup_LogFull()
    _exception_marker = mod_engine.create_ExceptionMarker()
    _control_full = mod_control.setup_ControlFull()
    _subroutine_full = mod_sub.setup_SubroutineFull()
    _ev_proc_record_full = mod_record.setup_ProcessRecordFull()
    _sub_proc_record_full = mod_record.setup_ProcessRecordFull()
    _message_full = mod_report.setup_MessageFull(_log_full.get_reader())
    _result_full = mod_result.setup_ResultFull(_log_full.get_reader())
    _event_full = mod_event.setup_EventHandlerFull(_message_full, _ev_proc_record_full)
    
    _context_full = mod_context.setup_ContextFull(
        _log_full.get_reader(),
        _subroutine_full,
        _control_full.get_pauser(),
        _sub_proc_record_full,
        _message_full.get_environment().mapping,
        _message_full.get_event_messenger().mapping,
        _message_full.get_routine_messenger(),
    )

    class _Interface(_InnerSkeletonHandle):
        __slots__ = ()

        @property
        def log(_) -> Log:
            return _log_full.get_reader()
        
        @staticmethod
        def set_role(role: str) -> None:
            _state_full.maintain_state(
                _state_full.LOAD,
                _log_full.set_role,
                role
            )
        
        @staticmethod
        def set_logger(logger: logging.Logger) -> None:
            _state_full.maintain_state(
                _state_full.LOAD,
                _log_full.set_logger,
                logger
            )
        
        @staticmethod
        def set_field(field: mod_context.T) -> None:
            _state_full.maintain_state(
                _state_full.LOAD,
                _context_full.set_field,
                field
            )
        
        @staticmethod
        def set_on_start(handler: EventHandler) -> None:
            _state_full.maintain_state(
                _state_full.LOAD,
                _event_full.set_event_handler, 'on_start', handler)
        @staticmethod
        def set_on_redo(handler: EventHandler) -> None:
            # TODO:もしroutineが同期関数なら、ここに非同期関数が入った場合、例外
            _state_full.maintain_state(
                _state_full.LOAD,
                _event_full.set_event_handler, 'on_continue', handler)
        @staticmethod
        def set_on_end(handler: EventHandler) -> None:
            # TODO:もしroutineが同期関数なら、ここに非同期関数が入った場合、例外
            _state_full.maintain_state(
                _state_full.LOAD,
                _event_full.set_event_handler, 'on_end', handler)
        @staticmethod
        def set_on_cancel(handler: EventHandler) -> None:
            _state_full.maintain_state(
                _state_full.LOAD,
                _event_full.set_event_handler, 'on_cancel', handler)
        @staticmethod
        def set_on_close(handler: EventHandler) -> None:
            _state_full.maintain_state(
                _state_full.LOAD,
                _event_full.set_event_handler, 'on_close', handler)
        
        @staticmethod
        def start() -> asyncio.Task:
            _state_full.transit_state(_state_full.ACTIVE)
            if not isinstance(_routine, Routine):
                raise RuntimeError("Routine is missing")
            return _start_engine(_routine)
        
        @property
        def request(_) -> mod_control.ControlRequest:
            return _control_full.get_control_request()
        
        @property
        def environment(_) -> Messenger:
            return _message_full.get_environment()
        
        @staticmethod
        def append_subroutine(fn: Subroutine[mod_context.T], name: Optional[str] = None) -> None:
            _state_full.maintain_state(
                _state_full.LOAD,
                _subroutine_full.append_subroutine, fn, name)
        
        @property
        def state_observer(_) -> mod_state.UsageStateObserver:
            return _state_full.get_observer()
        
        @property
        def running_observer(_) -> mod_control.RunningObserver:
            return _control_full.get_observer()

        @staticmethod
        def code(ct: mod_codegen.CodeTemplate):
            if _field_type is None:
                raise RuntimeError("Not in code generation mode.")
            return ct.generate_routine_code(_field_type, _subroutine_full.get_subroutines())
        
        @staticmethod
        def code_on_trial(ct: mod_codegen.CodeTemplate):
            _subroutine_full.remap_to_secure_subroutine_name()
            code = ct.generate_trial_routine_code(
                "trial_routine",
                _subroutine_full.get_subroutines(),
                _subroutine_full.translate_raw_to_secure_name
            )
            _subroutine_full.remap_to_raw_subroutine_name()
            return code
        
        @staticmethod
        def trial(ct: mod_codegen.CodeTemplate):
            ROUTINE_NAME = "trial_routine"
            _state_full.transit_state(_state_full.ACTIVE)
            _subroutine_full.remap_to_secure_subroutine_name()
            code = ct.generate_trial_routine_code(
                ROUTINE_NAME,
                _subroutine_full.get_subroutines(),
                _subroutine_full.translate_raw_to_secure_name
            )
            dst = {}
            exec(code, {}, dst)
            trial_routine = dst[ROUTINE_NAME]
            # TODO:もしtrial_routineが同期関数なら、on_redoとon_endをチェック
            #これらが非同期関数なら例外
            return _start_engine(trial_routine)
        
        @staticmethod
        def set_routine(routine: Routine[mod_context.T]) -> None:
            def setter():
                nonlocal _routine
                _routine = routine
            _state_full.maintain_state(
                _state_full.LOAD,
                _event_full.set_event_handler, setter)
        
        @staticmethod
        def set_field_type(field_type: Type[mod_context.T]):
            def setter():
                nonlocal _field_type
            _state_full.maintain_state(
                _state_full.LOAD,
                _event_full.set_event_handler, setter)

    return _Interface()


def make_skeleton_handle(routine: Routine[mod_context.T]) -> SkeletonHandle:

    base_handle = _make_inner_skeleton_handle(routine)

    base_handle.set_routine(routine)

    class _Interface(SkeletonHandle):
        __slots__ = ()
        
        @property
        def log(_) -> Log:
            return base_handle.log
        
        @staticmethod
        def set_role(role: str) -> None:
            base_handle.set_role(role)
        
        @staticmethod
        def set_logger(logger: logging.Logger) -> None:
            base_handle.set_logger(logger)

        @staticmethod
        def set_field(field: mod_context.T) -> None:
            base_handle.set_field(field)
        
        @staticmethod
        def set_on_start(handler: EventHandler) -> None:
            base_handle.set_on_start(handler)
            
        @staticmethod
        def set_on_redo(handler: EventHandler) -> None:
            base_handle.set_on_redo(handler)

        @staticmethod
        def set_on_end(handler: EventHandler) -> None:
            base_handle.set_on_end(handler)

        @staticmethod
        def set_on_cancel(handler: EventHandler) -> None:
            base_handle.set_on_cancel(handler)

        @staticmethod
        def set_on_close(handler: EventHandler) -> None:
            base_handle.set_on_cancel(handler)
        
        @staticmethod
        def start():
            return base_handle.start()
        
        @property
        def request(_) -> mod_control.ControlRequest:
            return base_handle.request
        
        @property
        def environment(_) -> Messenger:
            return base_handle.environment
        
        @staticmethod
        def append_subroutine(fn: Subroutine[mod_context.T], name: Optional[str] = None) -> None:
            return base_handle.append_subroutine(fn, name)
        
        @property
        def state_observer(_) -> mod_state.UsageStateObserver:
            return base_handle.state_observer
        
        @property
        def running_observer(_) -> mod_control.RunningObserver:
            return base_handle.running_observer

        @staticmethod
        def code(ct: mod_codegen.CodeTemplate):
            return base_handle.code(ct)
        
        @staticmethod
        def code_on_trial(ct: mod_codegen.CodeTemplate):
            return base_handle.code_on_trial(ct)
        

    return _Interface()



def make_trial_skeleton_handle(field_type: Type[mod_context.T]) -> TrialSkeletonHandle:

    base_handle = _make_inner_skeleton_handle(field_type)

    base_handle.set_field_type(field_type)

    class _Interface(TrialSkeletonHandle):
        __slots__ = ()
        
        @property
        def log(_) -> Log:
            return base_handle.log
        
        @staticmethod
        def set_role(role: str) -> None:
            base_handle.set_role(role)
        
        @staticmethod
        def set_logger(logger: logging.Logger) -> None:
            base_handle.set_logger(logger)

        @staticmethod
        def set_field(field: mod_context.T) -> None:
            base_handle.set_field(field)
        
        @staticmethod
        def set_on_start(handler: EventHandler) -> None:
            base_handle.set_on_start(handler)
            
        @staticmethod
        def set_on_redo(handler: EventHandler) -> None:
            base_handle.set_on_redo(handler)

        @staticmethod
        def set_on_end(handler: EventHandler) -> None:
            base_handle.set_on_end(handler)

        @staticmethod
        def set_on_cancel(handler: EventHandler) -> None:
            base_handle.set_on_cancel(handler)

        @staticmethod
        def set_on_close(handler: EventHandler) -> None:
            base_handle.set_on_cancel(handler)
        
        @property
        def request(_) -> mod_control.ControlRequest:
            return base_handle.request
        
        @property
        def environment(_) -> Messenger:
            return base_handle.environment
        
        @staticmethod
        def append_subroutine(fn: Subroutine[mod_context.T], name: Optional[str] = None) -> None:
            return base_handle.append_subroutine(fn, name)
        
        @property
        def state_observer(_) -> mod_state.UsageStateObserver:
            return base_handle.state_observer
        
        @property
        def running_observer(_) -> mod_control.RunningObserver:
            return base_handle.running_observer

        @staticmethod
        def code(ct: mod_codegen.CodeTemplate):
            return base_handle.code(ct)
        
        @staticmethod
        def code_on_trial(ct: mod_codegen.CodeTemplate):
            return base_handle.code_on_trial(ct)
        
        @staticmethod
        def trial(ct: mod_codegen.CodeTemplate):
            return base_handle.trial(ct)
        

    return _Interface()
