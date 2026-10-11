"""実行の開始と、実行中の操作(一時停止、再開、停止、待ち合わせ)に関する仕様。"""

from shikumi_devdoc.fields.specification import (
    INFORMATIVE,
    MUST,
    SHOULD_NOT,
    condition,
    level,
    related,
)
from shikumi_devdoc.norms.common import canonical_source, summary
from shikumi_devdoc.norms.document import title

from devdocs.canonical_sources.specification.combinators import (
    SPECIFICATION_PART as COMB_SPEC,
)
from devdocs.canonical_sources.specification.lifecycle import (
    SPECIFICATION_PART as LIFE_SPEC,
)


@summary(
    "run と start、操作盤 Run、区切りでの一時停止、待ち合わせ、gpframe とのつなぎに関する規則。"
)
@canonical_source(
    "Control",
    filename="control.md",
    order=50,
    merge_policy="local",
    heading="identity",
)
class SPECIFICATION_PART:
    """run と start、操作盤 Run、区切りでの一時停止、待ち合わせ、gpframe とのつなぎに関する規則。"""

    class CTRL_001:
        """`honehone.run(obj, *, listener=None, stop_timeout=None)` は、呼び出したスレッドを家のスレッドとして実行し、終わるまで待って `Result` を返さなければならない。メインスレッドから呼ばれた場合、実行中の `KeyboardInterrupt`(Ctrl+C)を停止の要求に変える。二度目の Ctrl+C は、二度目の停止の要求になる(LIFE_009)。"""

        title @= "run"
        level @= MUST
        related @= (LIFE_SPEC.LIFE_009,)

    class CTRL_002:
        """`honehone.start(obj, *, listener=None, stop_timeout=None)` は、実行のための家のスレッドを用意して実行を始め、待たずに操作盤 `Run` を返さなければならない。"""

        title @= "start"
        level @= MUST

    class CTRL_003:
        """`stop_timeout` は、停止を要求したノードが終わるのを待つ上限の秒数である。上限を過ぎても終わらないノードは、止まらなかったノードとして見切る(RESULT_004)。`None` なら終わるまで待つ。"""

        title @= "stop_timeout"
        level @= MUST

    class CTRL_004:
        """
        `Run` は次の操作を持たなければならない。ノードは名前で指し(STRUCT_011)、存在しない名前には `KeyError` を送出する。

        | 操作 | 内容 |
        | --- | --- |
        | `pause(name=None)` | 一時停止を要求する(CTRL_005) |
        | `resume(name=None)` | 一時停止の要求を取り消す(CTRL_008) |
        | `stop()` | 実行全体に停止を要求する(CTRL_009) |
        | `wait(timeout=None)` | 実行の終わりを待ち、`Result` を返す。時間切れなら `None` |
        | `wait_until(name, state, timeout=None)` | ノードが指定の状態になるまで待つ(CTRL_010) |
        | `state(name)` | ノードの今の状態を返す(RESULT_002) |

        どの操作も、どのスレッドからでも呼べる。
        """

        title @= "The Run handle"
        level @= MUST

    class CTRL_005:
        """
        `pause(name)` は一時停止を要求し、止まるのを待たずに戻らなければならない。指したノードとその子孫は、次の**区切り**で止まる。`name` を省略すると本体全体が対象になる。区切りは、スケルトンが呼び出しの間に持つ次の時点である。

        - `@repeat` の次の回を始める前
        - `Sequence` の次の子を始める前
        - `Parallel` が子を起動する前
        - `@retry` の呼び直しの前
        - ワーカーが `ctx.checkpoint()` を呼んだとき

        要求を受けてから区切りで止まるまでのノードは `pausing`、区切りで止まったノードは `paused` になる。
        """

        title @= "Pausing at boundaries"
        level @= MUST

    class CTRL_006:
        """一時停止は、呼び出し中の 1 回分を中断してはならない。スレッドを外から安全に凍結する方法はないためである。ループと手順の移り目をスケルトンが持つので、ワーカーが何も協力しなくても、区切りでは確実に止まる。"""

        title @= "A call in progress is not interrupted"
        level @= MUST

    class CTRL_007:
        """service は区切りを持たない。`ready` の後も動き続ける service を一時停止させるには、ワーカー自身が `ctx.checkpoint()` を呼ぶ必要がある。`ctx.checkpoint()` は、自分か祖先に一時停止が要求されていれば、再開か停止の要求まで待たなければならない。ここだけは協調的な一時停止になる。"""

        title @= "Checkpoints in services"
        level @= MUST
        related @= (LIFE_SPEC.LIFE_010,)

    class CTRL_008:
        """一時停止の要求は、名前ごとに記録しなければならない。ノードは、自分か祖先のどれかに要求があれば止まる。`resume(name)` はその名前の要求だけを取り消し、ほかの要求が残っていなければノードは `running` に戻る。`pause(name)` を二度呼んでも、要求は一つである。"""

        title @= "Resuming"
        level @= MUST

    class CTRL_009:
        """`stop()` は実行全体に停止を要求し、終わるのを待たずに戻らなければならない。停止の要求は一時停止より優先し、`paused` や `pausing` のノードも起こして止める。停止の要求は取り消せない。二度目の `stop()` は二度目の停止の要求になる(LIFE_009)。"""

        title @= "Stopping"
        level @= MUST
        related @= (LIFE_SPEC.LIFE_009,)

    class CTRL_010:
        """`wait_until(name, state, timeout=None)` は、ノードが `state` になった時点で `True` を返さなければならない。すでにその状態を経ていれば(たとえば一度 `ready` になった service)、すぐに `True` を返す。実行が終わってその状態にもう達し得なくなった場合と、時間切れの場合は `False` を返す。"""

        title @= "Waiting for a node"
        level @= MUST

    class CTRL_011:
        """`Parallel(lockstep=True)` の子の一つが止まると、ほかの子も次の回を始められないため、グループ全体が足並みをそろえて止まる。"""

        title @= "Pausing in lockstep"
        level @= INFORMATIVE
        related @= (COMB_SPEC.COMB_008,)

    class CTRL_012:
        """ワーカーの中から、そのワーカー自身の実行の `Run.wait()` や `Run.wait_until()` を呼ぶべきではない。自分の終わりを自分で待つことになり、終わらなくなる。"""

        title @= "Waiting from inside a run"
        level @= SHOULD_NOT
        condition @= "ワーカーの中で `Run` を使うとき。"

    class CTRL_013:
        """`honehone.control(obj)` は、実行中または実行を終えたインスタンス `obj` の `Run` を返さなければならない。インスタンス一つが実行一つに対応する(LIFE_001)ので、インスタンスが実行を指す鍵になる。実行を始めていないインスタンスには `SkeletonStateError` を送出する。"""

        title @= "Finding the Run of an instance"
        level @= MUST
        related @= (LIFE_SPEC.LIFE_001,)

    class CTRL_014:
        """
        gpframe の木にスケルトンを組み込む部品は、本体とは別のモジュール `honehone.gpframe` に置かなければならない。`honehone` 本体の公開面には、gpframe の型を出してはならない。

        `honehone.gpframe.routine` は gpframe のフレーム用ルーティンで、`s.spawn(honehone.gpframe.routine, obj)` のように使い、報告の受け手を渡すときは `s.spawn(honehone.gpframe.routine, obj, listener)` とする。家のスレッドはそのフレームのスレッドである。フレームへの停止の要求は実行への停止の要求になり、実行が `failed` で終われば、フレームは `SkeletonFailed` で失敗する(RESULT_008)。操作盤は `honehone.control(obj)` で取り出せる。
        """

        title @= "Joining a gpframe tree"
        level @= MUST

    class CTRL_015:
        """一時停止を要求されたグループは、自分の区切りで止まっているとき、または動いている子(`running` と `ready` の子)がすべて `paused` になったときに `paused` になり、それ以外のあいだは `pausing` でなければならない。グループの状態から、その下がすべて止まったかどうかが分かるためである。"""

        title @= "Pausing groups"
        level @= MUST
