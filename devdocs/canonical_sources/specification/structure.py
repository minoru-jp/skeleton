"""スケルトンの構造(ワーカー、グループ、定義の規則)に関する仕様。"""

from shikumi_devdoc.fields.specification import (
    INFORMATIVE,
    MUST,
    SHOULD,
    condition,
    level,
)
from shikumi_devdoc.norms.common import canonical_source, summary
from shikumi_devdoc.norms.document import title


@summary("スケルトンクラスと実装クラス、ワーカーとグループ、構造の検査に関する規則。")
@canonical_source(
    "Structure",
    filename="structure.md",
    order=10,
    merge_policy="local",
    heading="identity",
)
class SPECIFICATION_PART:
    """スケルトンクラスと実装クラス、ワーカーとグループ、構造の検査に関する規則。"""

    class STRUCT_001:
        """
        スケルトンは、決まった形の処理を持つクラスである。形(どのワーカーが、どの順に、どう並んで動くか)はスケルトンクラスが決め、各ワーカーの中身は実装クラスがメソッドの上書きで埋める。

        - **スケルトンクラス**: `Skeleton` を直接継承したクラス。ワーカー、グループ、`boot`、`cleanup` を定義する
        - **実装クラス**: スケルトンクラスをさらに継承したクラス。ワーカーの中身を上書きするだけで、形は変えない

        形と中身を分けることで、同じ形を中身違いで何度も使え、形はクラスの定義を読めば分かる。
        """

        title @= "Skeleton classes and implementation classes"
        level @= INFORMATIVE

    class STRUCT_002:
        """ワーカー、グループ、`boot`、`cleanup` を定義できるのはスケルトンクラスだけでなければならない。実装クラスの中でグループを宣言した場合、またはワーカー・`boot`・`cleanup` を作るデコレータを使った場合、クラスの定義時に `SkeletonDefinitionError` を送出しなければならない。"""

        title @= "Only skeleton classes define the shape"
        level @= MUST

    class STRUCT_003:
        """実装クラスがワーカー・`boot`・`cleanup` と同じ名前のメソッドを定義すると、そのメソッドが中身を置き換える。置き換えたメソッドは、デコレータを付け直さなくても、元の所属と修飾をすべて引き継がなければならない。"""

        title @= "Overriding keeps the role"
        level @= MUST

    class STRUCT_004:
        """ワーカー・`boot`・`cleanup` のメソッドは `(self, ctx)` の形を取る。`ctx` は実行環境 `Context` である(EXEC_010)。`async def` のメソッドは、この版では扱わず、クラスの定義時に `SkeletonDefinitionError` を送出しなければならない。"""

        title @= "Signature of workers"
        level @= MUST

    class STRUCT_005:
        """
        グループはクラス属性として宣言する。親を持たないグループは `Sequence()` か `Parallel()` で作り、ほかのグループの中に入るグループは親のメソッド `sequence()` / `parallel()` で作る。

        ```python
        class DevEnv(Skeleton):
            main = Sequence()
            services = main.parallel()  # main の中の、この位置に入る
        ```
        """

        title @= "Declaring groups"
        level @= MUST

    class STRUCT_006:
        """グループはそのままデコレータとして使え、付けたメソッドをそのグループのワーカーにしなければならない。一つのメソッドは多くても一つのグループに属する。二つ以上のグループに入れた場合は、クラスの定義時に `SkeletonDefinitionError` を送出しなければならない。"""

        title @= "Groups are decorators"
        level @= MUST

    class STRUCT_007:
        """グループの中の子(ワーカーと子グループ)の順番は、クラス本体の中で定義された順でなければならない。ワーカーと子グループは区別しない。子グループの位置は、その属性を宣言した位置である。"""

        title @= "Order of children"
        level @= MUST

    class STRUCT_008:
        """親を持たないグループを**ルート**と呼ぶ。ルートは多くても一つでなければならず、二つ以上あればクラスの定義時に `SkeletonDefinitionError` を送出する。ルートがないスケルトンでは、本体は空で、`boot` と `cleanup` だけが動く。"""

        title @= "The root group"
        level @= MUST

    class STRUCT_009:
        """子を一つも持たないグループは、クラスの定義時に `SkeletonDefinitionError` を送出しなければならない。デコレータの付け忘れを早く知らせるためである。"""

        title @= "Empty groups"
        level @= MUST

    class STRUCT_010:
        """どのグループにも属さず、`boot` でも `cleanup` でもないメソッドは、普通のメソッドである。ワーカーから補助として呼べ、スケルトンは関与しない。"""

        title @= "Plain methods"
        level @= INFORMATIVE

    class STRUCT_011:
        """
        ワーカー・`boot`・`cleanup` を**ノード**と呼び、グループもノードである。ノードの名前は、メソッドならメソッド名、グループなら属性名とし、名前はクラスの中で一意である。操作(CTRL_004)や結果(RESULT_005)では、ノードを名前で指す。

        報告(REPORT_003)には名前に加えて**経路**を付ける。経路は、ルートから自分までの名前を `.` でつないだものである(例: `main.services.db`)。
        """

        title @= "Node names and paths"
        level @= MUST

    class STRUCT_012:
        """`Skeleton` は `abc.ABC` を継承する。`abc.abstractmethod` を付けたワーカーは、実装クラスで上書きしなければならない。上書きしていないクラスを生成すると、標準の仕組みにより `TypeError` になる。型検査器も、抽象クラスの生成として検出できる。"""

        title @= "Required workers"
        level @= MUST

    class STRUCT_013:
        """抽象でないワーカーの本体は、そのワーカーの既定の動作である。本体が `...` だけなら何もしない。何も上書きしない実装クラスでも、起動し、停止の要求で止まり、後始末まで走る。作りかけのまま形だけを先に動かせる。"""

        title @= "Default behavior"
        level @= INFORMATIVE

    class STRUCT_014:
        """間隔(`every`)を持たない `@repeat` のワーカーは、`abc.abstractmethod` にすべきである。何もしない本体のまま繰り返すと、CPU を回し続けるためである。"""

        title @= "Repeated workers should be required"
        level @= SHOULD
        condition @= "スケルトンクラスを書くとき。"

    class STRUCT_015:
        """構造の検査は、クラスの定義時(`__init_subclass__`)にすべて行わなければならない。実行を始めてから構造の誤りが見つかることはない。検査の対象は、この文書の規則のほか、組み合わせと修飾の矛盾(COMB_007、COMB_008、LIFE_014)と、実行の単位の矛盾(EXEC_003、EXEC_005)である。"""

        title @= "Checking at definition time"
        level @= MUST
