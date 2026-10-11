"""honehone の CHANGELOG の正本。"""

from shikumi_devdoc.fields.changelog import added, changed, removed, version
from shikumi_devdoc.norms.common import canonical_source


@canonical_source(
    "honehone 変更履歴",
    filename="CHANGELOG.md",
    merge_policy="forbidden",
    heading="identity",
)
class CHANGELOG:
    """`honehone` の版ごとの変更を記録する。`2.0.0` より前の版(`1.0.0`)は `skeleton` という名前だった作り直す前の旧実装で、その履歴はこの文書に含めない。"""

    class V2_0_0:
        """
        **設計から作り直した版で、`1.0.0` との後方互換性はまったくない。** `1.0.0` の API は何も残っておらず、移行の手段も用意しない。

        `1.0.0` は、一つの Routine を包んでイベント、状態、ログ、一時停止、結果の報告、コード生成と試行実行までを一度に抱え、実装が追いつかなかった。その後、受け渡しと実行の原則は gpframe に、報告の送信口は fport に切り出された。この版では、名前の原点である「既定の動作を持つ塊を、変えたい部分だけ上書きする」に立ち返り、形をデコレータで宣言するスケルトンクラスと、中身を上書きする実装クラスの組として作り直した。
        """

        version @= "2.0.0"

        added @= "`Skeleton` を直接継承したスケルトンクラスが形を宣言し、それを継承した実装クラスが中身を上書きする仕組みを追加した。形の誤りはクラスの定義時に `SkeletonDefinitionError` で知らせる。上書きの強制には標準の `abc.abstractmethod` を使う。"
        added @= "グループ `Sequence` / `Parallel` と終わり方 `until`(`all`、`first_success`、`first_done`)、`Parallel(lockstep=True)` を追加した。"
        added @= "修飾 `@repeat`、`@retry`、`@timeout`、`@optional`、`@service`、`@pinned`、`@isolated` を追加した。グループにも `modifiers` で `repeat`、`retry`、`timeout`、`optional` を付けられる。"
        added @= "`boot`、本体、`cleanup` の流れと、`boot` と対にした `cleanup`、本体の間のインスタンスの凍結を追加した。"
        added @= "準備の後も動き続ける `@service` と、ready になった順の逆順での停止を追加した。"
        added @= "構造から決まるスレッドの割り当てと、作ったスレッドに資源を縛る `ThreadBound` を追加した。"
        added @= "`honehone.run()`、`honehone.start()`、`honehone.control()` と、区切りで一時停止できる操作盤 `Run` を追加した。`run()` はメインスレッドで Ctrl+C を停止の要求に変える。"
        added @= "ワーカーが受け取る `Context`(`stopping`、`wait_stop()`、`on_stop()`、`checkpoint()`、`ready()`、`report()`)を追加した。"
        added @= "gpframe の型を含まない結果 `Result` と記録 `NodeRecord`、失敗をまとめる `SkeletonFailed`(`ExceptionGroup`)、止まらなかったノードの警告 `SkeletonWarning` を追加した。"
        added @= "fport の送信口による報告(`run.started`、`node.changed`、`node.called`、`worker.report`、`run.finished`)を追加した。"
        added @= "gpframe の `Channel` と `Shared` を `honehone.Channel` と `honehone.Shared` として再公開した。"
        added @= "gpframe の木に組み込むための `honehone.gpframe.routine` を追加した。"
        added @= "振る舞いの規則を Specification として追加した(Structure、Combinators、Lifecycle、Execution、Control、Result、Report の 7 文書)。テストは文書ごとにファイルを分け、各テストの名前に確かめる規則の識別子を入れた。"

        added @= "`examples/` に二つの例を追加した。形の使い回しと一時停止を見せる料理のタイマー `cooking.py` と、service と後始末の順序を見せる計測装置の制御 `instrument.py` である。"
        added @= "`examples/console.py` を追加した。裏で動く仕事を、別スレッドの入力のワーカーが受け付けるコマンドで操作する、操作盤としての CLI の例である。"

        added @= "すべての検査をまとめた `tools/check.py` と、GitHub Actions の CI(`ci.yml`)とリリース(`release.yml`)を追加した。リリースは CI と同じ検査を通したうえで、PyPI の Trusted Publishing で公開する。"
        added @= "英語の公開文書を、リポジトリのルート(README、STATUS、CHANGELOG)と `docs/specification/` に追加した。翻訳が canonical document と食い違っていないことを `scripts/published_docs.py` で確かめる。"
        changed @= "配布名と import 名を `skeleton` から `honehone` に変更した。`skeleton` は PyPI で別のプロジェクトが使っているためである。GitHub のリポジトリ名は `skeleton` のままである。"
        changed @= "対象の Python を `>=3.11` に変更した。"
        changed @= "実行時の依存パッケージに `gpframe` と `fport` を加えた。"

        removed @= "`make_skeleton_handle()` と `make_trial_skeleton_handle()`、ハンドルの API をすべて削除した。"
        removed @= "イベントハンドラ(`on_start` / `on_redo` / `on_end` / `on_cancel` / `on_close`)を削除した。観測は報告で、振る舞いの変更はメソッドの上書きで行う。"
        removed @= "3 チャンネルのメッセージ(`environment` / `event_message` / `routine_message`)と `Context.field` を削除した。設定は `__init__`、共有は `boot` で用意する `Channel` / `Shared` で扱う。"
        removed @= "シグナル(`Redo` / `Graceful` / `Resigned`)を削除した。繰り返しは `@repeat`、終わり方はノードの状態と `Result` で表す。"
        removed @= (
            "コード生成モード(`CodeTemplate`、`LinearLoop`)と試行実行を削除した。"
        )
