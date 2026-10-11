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

# honehone Specification

| Document | Summary |
| --- | --- |
| [Structure](structure.md) | スケルトンクラスと実装クラス、ワーカーとグループ、構造の検査に関する規則。 |
| [Combinators](combinators.md) | ノードの終わり方、Sequence と Parallel の終わり方、修飾に関する規則。 |
| [Lifecycle](lifecycle.md) | インスタンスと実行の関係、boot・本体・cleanup の流れ、凍結、service に関する規則。 |
| [Execution](execution.md) | 家のスレッド、既定の実行の単位、pinned と isolated、受け渡しの規則、Context に関する規則。 |
| [Control](control.md) | run と start、操作盤 Run、区切りでの一時停止、待ち合わせ、gpframe とのつなぎに関する規則。 |
| [Result](result.md) | Result、実行全体の判定、ノードの状態と記録、例外の送出に関する規則。 |
| [Report](report.md) | 報告の送信口、受け手の接続、報告の語彙と順序に関する規則。 |
