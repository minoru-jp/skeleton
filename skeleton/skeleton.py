
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
from . import control as mod_pauser
from . import codegen as mod_codegen
from . import message as mod_report
from . import result as mod_result
from . import record as mod_record

if TYPE_CHECKING:
    from .state import UsageStateFull
    from .log import LogFull, Log
    from .event import EventHandlerFull, EventHandler
    from .context import ContextFull
    from .subroutine import Subroutine, SubroutineFull
    from .control import PauserFull
    from .message import MessageFull, Message, Messenger
    from .routine import Routine
    from .result import ResultFull, ResultReader
    from .record import ProcessRecordFull

    from .codegen import CodeTemplate


@runtime_checkable
class ResultHandler(Protocol):
    def __call__(self, result: ResultReader) -> bool:
        ...

@runtime_checkable
class SkeletonHandle(Protocol, Generic[mod_context.T]):
    @property
    def EventHandlerError(_) -> Type[Exception]:
        ...
    
    @property
    def RoutineError(_) -> Type[Exception]:
        ...
    
    @property
    def ResultHandlerError(_) -> Type[Exception]:
        ...

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
    def set_on_continue(handler: EventHandler) -> None:
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
    
    @staticmethod
    def start():
        ...
    @property
    def stop(_):
        ...
    @property
    def task_is_running(_):
        ...
    @property
    def pause(_):
        ...
    @property
    def resume(_):
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
    def running_observer(_) -> mod_pauser.RunningObserver:
        ...
    
    @staticmethod
    def code(ct: CodeTemplate) -> str:
        ...

    @staticmethod
    def code_on_trial(ct: CodeTemplate) -> str:
        ...
    
    @staticmethod
    def trial(ct: CodeTemplate):
        ...
    


