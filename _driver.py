
import asyncio
import logging
from typing import Any, Generic, Protocol, TypeVar
from skeleton import make_skeleton_handle

from skeleton.codegen.linearloop import LinearLoop
from skeleton.context import Context
from skeleton.skeleton import SkeletonHandle

logger = logging.getLogger("myapp")
logger.setLevel(logging.DEBUG)
logging.basicConfig(level=logging.DEBUG)

async def main():
    
    def routine(context: Context[Any]):
        print("hello world.")
        context.caller.subroutine()
        print(f"{context.prev.process} result: {context.prev.result}")
        return 'hello return value'

    def subroutine(context: Context[Any]):
        return "hello small world."

    handle = make_skeleton_handle(routine)

    handle.set_role("exsample")
    handle.set_logger(logger)

    # 各EventHandlerはデフォルトでイベント名をロギングする

    handle.append_subroutine(subroutine)

    task = handle.start()


if __name__ == "__main__":
    asyncio.run(main())