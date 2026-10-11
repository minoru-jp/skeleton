<!--
この文書は `shikumi-devdoc` によって生成された canonical document です。
Canonical source は `devdocs/canonical_sources/specification/__init__.py` です。
直接編集しないでください。

公開文書作成方針

- `devdocs/canonical_documents/` にある日本語 canonical document を公開工程の入力とする。
- 翻訳では意味、構造、情報量を維持し、内容を勝手に追加・削除・要約しない。
- canonical document に `shikumi-devdoc:translation-metadata` が含まれる場合は、その `preserve_spelling` 指定の用語の表記を変更しない。
- コード、Python 識別子、コマンド、ファイルパス、URL は、翻訳上の必要がない限り変更しない。
- このコメントブロックは published document には含めない。
- published document は canonical document から派生する公開成果物として扱い、内容の変更が必要な場合は canonical source または realization context へ戻して canonical document を再生成する。
-->

# Structure

スケルトンクラスと実装クラス、ワーカーとグループ、構造の検査に関する規則。

## STRUCT_001

スケルトンは、決まった形の処理を持つクラスである。形(どのワーカーが、どの順に、どう並んで動くか)はスケルトンクラスが決め、各ワーカーの中身は実装クラスがメソッドの上書きで埋める。

- **スケルトンクラス**: `Skeleton` を直接継承したクラス。ワーカー、グループ、`boot`、`cleanup` を定義する
- **実装クラス**: スケルトンクラスをさらに継承したクラス。ワーカーの中身を上書きするだけで、形は変えない

形と中身を分けることで、同じ形を中身違いで何度も使え、形はクラスの定義を読めば分かる。

title: Skeleton classes and implementation classes

level: INFORMATIVE

## STRUCT_002

ワーカー、グループ、`boot`、`cleanup` を定義できるのはスケルトンクラスだけでなければならない。実装クラスの中でグループを宣言した場合、またはワーカー・`boot`・`cleanup` を作るデコレータを使った場合、クラスの定義時に `SkeletonDefinitionError` を送出しなければならない。

title: Only skeleton classes define the shape

level: MUST

## STRUCT_003

実装クラスがワーカー・`boot`・`cleanup` と同じ名前のメソッドを定義すると、そのメソッドが中身を置き換える。置き換えたメソッドは、デコレータを付け直さなくても、元の所属と修飾をすべて引き継がなければならない。

title: Overriding keeps the role

level: MUST

## STRUCT_004

ワーカー・`boot`・`cleanup` のメソッドは `(self, ctx)` の形を取る。`ctx` は実行環境 `Context` である(EXEC_010)。`async def` のメソッドは、この版では扱わず、クラスの定義時に `SkeletonDefinitionError` を送出しなければならない。

title: Signature of workers

level: MUST

## STRUCT_005

グループはクラス属性として宣言する。親を持たないグループは `Sequence()` か `Parallel()` で作り、ほかのグループの中に入るグループは親のメソッド `sequence()` / `parallel()` で作る。

```python
class DevEnv(Skeleton):
    main = Sequence()
    services = main.parallel()  # main の中の、この位置に入る
```

title: Declaring groups

level: MUST

## STRUCT_006

グループはそのままデコレータとして使え、付けたメソッドをそのグループのワーカーにしなければならない。一つのメソッドは多くても一つのグループに属する。二つ以上のグループに入れた場合は、クラスの定義時に `SkeletonDefinitionError` を送出しなければならない。

title: Groups are decorators

level: MUST

## STRUCT_007

グループの中の子(ワーカーと子グループ)の順番は、クラス本体の中で定義された順でなければならない。ワーカーと子グループは区別しない。子グループの位置は、その属性を宣言した位置である。

title: Order of children

level: MUST

## STRUCT_008

親を持たないグループを**ルート**と呼ぶ。ルートは多くても一つでなければならず、二つ以上あればクラスの定義時に `SkeletonDefinitionError` を送出する。ルートがないスケルトンでは、本体は空で、`boot` と `cleanup` だけが動く。

title: The root group

level: MUST

## STRUCT_009

子を一つも持たないグループは、クラスの定義時に `SkeletonDefinitionError` を送出しなければならない。デコレータの付け忘れを早く知らせるためである。

title: Empty groups

level: MUST

## STRUCT_010

どのグループにも属さず、`boot` でも `cleanup` でもないメソッドは、普通のメソッドである。ワーカーから補助として呼べ、スケルトンは関与しない。

title: Plain methods

level: INFORMATIVE

## STRUCT_011

ワーカー・`boot`・`cleanup` を**ノード**と呼び、グループもノードである。ノードの名前は、メソッドならメソッド名、グループなら属性名とし、名前はクラスの中で一意である。操作(CTRL_004)や結果(RESULT_005)では、ノードを名前で指す。

報告(REPORT_003)には名前に加えて**経路**を付ける。経路は、ルートから自分までの名前を `.` でつないだものである(例: `main.services.db`)。

title: Node names and paths

level: MUST

## STRUCT_012

`Skeleton` は `abc.ABC` を継承する。`abc.abstractmethod` を付けたワーカーは、実装クラスで上書きしなければならない。上書きしていないクラスを生成すると、標準の仕組みにより `TypeError` になる。型検査器も、抽象クラスの生成として検出できる。

title: Required workers

level: MUST

## STRUCT_013

抽象でないワーカーの本体は、そのワーカーの既定の動作である。本体が `...` だけなら何もしない。何も上書きしない実装クラスでも、起動し、停止の要求で止まり、後始末まで走る。作りかけのまま形だけを先に動かせる。

title: Default behavior

level: INFORMATIVE

## STRUCT_014

間隔(`every`)を持たない `@repeat` のワーカーは、`abc.abstractmethod` にすべきである。何もしない本体のまま繰り返すと、CPU を回し続けるためである。

title: Repeated workers should be required

level: SHOULD

condition: スケルトンクラスを書くとき。

## STRUCT_015

構造の検査は、クラスの定義時(`__init_subclass__`)にすべて行わなければならない。実行を始めてから構造の誤りが見つかることはない。検査の対象は、この文書の規則のほか、組み合わせと修飾の矛盾(COMB_007、COMB_008、LIFE_014)と、実行の単位の矛盾(EXEC_003、EXEC_005)である。

title: Checking at definition time

level: MUST
