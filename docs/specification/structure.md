<!-- Published from devdocs/canonical_documents/specification/structure.md sha256:945f5d71db82976ae95f15c2b09733a34aa7d6a808f6f91a03440c393216af28. Translated from the Japanese canonical document; edit the canonical source instead of this file. -->
# Structure

Rules on skeleton classes and implementation classes, workers and groups, and checking the structure.

## STRUCT_001

A skeleton is a class with work of a fixed shape. The shape (which workers run, in what order, arranged how) is decided by the skeleton class, and the content of each worker is filled in by an implementation class by overriding methods.

- **Skeleton class**: a class that inherits `Skeleton` directly. It defines workers, groups, `boot` and `cleanup`
- **Implementation class**: a class that further inherits a skeleton class. It only overrides the content of workers and does not change the shape

Separating the shape from the content lets the same shape be used many times with different content, and the shape can be understood by reading the class definition.

title: Skeleton classes and implementation classes

level: INFORMATIVE

## STRUCT_002

Only skeleton classes must be able to define workers, groups, `boot` and `cleanup`. If an implementation class declares a group, or uses a decorator that makes a worker, `boot` or `cleanup`, `SkeletonDefinitionError` must be raised when the class is defined.

title: Only skeleton classes define the shape

level: MUST

## STRUCT_003

When an implementation class defines a method with the same name as a worker, `boot` or `cleanup`, that method replaces the content. The replacing method must inherit all of the original membership and modifiers without being decorated again.

title: Overriding keeps the role

level: MUST

## STRUCT_004

Methods of workers, `boot` and `cleanup` take the form `(self, ctx)`. `ctx` is the execution environment `Context` (EXEC_010). `async def` methods are not handled in this version, and `SkeletonDefinitionError` must be raised when the class is defined.

title: Signature of workers

level: MUST

## STRUCT_005

Groups are declared as class attributes. A group without a parent is made with `Sequence()` or `Parallel()`, and a group that goes inside another group is made with the parent's method `sequence()` / `parallel()`.

```python
class DevEnv(Skeleton):
    main = Sequence()
    services = main.parallel()  # goes inside main, at this position
```

title: Declaring groups

level: MUST

## STRUCT_006

A group can be used as a decorator as it is, and it must make the decorated method a worker of that group. A method belongs to at most one group. If it is put into two or more groups, `SkeletonDefinitionError` must be raised when the class is defined.

title: Groups are decorators

level: MUST

## STRUCT_007

The order of the children (workers and child groups) in a group must be the order in which they are defined in the class body. Workers and child groups are not distinguished. The position of a child group is the position where its attribute is declared.

title: Order of children

level: MUST

## STRUCT_008

A group without a parent is called the **root**. There must be at most one root, and if there are two or more, `SkeletonDefinitionError` is raised when the class is defined. In a skeleton without a root, the body is empty and only `boot` and `cleanup` run.

title: The root group

level: MUST

## STRUCT_009

A group with no children must make `SkeletonDefinitionError` raised when the class is defined. This is to point out a forgotten decorator early.

title: Empty groups

level: MUST

## STRUCT_010

A method that belongs to no group and is neither `boot` nor `cleanup` is a plain method. Workers can call it as a helper, and the skeleton is not involved.

title: Plain methods

level: INFORMATIVE

## STRUCT_011

Workers, `boot` and `cleanup` are called **nodes**, and groups are nodes too. The name of a node is the method name for a method and the attribute name for a group, and names are unique within the class. Operations (CTRL_004) and results (RESULT_005) refer to nodes by name.

Reports (REPORT_003) carry a **path** in addition to the name. The path is the names from the root to the node joined with `.` (for example `main.services.db`).

title: Node names and paths

level: MUST

## STRUCT_012

`Skeleton` inherits `abc.ABC`. A worker decorated with `abc.abstractmethod` must be overridden by an implementation class. Creating a class that does not override it raises `TypeError` through the standard mechanism. Type checkers can also detect it as creating an abstract class.

title: Required workers

level: MUST

## STRUCT_013

The body of a non-abstract worker is the default behavior of that worker. If the body is only `...`, it does nothing. Even an implementation class that overrides nothing starts, stops on a stop request, and runs through to the cleanup. The shape alone can be run first, while still unfinished.

title: Default behavior

level: INFORMATIVE

## STRUCT_014

A `@repeat` worker without an interval (`every`) should be an `abc.abstractmethod`. Repeating a body that does nothing keeps the CPU spinning.

title: Repeated workers should be required

level: SHOULD

condition: When writing a skeleton class.

## STRUCT_015

All checks of the structure must be done when the class is defined (`__init_subclass__`). An error in the structure is never found after the run has started. What is checked is the rules of this document, plus contradictions between combinations and modifiers (COMB_007, COMB_008, LIFE_014) and contradictions in the unit of execution (EXEC_003, EXEC_005).

title: Checking at definition time

level: MUST
