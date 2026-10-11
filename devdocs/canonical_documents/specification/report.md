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

# Report

報告の送信口、受け手の接続、報告の語彙と順序に関する規則。

## REPORT_001

実行の出来事は、fport の送信口 `Port` を通して報告しなければならない。報告は実行の振る舞いを変えない。受け手が例外を送出しても実行には伝わらず、受け手が接続されていなくても実行は同じように進む。観測は報告、振る舞いの変更はメソッドの上書き、と役割を分ける。

title: Reporting does not change behavior

level: MUST

## REPORT_002

`honehone.run()`、`honehone.start()`、`honehone.gpframe.routine` に渡した受け手 `listener` は、最初の報告より前に接続し、最後の報告の後に外さなければならない。実行の途中から接続して報告を取りこぼすことはない。

title: Connecting the listener

level: MUST

related: [CTRL_001](control.md#ctrl_001), [CTRL_002](control.md#ctrl_002), [CTRL_014](control.md#ctrl_014)

## REPORT_003

スケルトンが送る報告は次のものでなければならない。受け手は fport の約束どおり `listener(tag, *args, **kwargs)` の形で受け取る。

| タグ | 引数 | いつ |
| --- | --- | --- |
| `run.started` | なし | 実行を始めたとき |
| `node.changed` | `name=`、`path=`、`state=`、`error=` | ノードの状態が変わるたび。`error` は `failed` のときの例外、それ以外は `None` |
| `node.called` | `name=`、`path=`、`count=` | ワーカーの 1 回分の呼び出しが終わるたび。`count` はそれまでの回数 |
| `run.finished` | `result=` | 結果が確定したとき。最後の報告 |

title: Report vocabulary

level: MUST

related: [RESULT_002](result.md#result_002)

## REPORT_004

報告の語彙(タグ、引数の名前、状態の名前)は公開の約束である。変更は後方互換性のない変更として扱わなければならない。進捗表示やログ画面などの受け手が、この語彙に依存するためである。

title: The vocabulary is a public contract

level: MUST

## REPORT_005

一つのノードの報告は、状態が変わった順に届かなければならない。異なるスレッドで動くノードの間の報告の順序は定めない。報告は、それを送ったスレッドで、その場で受け手に渡る(fport の約束)。

title: Order of reports

level: MUST

## REPORT_006

ワーカーは `ctx.report(*args, **kwargs)` で自分の報告を送れる。この報告はタグ `worker.report` で、最初の位置引数に `name` を置き、続けて `ctx.report()` に渡した引数をそのまま送らなければならない。進捗の割合など、ワーカーにしか分からない情報を受け手に伝えるためのものである。

title: Reports from workers

level: MUST

## REPORT_007

報告と `Run.state()` は、同じ状態の変化の二つの見え方である。報告は変化を押し出し、`Run.state()` は今の状態を引き出す。どちらから見ても、状態の変化の順序は食い違わない。

title: Reports and Run.state

level: INFORMATIVE
