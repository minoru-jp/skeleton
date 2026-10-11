"""実行の報告(fport の送信口)に関する仕様。"""

from shikumi_devdoc.fields.specification import (
    INFORMATIVE,
    MUST,
    level,
    related,
)
from shikumi_devdoc.norms.common import canonical_source, summary
from shikumi_devdoc.norms.document import title

from devdocs.canonical_sources.specification.control import (
    SPECIFICATION_PART as CTRL_SPEC,
)
from devdocs.canonical_sources.specification.result import (
    SPECIFICATION_PART as RESULT_SPEC,
)


@summary("報告の送信口、受け手の接続、報告の語彙と順序に関する規則。")
@canonical_source(
    "Report",
    filename="report.md",
    order=70,
    merge_policy="local",
    heading="identity",
)
class SPECIFICATION_PART:
    """報告の送信口、受け手の接続、報告の語彙と順序に関する規則。"""

    class REPORT_001:
        """実行の出来事は、fport の送信口 `Port` を通して報告しなければならない。報告は実行の振る舞いを変えない。受け手が例外を送出しても実行には伝わらず、受け手が接続されていなくても実行は同じように進む。観測は報告、振る舞いの変更はメソッドの上書き、と役割を分ける。"""

        title @= "Reporting does not change behavior"
        level @= MUST

    class REPORT_002:
        """`honehone.run()`、`honehone.start()`、`honehone.gpframe.routine` に渡した受け手 `listener` は、最初の報告より前に接続し、最後の報告の後に外さなければならない。実行の途中から接続して報告を取りこぼすことはない。"""

        title @= "Connecting the listener"
        level @= MUST
        related @= (CTRL_SPEC.CTRL_001, CTRL_SPEC.CTRL_002, CTRL_SPEC.CTRL_014)

    class REPORT_003:
        """
        スケルトンが送る報告は次のものでなければならない。受け手は fport の約束どおり `listener(tag, *args, **kwargs)` の形で受け取る。

        | タグ | 引数 | いつ |
        | --- | --- | --- |
        | `run.started` | なし | 実行を始めたとき |
        | `node.changed` | `name=`、`path=`、`state=`、`error=` | ノードの状態が変わるたび。`error` は `failed` のときの例外、それ以外は `None` |
        | `node.called` | `name=`、`path=`、`count=` | ワーカーの 1 回分の呼び出しが終わるたび。`count` はそれまでの回数 |
        | `run.finished` | `result=` | 結果が確定したとき。最後の報告 |
        """

        title @= "Report vocabulary"
        level @= MUST
        related @= (RESULT_SPEC.RESULT_002,)

    class REPORT_004:
        """報告の語彙(タグ、引数の名前、状態の名前)は公開の約束である。変更は後方互換性のない変更として扱わなければならない。進捗表示やログ画面などの受け手が、この語彙に依存するためである。"""

        title @= "The vocabulary is a public contract"
        level @= MUST

    class REPORT_005:
        """一つのノードの報告は、状態が変わった順に届かなければならない。異なるスレッドで動くノードの間の報告の順序は定めない。報告は、それを送ったスレッドで、その場で受け手に渡る(fport の約束)。"""

        title @= "Order of reports"
        level @= MUST

    class REPORT_006:
        """ワーカーは `ctx.report(*args, **kwargs)` で自分の報告を送れる。この報告はタグ `worker.report` で、最初の位置引数に `name` を置き、続けて `ctx.report()` に渡した引数をそのまま送らなければならない。進捗の割合など、ワーカーにしか分からない情報を受け手に伝えるためのものである。"""

        title @= "Reports from workers"
        level @= MUST

    class REPORT_007:
        """報告と `Run.state()` は、同じ状態の変化の二つの見え方である。報告は変化を押し出し、`Run.state()` は今の状態を引き出す。どちらから見ても、状態の変化の順序は食い違わない。"""

        title @= "Reports and Run.state"
        level @= INFORMATIVE
