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

# Execution

家のスレッド、既定の実行の単位、pinned と isolated、受け渡しの規則、Context に関する規則。

## EXEC_001

ワーカーはスレッドで動く。一回の実行には一つの**家のスレッド**がある。`honehone.run()` では呼び出したスレッドが、`honehone.start()` では実行のために用意したスレッドが家のスレッドになる(CTRL_001、CTRL_002)。

どのワーカーをどのスレッドで動かすかは、利用者が葉ごとに選ぶのではなく、構造と、葉に付けた制約(`@pinned`、`@isolated`)から決まる。

title: Threads and the home thread

level: INFORMATIVE

## EXEC_002

既定では、次の規則でスレッドを決めなければならない。

- 順に動くもの(`boot`、`cleanup`、`Sequence` の子、`@repeat` の各回、`@retry` の呼び直し)は、親と同じスレッドで呼ぶ
- `Parallel` の子は、それぞれ専用のスレッドで動かす。ただし EXEC_003 により家のスレッドを受け継ぐ子は除く
- `@service` のワーカーは、親が `Sequence` でも、かならず専用のスレッドで動かす。準備の後も動き続け、そのあいだ親は次の子へ進むためである

並行が必要な所でだけスレッドを立て、順に動く所ではスレッドを増やさない。

title: Default threading

level: MUST

## EXEC_003

`@pinned` を付けたワーカーは、かならず家のスレッドで動かなければならない。sqlite の接続のように、スレッドをまたいで使えない資源を扱うワーカーのためのものである。

家のスレッドは、ルートから `@pinned` のワーカーまでの道に沿って受け継がれる。`Parallel` は、`@pinned` を子孫に含む子を家のスレッドで動かし、ほかの子を専用のスレッドで動かす。同じ `Parallel` の二つ以上の子が `@pinned` を子孫に含む場合は、クラスの定義時に `SkeletonDefinitionError` を送出しなければならない。

title: Pinned workers

level: MUST

related: [STRUCT_015](structure.md#struct_015)

## EXEC_004

`@isolated` を付けたワーカーは、`Sequence` の子であっても、かならず専用のスレッドで動かなければならない。止まらなかった場合、親はそれを止まらなかったノードとして見切り(RESULT_004)、先へ進む。固まる恐れのある処理のためのものである。

title: Isolated workers

level: MUST

## EXEC_005

一つのワーカーに `@pinned` と `@isolated` を両方付けた場合は、クラスの定義時に `SkeletonDefinitionError` を送出しなければならない。

title: Pinned and isolated conflict

level: MUST

related: [STRUCT_015](structure.md#struct_015)

## EXEC_006

親と同じスレッドで呼ばれたワーカーが戻らない場合、そのスレッドで後に続く処理(`cleanup` を含む)も進めない。スケルトンはこれを見切れない。止まらないおそれのある処理には `@isolated` を付ける。

title: Workers on a shared thread cannot be abandoned

level: INFORMATIVE

## EXEC_007

`honehone.ThreadBound(obj)` は、`obj` を包んで、作ったスレッドに縛る入れ物である。入れ物の `get()` は、作ったスレッドから呼ばれたときだけ `obj` を返し、ほかのスレッドから呼ばれたら `ThreadAffinityError` を送出しなければならない。`boot` の中で作れば、家のスレッドに縛られる。`boot` で `self.db = honehone.ThreadBound(sqlite3.connect(path))` のように使う。

title: Holding thread-bound resources

level: MUST

## EXEC_008

ワーカーの間の受け渡しは、次の規則に従う。

- スレッドをまたぐやり取りは `Channel` か `Shared` を通す
- スレッドに縛られた資源は `honehone.ThreadBound` で包み、`@pinned` のワーカーから使う
- インスタンスの属性に書けるのは `boot` と `cleanup` の間だけである(LIFE_005)

同じスレッドで順に動くワーカー同士は、これらの規則の範囲で自由にやり取りできる。

title: Rules for passing data

level: INFORMATIVE

related: [LIFE_005](lifecycle.md#life_005), [LIFE_006](lifecycle.md#life_006)

## EXEC_009

`honehone` は、値の受け渡しの道具 `Channel` と、型の固定された共有セル `Shared` を、`honehone.Channel` と `honehone.Shared` として公開しなければならない。ワーカーの `ctx` は、`Channel.receive(ctx)` など、これらの待ちの引数にそのまま渡せる。

title: Channel and Shared

level: MUST

## EXEC_010

ワーカー・`boot`・`cleanup` が受け取る `Context` は、次のものを持たなければならない。

| 名前 | 内容 |
| --- | --- |
| `name` | ノードの名前 |
| `stopping` | 停止が要求されていれば真(`cleanup` では LIFE_009 による) |
| `wait_stop(timeout)` | 停止の要求まで待つ。要求があれば真を返す |
| `on_stop(callback)` | 停止の要求で呼ばれるコールバックを登録する |
| `checkpoint()` | 一時停止が要求されていれば、再開まで待つ(CTRL_007) |
| `ready()` | service が準備できたことを知らせる(LIFE_010)。service 以外では `SkeletonStateError` |
| `report(*args, **kwargs)` | ワーカー自身の報告を送る(REPORT_006) |

title: Context

level: MUST

## EXEC_011

`ctx.on_stop(callback)` で登録したコールバックは、停止が要求されたときに、要求したスレッドでもワーカーのスレッドでもない別のスレッドで、一度だけ呼ばれなければならない。すでに停止が要求されているときに登録したコールバックは、登録の直後に同じ方法で呼ぶ。返る `StopHandle` の `cancel()` の後と、その呼び出しが終わった後は、まだ呼ぶことが決まっていないコールバックを呼ばない。呼び出しが終わる前に停止が要求されて呼ぶことが決まったコールバックは、呼び出しが戻った後でも呼び、呼び出しはその終わりを待ってから終わる(待つ上限は `stop_timeout`)。コールバックが例外を送出した場合は、その呼び出しを `failed` とし、例外を記録に残す。

title: Stop callbacks

level: MUST
