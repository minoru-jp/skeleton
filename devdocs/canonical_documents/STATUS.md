<!--
この文書は `shikumi-devdoc` によって生成された canonical document です。
Canonical source は `devdocs/canonical_sources/status/canonical.py` です。
直接編集しないでください。

公開文書作成方針

- `devdocs/canonical_documents/` にある日本語 canonical document を公開工程の入力とする。
- 翻訳では意味、構造、情報量を維持し、内容を勝手に追加・削除・要約しない。
- canonical document に `shikumi-devdoc:translation-metadata` が含まれる場合は、その `preserve_spelling` 指定の用語の表記を変更しない。
- コード、Python 識別子、コマンド、ファイルパス、URL は、翻訳上の必要がない限り変更しない。
- このコメントブロックは published document には含めない。
- published document は canonical document から派生する公開成果物として扱い、内容の変更が必要な場合は canonical source または realization context へ戻して canonical document を再生成する。
-->

# honehone Project Status

`honehone` の現在の状態と、現在から見た今後の方向を記述する。
過去に実際に起きた変更は CHANGELOG が担当する。

## STATUS_001

現在の開発段階は Alpha。現在のバージョンは `2.0.0` で、設計から作り直した最初の版である。旧実装 `1.0.0` とは互換性がない。

title: Development stage

## STATUS_002

対象の Python バージョン範囲は `>=3.11`。`SkeletonFailed` が標準の `ExceptionGroup` を使うためである。

実行時の依存パッケージは次の二つで、どちらも意図した依存である。旧実装が自分で抱えていた受け渡しと報告を、それぞれの専用のパッケージに任せるための作り直しだからである。

- `gpframe`: ワーカーの間の受け渡しの道具(`Channel`、`Shared`)を借り、`honehone.gpframe` で gpframe の木に組み込む。スレッドの起動と停止の要求の伝え方は、gpframe と同じ原則で honehone 自身が持つ(RESULT_010)
- `fport`: 実行の報告の送信口

title: Supported Python and dependencies

## STATUS_003

提供している機能は次のとおり。

- `Skeleton` を直接継承したスケルトンクラスによる形の宣言と、それを継承した実装クラスによる中身の上書き。形の誤りはクラスの定義時に検出する
- グループ `Sequence` / `Parallel` と終わり方 `until`(`all`、`first_success`、`first_done`)、`Parallel(lockstep=True)`
- 修飾 `@repeat`、`@retry`、`@timeout`、`@optional`、`@service`、`@pinned`、`@isolated`
- 上書きの強制に標準の `abc.abstractmethod` を使うこと
- `boot`、本体、`cleanup` の流れ、`boot` と対にした `cleanup`、本体の間の凍結
- 構造から決まるスレッドの割り当てと、`ThreadBound` による資源の縛り
- `honehone.run()`(Ctrl+C を停止の要求に変える)、`honehone.start()` と操作盤 `Run`(`pause`、`resume`、`stop`、`wait`、`wait_until`、`state`)、`honehone.control()`
- gpframe の型を含まない結果 `Result` と、fport による報告
- gpframe の木に組み込むための `honehone.gpframe.routine`

実行はスレッド(同期版)だけを扱う。

title: Scope

## STATUS_004

振る舞いの規則は Specification を正本とし、`devdocs/canonical_sources/specification/` に置く。テストは Specification の文書ごとにファイルを分け(`tests/test_structure.py`、`test_combinators.py`、`test_lifecycle.py`、`test_execution.py`、`test_control.py`、`test_result_report.py`、`test_gpframe.py`、文書をまたぐ規則の `test_cross_cutting.py`)、各テストの名前に確かめる規則の識別子を入れている。例は `tests/test_examples.py` で確かめる。gpframe との組み合わせは gpframe そのものを使って確かめる。

`tests/test_devdocs.py` は、canonical document が正本から生成し直したものと一致していること、README のコード例が実際に動くこと、文書に注入するバージョンが `pyproject.toml` と一致していることを確かめる。

pytest は警告をすべてエラーとして扱う。

title: Specification and tests

## STATUS_005

旧実装との関係は次のとおり。旧実装の実装は引き継がず、考え方の一部だけを引き継ぐ。

- 旧実装の EventHandler は、観測と振る舞いの変更(`on_end` が真なら Redo など)を兼ねていた。新しい設計では、観測を fport の報告に、振る舞いの変更をメソッドの上書きに分けた
- 旧実装の Redo は、`@repeat` としてループの外側をスケルトンが持つ形になった
- 旧実装の二階建ての一時停止(driver からの super pause と、Routine 自身の pause)は、区切りでの一時停止(`Run.pause()`)と、ワーカー自身の `ctx.checkpoint()` に整理した。ループと手順の移り目をスケルトンが持つので、ワーカーが協力しなくても区切りで止まる
- 旧実装の `Context.field` は、`boot` で用意して凍結されるインスタンスの属性になった
- 旧実装のコード生成モードと試行実行(`exec`)は引き継がない。形は宣言そのものであり、生成する必要がないためである

