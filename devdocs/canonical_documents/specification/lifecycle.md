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

# Lifecycle

インスタンスと実行の関係、boot・本体・cleanup の流れ、凍結、service に関する規則。

## LIFE_001

インスタンス一つは、一回の実行に対応する。実行を始めたインスタンスをもう一度実行しようとした場合は、`SkeletonStateError` を送出しなければならない。何度も実行するには、インスタンスを作り直す。

title: One instance, one run

level: MUST

## LIFE_002

`__init__` は設定値を受け取るだけにすべきで、接続やファイルなどの資源を取るべきではない。`__init__` は実行の外で動くため、停止の要求も `cleanup` も効かない。資源は `boot` で用意する。

title: What __init__ is for

level: SHOULD

condition: スケルトンクラスや実装クラスに `__init__` を書くとき。

## LIFE_003

一回の実行は、次の順に進まなければならない。

1. `boot` を定義順に一つずつ
2. 本体(ルートのグループ)
3. `cleanup` を定義の逆順に一つずつ
4. 結果の確定(RESULT_001)

`boot` と `cleanup` は家のスレッドで動く(EXEC_002)。

title: The flow of a run

level: MUST

## LIFE_004

`boot` が `failed` で終わったら、残りの `boot` と本体のノードをすべて `skipped` とし、`cleanup` へ進まなければならない。`boot` の途中で停止を要求された場合も同じく、残りを `skipped` として `cleanup` へ進む。

title: When boot fails

level: MUST

## LIFE_005

本体が動いている間は、インスタンスの属性への代入と削除を拒み、`FrozenSkeletonError` を送出しなければならない。`boot` と `cleanup` の間は代入できる。どちらも家のスレッドで一つずつ動き、ほかのワーカーと並行しないためである。

title: The instance is frozen while the body runs

level: MUST

## LIFE_006

本体のワーカー同士で値をやり取りするには、`boot` で `Channel` や `Shared` を用意して属性に置き、それを通して受け渡す。属性そのものを書き換えることはできない(LIFE_005)ので、共有はかならず明示的な道具を通る。

title: Sharing between workers

level: INFORMATIVE

## LIFE_007

`cleanup` は、本体の終わり方(`succeeded`、`failed`、`stopped`、`boot` の失敗による `skipped`)によらず走らなければならない。定義の逆順に一つずつ動かし、一つが `failed` で終わっても残りを走らせる。`cleanup` の例外は `Result.cleanup_errors` に集める(RESULT_007)。

title: Cleanup always runs

level: MUST

## LIFE_008

`cleanup` は、特定の `boot` と対にできる。`@cleanup(of=connect)` のように対にした `cleanup` は、対応する `boot` が `succeeded` で終わった場合だけ走らなければならない。対にしない `@cleanup` は常に走る。

```python
@boot
def connect(self, ctx): ...

@cleanup(of=connect)
def disconnect(self, ctx): ...  # connect が成功したときだけ走る
```

`@boot` と `@cleanup` は関数をそのまま返さなければならない。実装クラスが `boot` や `cleanup` の中身を普通のメソッドとして上書きでき、型検査器もそれを普通のメソッドの上書きとして扱えるようにするためである。

title: Pairing cleanup with boot

level: MUST

## LIFE_009

`cleanup` の中では、`ctx.stopping` は偽でなければならない。後始末が、それを引き起こした停止の要求によって中断されないためである。ただし、実行に対して二度目の停止の要求があった場合は、動いている `cleanup` に停止を要求し、残りの `cleanup` を `skipped` とする。

title: Cleanup is not interrupted by the first stop

level: MUST

## LIFE_010

`@service` を付けたワーカーは、準備ができた後も動き続ける部品(サーバー、装置の監視など)である。ワーカーが `ctx.ready()` を呼んだ時点で、そのノードは `ready` になる。

- 親が `Sequence` なら、`ready` になった時点で次の子へ進む。service 自体は動き続ける
- 親が `Parallel` なら、`ready` を完了とみなして終わり方を判定する
- `ctx.ready()` を呼ばずに戻った場合は、戻った時点で `ready` になり、続けて `succeeded` になる
- `ready` になる前に `failed` で終わった場合は、普通のワーカーと同じく `failed` になる

title: Services

level: MUST

## LIFE_011

`ready` になった service は、本体の残り(service 以外のノード)がすべて終わった時点で、スケルトンが止める。この停止による終わりは、service を `succeeded` としなければならない。予定された終わり方であり、停止の要求による `stopped` とは区別する。

title: When services are stopped

level: MUST

## LIFE_012

`ready` になった後の service が `failed` で終わった場合、本体全体の失敗として扱い、本体に停止を要求しなければならない。

title: A service that fails after ready

level: MUST

## LIFE_013

service を止めるときは、`ready` になった順の逆順に一つずつ停止を要求し、それが終わるのを待ってから次へ進まなければならない。後に用意したものから先に片付けるためである(API を止めてから DB を止める)。service でないノードは、同時に停止を要求する。

title: Order of stopping services

level: MUST

## LIFE_014

`@service` には、`@optional` と `@isolated` のほかの修飾を合わせて付けられない。`@repeat`、`@retry`、`@timeout`、`@pinned` を合わせて付けた場合と、`Parallel(lockstep=True)` の子に `@service` を付けた場合は、クラスの定義時に `SkeletonDefinitionError` を送出しなければならない。service は専用のスレッドで動き(EXEC_002)、準備の後も動き続けるため、これらの修飾とは意味が合わない。

title: Conflicting service declarations

level: MUST

related: [STRUCT_015](structure.md#struct_015), [COMB_008](combinators.md#comb_008)

## LIFE_015

service への停止の要求は、親のグループからは伝わらない。実行全体に停止が要求された場合も、まず本体の service でないノードが止まり、本体が終わってから、service を LIFE_013 の順に止める。ただし、`ready` になる前の service は、待っている親が止められた時点で止める(準備の途中で本体の停止を待たせないため)。

title: Services are stopped after the body

level: MUST
