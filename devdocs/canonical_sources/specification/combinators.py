"""グループの組み合わせ方と、ワーカーの修飾に関する仕様。"""

from shikumi_devdoc.fields.specification import (
    INFORMATIVE,
    MUST,
    level,
    related,
)
from shikumi_devdoc.norms.common import canonical_source, summary
from shikumi_devdoc.norms.document import title

from devdocs.canonical_sources.specification.structure import (
    SPECIFICATION_PART as STRUCT_SPEC,
)


@summary("ノードの終わり方、Sequence と Parallel の終わり方、修飾に関する規則。")
@canonical_source(
    "Combinators",
    filename="combinators.md",
    order=20,
    merge_policy="local",
    heading="identity",
)
class SPECIFICATION_PART:
    """ノードの終わり方、Sequence と Parallel の終わり方、修飾に関する規則。"""

    class COMB_001:
        """
        どのノードも、次のどれかで終わる。

        | 終わり方 | 意味 |
        | --- | --- |
        | `succeeded` | 成功した |
        | `failed` | 例外で終わった |
        | `stopped` | 停止が要求された後に終わった。失敗ではない。例外で終わった場合は `failed` になる |
        | `skipped` | 手前の失敗か停止の要求のために、始まらなかった。失敗ではない |

        グループは、子の終わり方から自分の終わり方を決める規則だけを持つ。どのノードも同じ終わり方をするので、グループはどこまでも入れ子にできる。止まらなかったノードの扱いは RESULT_004 による。
        """

        title @= "How nodes end"
        level @= INFORMATIVE

    class COMB_002:
        """
        グループの種類は、子の**並べ方**(`Sequence` は一つずつ順に、`Parallel` は同時に)と、**終わり方** `until` の組み合わせで決まる。

        | | `until="all"`(既定) | `until="first_success"` | `until="first_done"` |
        | --- | --- | --- | --- |
        | `Sequence` | 順に全部(COMB_003) | 順に試して最初の成功まで(COMB_006) | 定義時エラー(COMB_007) |
        | `Parallel` | 同時に全部(COMB_004) | 同時に走らせて先着の成功(COMB_005) | 同時に走らせて先着の終了(COMB_009) |

        子グループを作る `sequence()` / `parallel()` も、同じ `until` を受け取る。
        """

        title @= "Arrangement and completion"
        level @= INFORMATIVE

    class COMB_003:
        """`Sequence(until="all")` は、子を定義順に一つずつ動かさなければならない。子が `succeeded` で終われば次の子へ進み、すべての子が `succeeded` なら自分も `succeeded` になる。子が `failed` で終わったら、残りの子を `skipped` とし、自分は `failed` になる。"""

        title @= "Sequence"
        level @= MUST

    class COMB_004:
        """`Parallel(until="all")` は、子をすべて同時に起動しなければならない。すべての子が `succeeded` なら自分も `succeeded` になる。子が `failed` で終わったら、残りの子に停止を要求し、それらが終わるのを待ってから、自分は `failed` になる。停止を要求された子は `stopped` で終わり、失敗に数えない。"""

        title @= "Parallel"
        level @= MUST

    class COMB_005:
        """`Parallel(until="first_success")` は、子をすべて同時に起動し、最初に `succeeded` で終わった子が出た時点で残りの子に停止を要求しなければならない。自分は `succeeded` になる。それまでに `failed` で終わった子は、自分の失敗にはならないが、記録には残す(RESULT_005)。すべての子が `failed` なら、自分は `failed` になる。"""

        title @= "Race"
        level @= MUST

    class COMB_006:
        """`Sequence(until="first_success")` は、子を定義順に一つずつ試さなければならない。子が `succeeded` で終われば残りを `skipped` とし、自分は `succeeded` になる。子が `failed` なら次の子を試す。すべての子が `failed` なら、自分は `failed` になる。`failed` で終わった子は、記録には残す(RESULT_005)。"""

        title @= "Fallback"
        level @= MUST

    class COMB_007:
        """`Sequence(until="first_done")` は、最初の子だけを動かすことと同じで意味を持たないため、クラスの定義時に `SkeletonDefinitionError` を送出しなければならない。"""

        title @= "Sequence cannot end at the first done"
        level @= MUST
        related @= (STRUCT_SPEC.STRUCT_015,)

    class COMB_008:
        """`Parallel(lockstep=True)` の子は、すべて `@repeat` のワーカーでなければならず、そうでなければクラスの定義時に `SkeletonDefinitionError` を送出する。各子の 1 回分の呼び出しがすべて終わるまで、どの子も次の回を始めてはならない。どれかの子の繰り返しが終わった場合、ほかの子は次の回を始めずに終わる。"""

        title @= "Lockstep"
        level @= MUST
        related @= (STRUCT_SPEC.STRUCT_015,)

    class COMB_009:
        """`Parallel(until="first_done")` は、子をすべて同時に起動し、最初に終わった子が出た時点で、終わり方を問わず残りの子に停止を要求しなければならない。自分の終わり方は、最初に終わった子と同じになる。一つの接続の読み取りと書き込みのように、どちらかが終われば全体が終わる処理のためのものである。"""

        title @= "First done"
        level @= MUST

    class COMB_010:
        """
        停止の要求を受けたグループは、まだ始めていない子を `skipped` とし、動いている子に停止を伝え、それらが終わるのを待たなければならない。自分は `stopped` で終わる。ただし、子に `failed` があれば `failed` で終わる(失敗は停止より優先する)。

        停止の要求は、グループから子へ、さらにその下へと伝わる。
        """

        title @= "Groups and stop requests"
        level @= MUST

    class COMB_011:
        """
        修飾は、ワーカーにデコレータとして付けて、呼ばれ方を変える。この版の修飾は `@repeat`、`@retry`、`@timeout`、`@optional` の四つと、`@service`(LIFE_010)、`@pinned` / `@isolated`(EXEC_003、EXEC_004)である。

        グループにも、生成時の引数 `modifiers` で `repeat`、`retry`、`timeout`、`optional` を付けられる(例: `Sequence(modifiers=(repeat(every=5.0),))`)。その場合、グループ全体の 1 回分が、ワーカーの 1 回分の呼び出しに当たる。
        """

        title @= "Modifiers"
        level @= INFORMATIVE

    class COMB_012:
        """
        `@repeat(times=None, every=None, until=None)` を付けたノードは、スケルトンが呼び出しを繰り返さなければならない。ループの外側はスケルトンが持ち、ワーカーは 1 回分の処理だけを書く。

        - `times` を指定すれば、その回数で終わる
        - `until` は各回の戻り値を受け取る関数で、真を返せば終わる
        - `every` を指定すれば、各回の開始の間隔を `every` 秒にする。前の回が `every` 秒より長くかかった場合は、待たずに次の回を始め、遅れを取り戻すために続けて呼ぶことはしない。間隔の待機は停止の要求で解ける
        - 指定した条件で終われば `succeeded`、停止の要求で終われば `stopped` になる

        どれも指定しなければ、停止の要求まで繰り返す。`until` が例外を送出した場合は、ノードが `failed` で終わる。
        """

        title @= "Repeat"
        level @= MUST

    class COMB_013:
        """`@repeat` のノードの 1 回分が `failed` で終わったら、次の回を始めずに、ノード全体が `failed` で終わらなければならない。失敗した回を呼び直したい場合は `@retry` を合わせて付ける。"""

        title @= "A failed round ends the repeat"
        level @= MUST

    class COMB_014:
        """`@retry(times, backoff=None)` を付けたノードは、1 回分の呼び出しが `failed` で終わったとき、最大 `times` 回まで呼び直さなければならない。`backoff` は呼び直す前に待つ秒数で、待機は停止の要求で解ける。呼び直しが尽きたら、最後の失敗でノードは `failed` になる。それまでの失敗の例外も記録に残す(RESULT_005)。"""

        title @= "Retry"
        level @= MUST

    class COMB_015:
        """`@timeout(seconds)` を付けたノードは、1 回分の呼び出しが `seconds` 秒を超えたら、そのノードに停止を要求し、例外 `WorkerTimeout` で `failed` としなければならない。停止は協調的なので、要求の後も呼び出しが戻らなければ、そのノードは止まらなかったノードとして扱われる(RESULT_004)。"""

        title @= "Timeout"
        level @= MUST

    class COMB_016:
        """`@optional` を付けたノードは、`failed` で終わっても、親からは `succeeded` として扱われなければならない。失敗と例外は記録に残す(RESULT_005)。止めずに続けたい、失敗しても構わない処理のためのものである。"""

        title @= "Optional"
        level @= MUST

    class COMB_017:
        """修飾は、デコレータを重ねた順によらず、内側から `timeout`、`retry`、`repeat`、`optional` の順に適用しなければならない。つまり `timeout` は 1 回の呼び出しに、`retry` はその呼び直しに、`repeat` は呼び直しを含めた 1 回分の繰り返しに、`optional` は最終的な終わり方に効く。"""

        title @= "Order of modifiers"
        level @= MUST