title: Relation to the old implementation

## STATUS_006

`examples/` には三つの例を置いている。どれも標準ライブラリだけで動く。

- `cooking.py`: 料理のタイマー。一つのレシピの形を二つのレシピが使い回すこと、`ctx.checkpoint()` による作業の途中での一時停止、報告の受け手による表示を見せる
- `instrument.py`: 計測装置の制御。service、`boot` と対の `cleanup`、`@pinned` と `ThreadBound` による sqlite への記録、正常終了・失敗・Ctrl+C のどの場合も後始末の順序が守られることを見せる
- `console.py`: 操作盤としての CLI。裏で動く仕事を、入力のワーカーが受け付けるコマンドで操作する。Ctrl+C を受ける管理役(家のスレッド)と、`@isolated` で別スレッドに置いた入力のワーカーを分けている

`tests/test_examples.py` は、例が書いてあるとおりに動くことを確かめる。料理のタイマーでは一時停止の間に進まないこと、計測装置では Ctrl+C で止めたときにも記録を締め、見張りを止めてから切断することを確かめている。CLI では、疑似端末の上で実際に例を動かし、入力待ちの間の Ctrl+C で終わることも確かめている。

二つの例を書く中で、報告の受け手の作り方について次のことが分かった。報告は送ったワーカーのスレッドでその場で届くので、複数のワーカーから報告を受けて表示する受け手は、表示が混ざらないよう自分でロックを取る必要がある。どの例の受け手もそうしている。

CLI の例を書く中で、入力の待ちについて次のように整理した。`input()` は停止の要求で待ちを解けないが、入力中は人の番なので、打ち終えるまで待つのが自然な振る舞いである。これは「呼び出し中の 1 回分は中断しない」(CTRL_006)の素直な例であり、ライブラリの側に手当ては要らない。Ctrl+C の `KeyboardInterrupt` はメインスレッドにしか出ないが、Ctrl+C を受ける管理役(家のスレッド)と入力のワーカーを分けておけば、`KeyboardInterrupt` は出ず、Ctrl+C は停止の要求として区切りで効く。入力のワーカーは、`input()` が戻った直後に `ctx.stopping` を確かめ、止まる途中に打たれた行は実行しない。

title: Examples

## STATUS_007

配布名と import 名は `honehone`(骨々)である。GitHub のリポジトリ名は、旧実装の名前を受け継いで `skeleton` のままとする。

旧実装の名前 `skeleton` は、PyPI で別のプロジェクトがすでに使っているため、配布名には使えない。PyPI は、`.` `_` `-` を除き、`l` と `i` を `1` に、`o` を `0` に置き換えた名前が既存のプロジェクトと一致する名前も「似すぎた名前」として拒む。import 名を配布名にそろえたのは、`skeleton` が一般的な名前で、ほかのパッケージの import 名とぶつかりやすいためである。基底クラスの名前 `Skeleton` と、文書の中の「スケルトン」という呼び方は、この仕組みの考え方を表す言葉として残している。

title: Name

## STATUS_008

すべての検査は `tools/check.py` にまとめている。`docs`(canonical document が最新で、英語の公開文書が canonical document と食い違っていない)、`format`、`lint`、`types`、`types-tests`、`tests`、`dist`(sdist と wheel を作り、`twine check --strict`、中身の検査、きれいな venv に依存パッケージごと入れての動作確認)の七つである。`python tools/check.py` ですべてを、名前を並べれば一部だけを走らせる。検査に使う道具の版は `pyproject.toml` の extra で固定している(`dev` がすべてを含む)。

GitHub Actions のワークフローは二つある。

- `ci.yml`: プッシュとプルリクエストのたびに、Python 3.11、3.12、3.13 で `python tools/check.py` を走らせる
- `release.yml`: GitHub で Release を公開すると、まず `ci.yml` をそのまま呼んで同じ検査を通す。続いて `python tools/check.py dist --tag <タグ>` で配布物を作って確かめ(タグが `v<version>` と一致することも確かめる)、PyPI の Trusted Publishing で公開する。API トークンは使わない

Trusted Publishing には、PyPI 側で、このリポジトリ(`minoru-jp/skeleton`)、ワークフロー `release.yml`、環境 `pypi` を、プロジェクト `honehone` の Trusted Publisher として登録しておく必要がある。

title: Checks, CI and release

## STATUS_009

静的解析は、`ruff format --check .`、`ruff check .`、BasedPyright の二つの設定のどれでも問題がない。

