
import asyncio
from typing import Any, Generic, Protocol, TypeVar
from skeleton import make_skeleton_handle

from skeleton.codegen.linearloop import LinearLoop
from skeleton.context import Context
from skeleton.skeleton import SkeletonHandle


async def main():
    async def routine(context: Context[Any]):
        print("hello world.")
        context.caller.subroutine()
        print(f"{context.prev.process} result: {context.prev.result}")

    def subroutine(context: Context[Any]):
        return "hello small world."

    handle = make_skeleton_handle(routine)

    handle.set_role("exsample")

    # 各EventHandlerはデフォルトでイベント名をロギングする

    handle.append_subroutine(subroutine)

    task = handle.start()


if __name__ == "__main__":
    asyncio.run(main())