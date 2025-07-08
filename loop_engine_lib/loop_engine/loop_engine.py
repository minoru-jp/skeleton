
"""
loop_engine.py
-----------------

High-level assembly of the loop engine components.

This module builds and wires together the Protocol implementations
from internal.py into a ready-to-use LoopEngineHandle.

Usage and detailed documentation are provided in loop_engine_manual.py.

Note for tests: Internal state is intentionally hidden; tests may access it
via .__closure__ references as a backdoor if needed.

"""

import asyncio
import inspect
import logging

from typing import Any, Callable, Mapping, Optional, Type

from loop_engine_lib.loop_engine.hidden_components import (
    State,
    LoopControl,
    LoopResult,
    LoopInterrupt,
    LoopEvent
)
import loop_engine_lib.loop_engine.hidden_components as _setup

from loop_engine_manual import (
    StateObserver,
    StateError,
    LoopResultReader,
    LoopInterruptObserver,
    LoopException,
    LoopError,
    LoopSignal,
    LoopLog,
    LoopEngineHandle,
    Circuit,
    CircuitTools,
)





    
def make_loop_engine_handle(static_circuit: Optional[Circuit] = None) -> LoopEngineHandle:

    def _compile(circuit_name, circuit_code: str, action_ns: Mapping):
        namespace = {
            "__builtins__" : {},
            "Break": _loop_control.exceptions.signals.Break,
            **action_ns,
        }
        dst = {}
        exec(circuit_code, namespace, dst)
        _compiled_func = dst[circuit_name]
        return _compiled_func
    
    async def _loop_engine(
            log: LoopLog, state: State,
            circuit, ev: LoopEvent, control: LoopControl,
            res: LoopResult) -> None:
        try:
            log.logger.info(f"[{log.role}] Loop start")
            errors = control.exceptions.errors
            control.setup_event_context()
            try:
                await control.process_event(ev.START)
                control.setup_action_context()
                try:
                    circuit_tmp = circuit(control)
                except Exception as e:
                    raise errors.CircuitError(e)
                if inspect.isawaitable(circuit_tmp):
                    try:
                        await circuit_tmp
                    except Exception as e:
                        raise errors.CircuitError(e)
                await control.process_event(ev.STOP_NORMALLY)
            except asyncio.CancelledError as e:
                log.logger.info(f"[{log.role}] Loop was cancelled")
                await control.process_event(ev.STOP_CANCELED)
            finally:
                await control.process_event(ev.CLEANUP)
                await control.process_event(ev.LOOP_RESULT)
                res.set_loop_result(control.event.prev_result)
        except errors.CircuitError as e:
            # Exceptions thrown by action-reactor and action are included here.
            res.set_circuit_error(e)
            raise
        except errors.EventReactorError as e:
            res.set_event_reactor_error(e)
            raise
        except errors.EventHandlerError as e:
            res.set_handler_error(e)
            raise
        except Exception as e:
            log.logger.critical(f"[{log.role}] Internal error: {e.__class__.__name__}")
            res.set_internal_error(e)
            raise
        finally:
            res.set_last_process(_ev_step.prev_proc)
            state.transit_state(_state.TERMINATED)

            # Do not call res.cleanup() in here
            control.cleanup()
            circuit = None
            ev = None # type: ignore
            control = None # type: ignore
            res = None # type: ignore
    
    def _start_loop_engine(circuit_func):
        return _task_control.start(
            _loop_engine,
            circuit_func,
            _state,
            _log,
            _event,
            _loop_control,
            _loop_res)

    _event = _setup.setup_loop_event()

    _state = _setup.setup_state()
    _state_observer = _setup_state_observer(_state)
    
    _evh_registry = _setup.setup_event_handler_registry(_event, _state)
    _act_registry = _setup.setup_action_registry(_state)
    _react_registry = _setup.setup_reactor_registry(_state)
    
    _ev_step = _setup.setup_step_slot()
    _act_step = _setup.setup_step_slot()
    


    _exc = _setup_loop_exception()
    _task_control = _setup.setup_task_control(_state)
    
    _circ_code_factory = _setup.setup_circuit_code_factory()
    
    _log = _setup_loop_log(_state)

    _loop_control = _setup.setup_loop_control(
        evh = _evh_registry,
        context = _react_registry,
        ev_step = _ev_step,
        act_step = _act_step,
        exc = _exc
    )

    _irq = _setup.setup_loop_interrupt(_event, _loop_control)
    _running_observer = _setup_loop_interrupt_observer(_irq)

    _loop_res = _setup.setup_loop_result()
    _loop_res_reader = _setup_loop_result_reader(_state, _loop_res)




    class _Interface(LoopEngineHandle):
        __slots__ = ()
        @property
        def log(_):
            return _log
        
        @staticmethod
        def set_on_start(fn):
            _evh_registry.set_event_handler('on_start', fn)
        @staticmethod
        def set_on_end(fn):
            _evh_registry.set_event_handler('on_end', fn)
        @staticmethod
        def set_on_stop(fn):
            _evh_registry.set_event_handler('on_stop', fn)
        @staticmethod
        def set_on_closed(fn):
            _evh_registry.set_event_handler('on_closed', fn)
        @staticmethod
        def set_on_result(fn):
            _evh_registry.set_event_handler('on_result', fn)
        @staticmethod
        def set_on_pause(fn):
            _evh_registry.set_event_handler('on_pause', fn)
        @staticmethod
        def set_on_resume(fn):
            _evh_registry.set_event_handler('on_resume', fn)
        
        @staticmethod
        def generate_circuit_code(name: str, irq: bool, ):
            return _circ_code_factory.generate_circuit_code(
                name,
                _act_registry.get_actions(),
                irq,
                False
            )
        
        @staticmethod
        def start():
            if not static_circuit:
                raise RuntimeError("XXX")
            return _start_loop_engine(static_circuit)
        @staticmethod
        def start_with_compile(irq: bool):
            circuit_name = "_generated_circuit"
            return _start_loop_engine(
                _compile(
                    circuit_name,
                    iface.generate_circuit_code(
                        circuit_name, irq
                    ),
                    _act_registry.get_action_namespace()
                )
            )
        @property
        def stop(_):
            return _task_control.stop
        @property
        def task_is_running(_):
            return _task_control.is_running
        @property
        def pause(_):
            return _irq.request_pause
        @property
        def resume(_):
            return _irq.resume
        
        @property
        def append_action(_):
            return _act_registry.append_action
        
        @property
        def set_event_reactor_factory(_):
            return _react_registry.set_event_reactor_factory
        @property
        def set_action_reactor_factory(_):
            return _react_registry.set_action_reactor_factory
        
        @property
        def state_observer(_) -> StateObserver:
            return _state_observer
        
        @property
        def running_observer(_) -> LoopInterruptObserver:
            return _running_observer

        @property
        def loop_result(_) -> LoopResultReader:
            return _loop_res_reader

    iface = _Interface()
    return iface