def make_skeleton_handle(mode: Routine[mod_context.T_in] | Type[mod_context.T_in]) -> SkeletonHandle[mod_context.T_in]:

    class EventHandlerError(Exception):
        def __init__(self, proc_name: str, e: Exception):
            self.proc_name = proc_name
            self.orig_exception = e
            super().__init__(f"at {proc_name}: {e}")

    class RoutineError(Exception):
        def __init__(self, e: Exception):
            self.orig_exception = e
            super().__init__(e)
    
    class ResultHandlerError(Exception):
        def __init__(self, e: Exception):
            self.orig_exception = e
            super().__init__(e)
    
    def create_event_processor(event: EventHandlerFull, mess_full: MessageFull, ev_record: ProcessRecordFull)-> Callable[[str], Awaitable[Any]]:
        _event_handlers = event.get_all_handlers()
        
        async def process_event(event: str) -> None:
            event_handler = _event_handlers[event]
            mess_full.set_event_name(event)
            message = mess_full.get_reader()
            try:
                tmp = event_handler(message)
                result = await tmp if inspect.isawaitable(tmp) else tmp
            except Exception as e:
                raise EventHandlerError(event, e)
            ev_record.set_result(event, result)
            return result

        return process_event

    async def _engine(
            state: UsageStateFull,
            log_full: LogFull,
            event_full: EventHandlerFull,
            routine: Routine,
            context_full: ContextFull,
            pauser_full: PauserFull,
            message_full: MessageFull,
            ev_proc_record: ProcessRecordFull,
            sub_proc_record: ProcessRecordFull,
            result_full: ResultFull,
            result_handler: ResultHandler,
            ) -> None:
        try:
            process_event = create_event_processor(event_full, message_full, ev_proc_record)
            log = log_full.get_reader()
            log.logger.debug(f"[{log.role}] routine start")
            try:
                await process_event('on_start')
                context = context_full.setup_context()
                context_full.load_context_caller_accessors()
                Redo = context.signal.Redo
                Graceful = context.signal.Graceful
                Resigned = context.signal.Resigned
                while True:
                    try:
                        result = await routine(context)
                        result_full.set_graceful(result)
                        break
                    except Redo:
                        process_event('on_redo')
                        pauser_full.reset()
                        continue
                    except Graceful as e:
                        result_full.set_graceful(e.result)
                    except Resigned as e:
                        result_full.set_resigned(e.result)
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        log.logger.exception(f"[{log.role}] routine raises exception")
                        raise RoutineError(e)
                    finally:
                        result_full.set_event_process_record(ev_proc_record.get_reader())
                        result_full.set_routine_process_record(sub_proc_record.get_reader())

                log.logger.debug(f"[{log.role}] routine end")
                await process_event('on_end')
            except asyncio.CancelledError as e:
                log.logger.info(f"[{log.role}] routine was cancelled")
                await process_event('on_cancel')
            finally:
                await process_event('on_close')

        except RoutineError as e:
            result_full.set_error(e)
        except EventHandlerError as e:
            result_full.set_error(e)
        except Exception as e:
            log.logger.critical(f"[{log.role}] Internal error: {e.__class__.__name__}")
            result_full.set_error(e)
        finally:
            try:
                state.transit_state(state.TERMINATED)
            except state.InvalidStateError as e:
                if state.current_state is not state.TERMINATED:
                    raise
            try:
                result = result_full.get_reader()
                rethrow = result_handler(result)
            except Exception as e:
                raise ResultHandlerError(e)
            if result.error and rethrow:
                raise result.error

    def _DEAULT_RESULT_HANDLER(result: ResultReader):
        log = result.log
        log.logger.info(
            f"[{log.role}] loop result \n"
            f"    outcome: {result.outcome}"
            f"    return value: {result.return_value}\n"
            f"    recorded last event process: {result.event.last_recorded_process}\n"
            f"    recorded last event result: {result.event.last_recorded_result}\n"
            f"    recorded last routine process: {result.routine.last_recorded_process}\n"
            f"    recorded last routine result: {result.routine.last_recorded_result}\n"
            f"    error: {result.error}\n"
            )
        
        return False # rethrow if exception has raised
    
    def _start_engine(routine) -> asyncio.Task:

        if not isinstance(mode, Routine):
            raise RuntimeError("Routine is missing")
        
        task = asyncio.create_task(_engine(
            _state_full,
            _log_full,
            _event_full,
            routine,
            _context_full,
            _pauser_full,
            _message_full,
            _ev_proc_record_full,
            _sub_proc_record_full,
            _result_full,
            _result_handler,
            )
        )
        
        return task


    _field_type = mode if isinstance(mode, Type) else None

    _state_full = mod_state.setup_UsageStateFull()
    _log_full = mod_log.setup_LogFull()
    _pauser_full = mod_pauser.setup_PauserFull()
    _event_full = mod_event.setup_EventHandlerFull()
    _subroutine_full = mod_sub.setup_SubroutineFull()
    _ev_proc_record_full = mod_record.setup_ProcessRecordFull()
    _sub_proc_record_full = mod_record.setup_ProcessRecordFull()
    _message_full = mod_report.setup_MessageFull(_log_full.get_reader())
    _result_full = mod_result.setup_ResultFull(_log_full.get_reader())

    _result_handler = _DEAULT_RESULT_HANDLER
    
    _context_full = mod_context.setup_ContextFull(
        _log_full.get_reader(),
        _subroutine_full,
        _pauser_full.get_routine_interface(),
        _sub_proc_record_full,
        _message_full.get_environment().mapping,
        _message_full.get_event_messenger().mapping,
        _message_full.get_routine_messenger(),
    )

    class _Interface(SkeletonHandle):
        __slots__ = ()
        @property
        def EventHandlerError(_) -> Type[Exception]:
            return EventHandlerError
        
        @property
        def RoutineError(_) -> Type[Exception]:
            return RoutineError
        
        @property
        def ResultHandlerError(_) -> Type[Exception]:
            return ResultHandlerError

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
        def set_field(field: mod_context.T_in) -> None:
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
        def set_on_continue(handler: EventHandler) -> None:
            _state_full.maintain_state(
                _state_full.LOAD,
                _event_full.set_event_handler, 'on_continue', handler)
        @staticmethod
        def set_on_end(handler: EventHandler) -> None:
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
        def start():
            _state_full.transit_state(_state_full.ACTIVE)
            if not isinstance(mode, Routine):
                raise RuntimeError("Routine is missing")
            return _start_engine(mode)
        
        @property
        def stop(_):
            return _task.stop
        @property
        def task_is_running(_):
            return _task.is_running
        @property
        def pause(_):
            return _pauser_full.request_super_pause()
        @property
        def resume(_):
            return _pauser_full.super_resume()
        
        @property
        def environment(_) -> Messenger:
            return _message_full.get_environment()
        
        @staticmethod
        def append_subroutine(fn: Subroutine[mod_context.T_in], name: Optional[str] = None) -> None:
            _state_full.maintain_state(
                _state_full.LOAD,
                _subroutine_full.append_subroutine, fn, name)
        
        @property
        def state_observer(_) -> mod_state.UsageStateObserver:
            return _state_full.get_observer()
        
        @property
        def running_observer(_) -> mod_pauser.RunningObserver:
            return _pauser_full.get_observer_interface()

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
            return _start_engine(trial_routine)

    return _Interface()

