from __future__ import annotations

from typing import Any, MutableSequence, Protocol

class CodeSnippet(Protocol):
    def _assign_depth(self, upper) -> None:
        ...

    def _check_cyclic(self, _: Block) -> None:
        ...

    def render(self, buffer: MutableSequence[str], indent: str = '    ') -> None:
        ...

class Code(CodeSnippet):
    __slots__ = ('_depth', '_code',)
    def __init__(self, code: str):
        self._depth = 0
        self._code = code
    
    def _assign_depth(self, upper) -> None:
        self._depth = upper + 1
    
    def _check_cyclic(self, _: Block) -> None:
        pass

    def render(self, buffer: MutableSequence[str], indent: str = '    ') -> None:
        buffer.append(indent * self._depth + self._code)

class Blank(CodeSnippet):
    __slots__ = ()

    def _assign_depth(self, upper) -> None:
        self._depth = 0
    
    def _check_cyclic(self, _: Block) -> None:
        pass
    
    def render(self, buffer: MutableSequence[str], indent: str = '    ') -> None:
        buffer.append("")

BLANK = Blank()

class Suite(CodeSnippet):
    __slots__ = ('_depth', '_lines',)
    def __init__(self, lines: MutableSequence[str]):
        self._depth = 0
        self._lines = lines
    
    def _assign_depth(self, upper) -> None:
        self._depth = upper + 1
    
    def _check_cyclic(self, _: Block) -> None:
        pass

    def render(self, buffer: MutableSequence[str], indent: str = '    ') -> None:
        for line in self._lines:
            buffer.append(indent * self._depth + line)

class Head(Suite):
    __slots__ = ()
    
    def _assign_depth(self, upper) -> None:
        self._depth = upper

class Block:
    __slots__ = ('_depth', '_head', '_body', '_tail', '_is_tail')
    def __init__(self, head: str | MutableSequence[str]):
        self._depth = 0
        if isinstance(head, str):
            casted_head: Head = Head([head])
        elif isinstance(head, MutableSequence):
            casted_head: Head = Head(head)
        else:
            raise TypeError(f"Invalid type '{type(head)}'")
        self._head = casted_head
        self._body: MutableSequence[Block | Code | Suite | Blank] = []
        self._tail: Block | None = None
        self._is_tail: bool = False


    def _assign_depth(self, upper = 0) -> None:
        self._depth = upper + 1 if not self._is_tail else upper
        self._head._assign_depth(self._depth)
        for part in self._body:
            part._assign_depth(self._depth)
        if self._tail:
            self._tail._assign_depth(self._depth)
    
    def _check_cyclic(self, block: Block) -> None:
        if block is self:
            raise ValueError(f"cyclic references found '{block}'")
        for part in self._body:
            part._check_cyclic(block)
        if self._tail:
            self._tail._check_cyclic(block)

    def _internal_render(self, buffer: MutableSequence[str], indent: str) -> MutableSequence[str]:
        # head
        self._head.render(buffer)
        # body
        if self._body:
            for part in self._body:
                if isinstance(part, Block):
                    part._internal_render(buffer, indent)
                else:
                    part.render(buffer, indent)
        else:
            empty = Code('pass')
            empty._assign_depth(self._depth)
            empty.render(buffer, indent)

        #tail
        if self._tail:
            self._tail._internal_render(buffer, indent)
        
        return buffer
    
    def render(self, buffer: MutableSequence[str], indent: str = '    ') -> MutableSequence[str]:
        self._assign_depth(self._depth)
        self._internal_render(buffer, indent)
        return buffer
    
    def add_block(self, part: Block) -> Block:
        if not isinstance(part, Block):
            raise TypeError(f"Invalid type '{type(part)}'")
        self._check_cyclic(part)
        self._body.append(part)
        return part
    
    def add(self, part: str | MutableSequence[str]) -> None:
        if isinstance(part, str):
            self._body.append(Code(part))
        elif isinstance(part, MutableSequence):
            self._body.append(Suite(part))
        else:
            raise TypeError(f"Invalid type '{type(part)}'")
    
    def add_blank(self) -> None:
        self._body.append(BLANK)
    
    def set_tail(self, tail: str | MutableSequence[str]) -> Block:
        tail_block = Block(tail)
        tail_block._is_tail = True
        self._check_cyclic(tail_block)
        self._tail = tail_block
        return tail_block