- Ruff は 0.16.10 に固定し、対象の版は Python 3.11 である。生成した canonical document は整形の対象から外している。
- BasedPyright 1.40.2 で、`src/honehone`、`scripts`、`tools` を `recommended` で検査し、0 errors / 0 warnings である。止めている診断は二つだけで、`typing.override` が Python 3.12 からのため `reportImplicitOverride` を、パッケージの中で互いの内部状態を扱うため `reportPrivateUsage` を止めている。
- `tests/pyrightconfig.json` で、テスト、例、文書の正本を利用側として `standard` で検査し、0 errors / 0 warnings である。例を利用側として検査するのは、利用者が書くスケルトンクラスに、ライブラリ向けの厳しい規則(クラス属性の型注釈など)を求めないためである。

明示的な `Any` は、`repeat(until=...)` に渡す関数の引数の型だけに残している。利用者が書く `lambda value: value >= 3` を型検査で通すためである。実行時の意味を保つための局所的な抑制(`pyright: ignore`)には、そばに理由を書いている。

型検査を通す中で、`@boot` のメソッドを実装クラスで上書きすると、型検査器が両立しない上書きとして報告することが分かった。`@boot` が記述子を返していたためである。`@boot` と `@cleanup` は関数をそのまま返すように変え、`boot` との対は `@cleanup(of=connect)` で書くようにした(LIFE_008)。

title: Static analysis

## STATUS_010

英語の公開文書は、日本語の canonical document を翻訳して作る。README、STATUS、CHANGELOG はリポジトリのルートに、Specification は `docs/specification/` に置く。翻訳そのものは自動化していない。`scripts/published_docs.py` が次のことを機械的に確かめる(`tools/check.py docs` に含まれる)。

- すべての canonical document に公開文書があり、余分な公開文書がない
- 公開文書の先頭の印が、いまの canonical document の SHA-256 と一致する。canonical document が変われば、翻訳し直して `python scripts/published_docs.py stamp <公開文書>` で印を付け直すまで失敗する
- Python のコード例が、コメントと docstring を除いて canonical document と同じである
- 仕様の規則の見出しが、同じ順に同じだけある
- リンクの先が実在する

title: Published documents

## NOTICE_001

非同期版を、gpframe.aio の上に、同期版と型を共有しない独立した系統として作ることを検討している。

title: Async version

kind: General

condition: 同期版の API が固まった後。

## NOTICE_002

手順と対になる取り消し(`.undo`、補償)を検討している。後の手順が失敗したとき、済んだ手順を逆順に取り消す。どの時点までに成功した手順を取り消すかと、取り消し自体が失敗した場合の報告を決める必要がある。

title: Undo (compensation)

kind: General

condition: 使い道から必要性を確かめた後。

## NOTICE_003

本体の中で、前のワーカーの戻り値を後のワーカーが受け取る仕組みを検討している。現在は、本体の中の受け渡しは `boot` で用意した `Channel` / `Shared` を通し、外からは `Result.nodes[...].value` で最後の戻り値を見られる。

title: Passing results between workers

kind: General

condition: 使い道から必要性を確かめた後。

## NOTICE_004

項目ごとに同じ手順を並行に回す `Each`(並行数の上限つき)と、条件で子を一つだけ選ぶ `Choice` を検討している。CLI の例では、コマンドの振り分けは一つのワーカーの中の辞書で素直に書け、形として表す必要はなかった。`Choice` が要るのは、選ぶ対象そのものが止め方や後始末を持つ手順である場面だと考えている。

title: Each and Choice

kind: General

condition: 使い道から必要性を確かめた後。

## NOTICE_005

一時停止中に `@timeout` と `@repeat(every=)` の時計を進めるか止めるかは、まだ決めていない。現在の実装では、時計は一時停止中も進む。

title: Clocks while paused

kind: General

condition: 使い道から必要性を確かめた後。

## NOTICE_006

失敗した子を再起動する方針(Erlang の supervisor の one_for_one、one_for_all などに当たるもの)は扱わない。

title: No restart strategies

kind: General

condition: 使い道から必要性が確かめられるまで。

## NOTICE_007

検証(ドッグフーディング)として、gpframe の `tools/devwatch.py` をスケルトンで書き直し、gpframe で直接書いたものと比べることを予定している。形が宣言として読めるか、配線のコードが消えるかを確かめる。

title: Dogfooding plan

kind: General

condition: 同期版の API が固まった後。

## NOTICE_008

gpframe と fport にならい、テストで守る約束を `shikumi-contrace` の契約として `contract/` に置き、公開 API の形を Protocol として置くことを予定している。

title: Contracts

kind: General

condition: 同期版の API が固まった後。
