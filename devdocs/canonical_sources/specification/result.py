"""実行の結果(Result)、ノードの状態と記録に関する仕様。"""

from shikumi_devdoc.fields.specification import (
    INFORMATIVE,
    MUST,
    MUST_NOT,
    level,
    related,
)
from shikumi_devdoc.norms.common import canonical_source, summary
from shikumi_devdoc.norms.document import title

from devdocs.canonical_sources.specification.combinators import (
    SPECIFICATION_PART as COMB_SPEC,
)
from devdocs.canonical_sources.specification.control import (
    SPECIFICATION_PART as CTRL_SPEC,
)
from devdocs.canonical_sources.specification.lifecycle import (
    SPECIFICATION_PART as LIFE_SPEC,
)


@summary("Result、実行全体の判定、ノードの状態と記録、例外の送出に関する規則。")
@canonical_source(
    "Result",
    filename="result.md",
    order=60,
    merge_policy="local",
    heading="identity",
)
class SPECIFICATION_PART:
    """Result、実行全体の判定、ノードの状態と記録、例外の送出に関する規則。"""

    class RESULT_001:
        """
        実行が終わると、結果 `Result` が確定する。`Result` は次のものを持たなければならない。

        | 名前 | 内容 |
        | --- | --- |
        | `outcome` | 実行全体の判定。`"completed"`、`"failed"`、`"stopped"` のどれか(RESULT_003) |
        | `nodes` | ノードの名前から記録 `NodeRecord` への読み取り専用の対応(RESULT_005) |
        | `cleanup_errors` | `cleanup` で起きた例外の並び(RESULT_007) |
        | `stuck` | 止まらなかったノードの名前の並び(RESULT_004) |
        | `raise_if_failed()` | 失敗なら例外を送出する(RESULT_008) |

        `Result` は、`Run.wait()` と `honehone.run()` が返す。どちらも例外を送出せず、かならず `Result` を返す。
        """

        title @= "Result"
        level @= MUST
        related @= (CTRL_SPEC.CTRL_001, CTRL_SPEC.CTRL_004)

    class RESULT_002:
        """
        ノードの状態は次のどれかでなければならない。

        | 状態 | 意味 |
        | --- | --- |
        | `pending` | まだ始まっていない |
        | `running` | 動いている |
        | `pausing` | 一時停止を要求され、区切りを待っている |
        | `paused` | 区切りで止まっている |
        | `ready` | service が準備を終え、動き続けている |
        | `succeeded` / `failed` / `stopped` / `skipped` | 終わった(COMB_001) |
        | `stuck` | 停止を要求されたが、`stop_timeout` までに終わらなかった |
        """

        title @= "Node states"
        level @= MUST
        related @= (COMB_SPEC.COMB_001,)

    class RESULT_003:
        """
        `outcome` は次の順に判定しなければならない。

        1. `boot`、本体、`cleanup` のどれかに、最終的な `failed` があれば `"failed"`
        2. そうでなく、実行に停止が要求されていれば `"stopped"`
        3. それ以外は `"completed"`

        失敗は停止より優先する。停止の途中で起きた失敗も `"failed"` になる。`@optional` や `until="first_success"` で親に受け入れられた失敗は、最終的な `failed` に数えない。
        """

        title @= "Judging the outcome"
        level @= MUST

    class RESULT_004:
        """止まらなかったノードは `stuck` になり、`Result.stuck` に名前を載せ、警告 `SkeletonWarning` で知らせなければならない。警告は、結果を受け取ったスレッド(`honehone.run()` を呼んだスレッドや、最初に結果を返した `Run.wait()` を呼んだスレッド)で一度だけ出す。止まらなかったこと自体は `outcome` を変えない。スケルトンはスレッドを強制的に止めず、その責任は報告で終わる。"""

        title @= "Nodes that did not stop"
        level @= MUST

    class RESULT_005:
        """
        `NodeRecord` は、ノード一つの記録で、次のものを持たなければならない。

        | 名前 | 内容 |
        | --- | --- |
        | `state` | 最終的な状態 |
        | `errors` | そのノードで起きた例外の並び。`@retry` の呼び直し、`@optional` で受け入れた失敗、`until="first_success"` の負けた子の失敗も含む |
        | `calls` | ワーカーが呼ばれた回数(`@repeat` の各回と `@retry` の呼び直しを数える) |
        | `value` | ワーカーの最後の戻り値。グループと、一度も戻らなかったワーカーでは `None` |
        | `duration` | 始まってから終わるまでの秒数。始まらなかったノードでは `None` |
        """

        title @= "Node records"
        level @= MUST

    class RESULT_006:
        """`boot` と `cleanup` も名前を持つノードであり、`Result.nodes` に記録を持たなければならない。"""

        title @= "Boot and cleanup are recorded"
        level @= MUST

    class RESULT_007:
        """`Result.cleanup_errors` は、`cleanup` で起きた例外を、起きた順に持たなければならない。`cleanup` の失敗は `outcome` を `"failed"` にする(RESULT_003)。"""

        title @= "Errors in cleanup"
        level @= MUST
        related @= (LIFE_SPEC.LIFE_007,)

    class RESULT_008:
        """`Result.raise_if_failed()` は、`outcome` が `"failed"` なら `SkeletonFailed` を送出し、そうでなければ何もしてはならない。`SkeletonFailed` は `ExceptionGroup` で、最終的に `failed` になったノードの例外と `cleanup_errors` を含む。`except*` で例外の型ごとに受け取れる。"""

        title @= "Raising on failure"
        level @= MUST

    class RESULT_009:
        """`Result` と `NodeRecord` は、gpframe の型を含んではならない。例外は、ワーカーが送出したものをそのまま持つ。"""

        title @= "No gpframe types in results"
        level @= MUST_NOT
        related @= (CTRL_SPEC.CTRL_014,)

    class RESULT_010:
        """スレッドの起動と停止の要求の伝え方は honehone 自身が持ち、gpframe と同じ原則に従う。停止は協調的で、止まらなかったスレッドは強制的に止めずに報告し、スレッドはデーモンスレッドとして起動するのでプロセスの終了を妨げない。gpframe のフレームを使わないのは、service を一つずつ止めるなど、ノードごとに停止を要求する必要があるためである。利用者はこの仕組みを意識しなくてよく、`Result` だけを見ればよい。"""

        title @= "Relation to gpframe"
        level @= INFORMATIVE
