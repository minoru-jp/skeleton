
from __future__ import annotations

import asyncio
import inspect
import logging
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Generic, Optional, Protocol, Type, runtime_checkable

from . import state as mod_state
from . import log as mod_log
from . import event as mod_event
from . import context as mod_context
from . import action as mod_action
from . import pauser as mod_pauser
from . import codegen as mod_codegen
from . import report as mod_report
from . import task as mod_task

if TYPE_CHECKING:
    from .state import UsageStateFull
    from .log import LogFull, Log
    from .event import EventHandlerFull, EventHandler
    from .context import ContextFull
    from .action import Action, ActionFull
    from .pauser import PauserFull
    from .report import ReportFull, ReportReader, Message
    from .routine import Routine

    from .codegen import CodeTemplate


@runtime_checkable
class ResultHandler(Protocol):
    def __call__(self, report: ReportReader) -> bool:
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
    def environment(_) -> Message:
        ...
    
    @staticmethod
    def append_action(action: Action[mod_context.T], name: Optional[str] = None) -> None:
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
    
    def create_event_processor(event: EventHandlerFull, report_full: ReportFull)-> Callable[[str], Awaitable[Any]]:
        _event_handlers = event.get_all_handlers()
        
        async def process_event(event: str) -> None:
            event_handler = _event_handlers[event]
            report_full.set_event_name(event)
            report_reader = report_full.get_reader()
            try:
                tmp = event_handler(report_reader)
                result = await tmp if inspect.isawaitable(tmp) else tmp
            except Exception as e:
                raise EventHandlerError(event, e)
            return result

        return process_event

    async def _engine(
            state: UsageStateFull,
            log: LogFull,
            event_full: EventHandlerFull,
            routine: Routine,
            context_full: ContextFull,
            pauser_full: PauserFull,
            report_full: ReportFull,
            result_handler: ResultHandler,
            ) -> None:
        context = None
        try:
            process_event = create_event_processor(event_full, report_full)
            log.logger.info(f"[{log.role}] Loop start")
            try:
                await process_event('on_start')
                context = context_full.setup_context()
                context_full.load_context_caller_accessors()
                Continue = context.signal.Continue
                while True:
                    try:
                        await routine(context)
                        break
                    except Continue:
                        process_event('on_continue')
                        pauser_full.reset()
                        continue
                    except Exception as e:
                        log.logger.exception(f"[{log.role}] routine raises exception")
                        raise RoutineError(e)
                await process_event('on_end')
                log.logger.info(f"[{log.role}] routine end")
            except asyncio.CancelledError as e:
                log.logger.info(f"[{log.role}] routine was cancelled")
                await process_event('on_cancel')
            finally:
                await process_event('on_close')

        except RoutineError as e:
            report_full.set_error(e)
        except EventHandlerError as e:
            report_full.set_error(e)
        except Exception as e:
            log.logger.critical(f"[{log.role}] Internal error: {e.__class__.__name__}")
            report_full.set_error(e)
        finally:
            try:
                state.transit_state(state.TERMINATED)
            except state.InvalidStateError as e:
                if state.current_state is not state.TERMINATED:
                    raise
            if context:
                report_full.set_last_routine_process(context.prev.process)
                report_full.set_last_routine_result(context.prev.result)
            report_reader = report_full.get_reader()
            try:
                rethrow = result_handler(report_reader)
            except Exception as e:
                raise ResultHandlerError(e)
            if report_reader.error and rethrow:
                raise report_reader.error

    def _DEAULT_RESULT_HANDLER(report: ReportReader):
        log = report.log
        log.logger.info(
            f"[{log.role}] loop ended with \n"
            f"    last routine process: {report.last_routine_process}\n"
            f"    last routine result: {report.last_routine_result}\n"
            f"    error: {report.error}\n"
            )
        
        return False # rethrow if exception has raised
    
    def _start_engine(routine):
        return _task.start(
            _engine,
            _state_full,
            _log_full, 
            _event_full,
            routine,
            _context_full,
            _pauser_full,
            _report_full,
            _result_handler)
    

    _field_type = mode if isinstance(mode, Type) else None

    _state_full = mod_state.setup_UsageStateFull()

    _log_full = mod_log.setup_LogFull()

    _pauser_full = mod_pauser.setup_PauserFull()
    
    _event_full = mod_event.setup_EventHandlerFull()
    _action_full = mod_action.setup_ActionRegistry()
    
    _report_full = mod_report.setup_ReportFull(_log_full)

    _result_handler = _DEAULT_RESULT_HANDLER
    
    _context_full = mod_context.setup_ContextFull(
        _log_full,
        _action_full,
        _pauser_full.get_routine_interface(),
        _report_full.get_environment().mapping,
        _report_full.get_event_message().mapping,
        _report_full.get_routine_message(),
    )

    _task = mod_task.setup_TaskControl(_state_full)
    

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
        def environment(_) -> Message:
            return _report_full.get_environment()
        
        @staticmethod
        def append_action(action: Action[mod_context.T_in], name: Optional[str] = None) -> None:
            _state_full.maintain_state(
                _state_full.LOAD,
                _action_full.append_action, action, name)
        
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
            return ct.generate_routine_code(_field_type, _action_full.get_actions())
        
        @staticmethod
        def code_on_trial(ct: mod_codegen.CodeTemplate):
            _action_full.remap_to_secure_action_name()
            code = ct.generate_trial_routine_code(
                "trial_routine",
                _action_full.get_actions(),
                _action_full.translate_raw_to_secure_name
            )
            _action_full.remap_to_raw_action_name()
            return code
        
        @staticmethod
        def trial(ct: mod_codegen.CodeTemplate):
            ROUTINE_NAME = "trial_routine"
            _state_full.transit_state(_state_full.ACTIVE)
            _action_full.remap_to_secure_action_name()
            code = ct.generate_trial_routine_code(
                ROUTINE_NAME,
                _action_full.get_actions(),
                _action_full.translate_raw_to_secure_name
            )
            dst = {}
            exec(code, {}, dst)
            routine = dst[ROUTINE_NAME]
            return _start_engine(routine)

    return _Interface()

