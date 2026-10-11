<!--
この文書は `shikumi-devdoc` によって生成された canonical document です。
Canonical source は `devdocs/canonical_sources/readme/canonical.py` です。
直接編集しないでください。

公開文書作成方針

- `devdocs/canonical_documents/` にある日本語 canonical document を公開工程の入力とする。
- 翻訳では意味、構造、情報量を維持し、内容を勝手に追加・削除・要約しない。
- canonical document に `shikumi-devdoc:translation-metadata` が含まれる場合は、その `preserve_spelling` 指定の用語の表記を変更しない。
- コード、Python 識別子、コマンド、ファイルパス、URL は、翻訳上の必要がない限り変更しない。
- このコメントブロックは published document には含めない。
- published document は canonical document から派生する公開成果物として扱い、内容の変更が必要な場合は canonical source または realization context へ戻して canonical document を再生成する。
-->

# honehone

`honehone` は、**決まった形の処理を持つクラス**を書くためのライブラリです。

形(どのワーカーが、どの順に、どう並んで動くか)はスケルトンクラスがデコレータで宣言し、中身は実装クラスがメソッドを上書きして埋めます。インスタンスを渡して起動すると、宣言した形のとおりに自律的に動き、止め方、後始末、一時停止、報告がついてきます。

## 形を書き、中身を埋める

例えば、開発環境を立ち上げる道具を考えます。DB と API を並行に起動し、両方の準備ができたらブラウザを開き、あとは見張りを続け、Ctrl+C で全部を片付けて止まる、という形です。

```python
import subprocess
import webbrowser
from abc import abstractmethod

import honehone
from honehone import Context, Sequence, Skeleton, repeat, service


class DevEnv(Skeleton):
    """開発環境を立ち上げる形。中身は実装クラスが埋める。"""

    main = Sequence()
    services = main.parallel()  # main の中の、この位置に入る

    @services
    @service
    @abstractmethod
    def database(self, ctx: Context) -> None: ...

    @services
    @service
    @abstractmethod
    def api(self, ctx: Context) -> None: ...

    @main
    def open_browser(self, ctx: Context) -> None: ...  # 既定では何もしない

    @main
    @repeat(every=1.0)
    def watch(self, ctx: Context) -> None: ...


class MyDevEnv(DevEnv):
    """このプロジェクト用の中身。デコレータは付けない。"""

    def __init__(self, port: int) -> None:
        self.port = port  # __init__ は設定値を受け取るだけ

    def database(self, ctx: Context) -> None:
        proc = subprocess.Popen(["postgres", "-D", "data"])
        ctx.on_stop(proc.terminate)
        ctx.ready()  # 準備ができた。ここから先も動き続ける
        proc.wait()

    def api(self, ctx: Context) -> None:
        proc = subprocess.Popen(["uvicorn", "app:app", "--port", str(self.port)])
        ctx.on_stop(proc.terminate)
        ctx.ready()
        proc.wait()

    def open_browser(self, ctx: Context) -> None:
        webbrowser.open(f"http://localhost:{self.port}")


def show(tag: str, *args: object, **kwargs: object) -> None:
    print(tag, *args, kwargs)  # 報告の受け手。進捗表示やログに使える


result = honehone.run(MyDevEnv(port=8000), listener=show)  # Ctrl+C で止まる
result.raise_if_failed()
```

読むときに注目してほしいのは、二つのクラスの役割の違いです。

- `DevEnv`(スケルトンクラス)は**形だけ**を持ちます。何をどの順に動かすかはデコレータで宣言され、クラスを読めば手順が分かります。`@abstractmethod` のワーカーは、実装クラスで上書きしないと生成できません
- `MyDevEnv`(実装クラス)は**中身だけ**を持ちます。デコレータは付けず、普通にメソッドを上書きします

同じ `DevEnv` を、別のプロジェクトでは別の中身で使えます。

## 形からついてくるもの

形を宣言したことで、次のものを書かずに手に入れられます。

- **止め方。** Ctrl+C や `stop()` で停止を要求すると、見張りが止まり、service は準備ができた順の逆順に一つずつ止まります(API を止めてから DB)
- **後始末。** `cleanup` は、成功しても失敗しても止められても、かならず走ります
- **一時停止。** ループと手順の移り目をスケルトンが持っているので、ワーカーが何も協力しなくても、区切りで止められます
- **報告。** 各ワーカーの状態の変化が送られるので、受け手を一つ用意すれば進捗表示やログが作れます
- **作りかけでも動くこと。** 抽象でないワーカーの既定は何もしない処理なので、形だけを先に動かし、中身を少しずつ埋められます

## 最初に知っておくこと

- **ワーカーを定義できるのはスケルトンクラスだけです。** `Skeleton` を直接継承したクラスだけが、グループやワーカーを宣言できます。それを継承した実装クラスは中身の上書きだけを行い、形は変えません
- **インスタンス一つは実行一つです。** もう一度動かすときは、インスタンスを作り直します
- **本体が動いている間、インスタンスは凍結されます。** 属性に書けるのは `boot` と `cleanup` の間だけです。ワーカー同士のやり取りは `boot` で用意した `Channel` や `Shared` を通します
- **停止と一時停止は協調的です。** スケルトンは区切りで止めますが、1 回分の呼び出しの途中には割り込みません。止まらなかったワーカーは報告されます
- Python `>=3.11` が必要です。

## 形の書き方

ここからは、形を書くための道具を一つずつ説明します。

### グループと順番

グループはクラス属性として宣言し、そのままデコレータとして使います。ほかのグループの中に入るグループは、親の `sequence()` / `parallel()` で作ります。グループの中の順番は、クラス本体の中で定義された順です。最初の例の形は、次の木になります。

```text
main (Sequence)
├── services (Parallel)
│   ├── database   @service
│   └── api        @service
├── open_browser
└── watch          @repeat(every=1.0)
```

親を持たないグループ(ルート)は一つだけです。形の誤り(ルートが二つある、空のグループがある、実装クラスで形を変えようとした、など)は、実行を待たずにクラスの定義時にエラーになります。

### 組み合わせ

グループの種類は、子の並べ方と終わり方の組み合わせで決まります。

| | `until="all"`(既定) | `until="first_success"` | `until="first_done"` |
| --- | --- | --- | --- |
| `Sequence` | 順に全部 | 順に試して最初の成功まで | (使えない) |
| `Parallel` | 同時に全部 | 先着の成功。残りは止める | 先着の終了。残りは止める |

止められた子は失敗に数えません。`Parallel(lockstep=True)` にすると、繰り返すワーカーたちが 1 回ずつ足並みをそろえて進みます。

### 修飾

ワーカーにはデコレータで修飾を付けられます。

- `@repeat(times=, every=, until=)`: スケルトンが呼び出しを繰り返します。ワーカーは 1 回分だけを書けばよく、停止の確認も要りません
- `@retry(times, backoff=)`: 失敗したら呼び直します
- `@timeout(seconds)`: 1 回の呼び出しの時間を制限します
- `@optional`: 失敗しても全体を止めません。失敗は記録に残ります
- `@service`: 準備ができたら次へ進み、本体が終わるまで動き続けます(`ctx.ready()` で準備を知らせる)
- `@pinned` / `@isolated`: 動くスレッドの制約です(後述)

修飾は、重ねた順によらず、内側から `timeout`、`retry`、`repeat`、`optional` の順に効きます。

### 準備と後始末、スレッド

資源は `boot` で用意し、`cleanup` で片付けます。`@cleanup(of=connect)` のように `boot` と対にした `cleanup` は、その `boot` が成功したときだけ走ります。`@boot` は関数をそのまま返すので、実装クラスは `boot` や `cleanup` の中身も普通のメソッドとして上書きできます。`cleanup` は定義の逆順に、一つが失敗しても全部走ります。

```python
import sqlite3
from abc import abstractmethod

import honehone
from honehone import Context, Parallel, Skeleton, boot, cleanup, pinned


class Archiver(Skeleton):
    body = Parallel()

    @boot
    def connect(self, ctx: Context) -> None:
        # boot の間だけ属性に書ける。資源はここで用意する
        db = sqlite3.connect("archive.db")
        db.execute("CREATE TABLE IF NOT EXISTS lines (line TEXT)")
        self.db = honehone.ThreadBound(db)
        self.lines = honehone.Channel(str)

    @cleanup(of=connect)
    def disconnect(self, ctx: Context) -> None:  # connect が成功したときだけ走る
        self.db.get().close()

    @body
    @abstractmethod
    def collect(self, ctx: Context) -> None: ...  # self.lines に送り、最後に close する

    @body
    @pinned
    def store(self, ctx: Context) -> None:
        db = self.db.get()  # 家のスレッドで動くので使える
        for line in self.lines.receive(ctx):
            db.execute("INSERT INTO lines VALUES (?)", (line,))
        db.commit()
```

ワーカーがどのスレッドで動くかは、構造から決まります。順に動くものは親と同じスレッドで、`Parallel` の子は専用のスレッドで動きます。そのうえで、葉に制約を付けられます。

- `@pinned`: かならず**家のスレッド**(`boot` が動いたスレッド)で動きます。sqlite の接続のように、スレッドをまたげない資源を使うワーカーに付けます。資源は `honehone.ThreadBound` で包むと、ほかのスレッドから触ったときにエラーで知らせます
- `@isolated`: かならず専用のスレッドで動きます。固まる恐れのある処理に付けると、止まらなくても見切って後始末へ進めます

## 動かして操作する

`honehone.run()` は呼んだスレッドで実行し、終わるまで待ちます。小さな道具ならこれで十分です。実行中に操作したいときは、`honehone.start()` で操作盤 `Run` を受け取ります。ノードは名前で指します。

```python
import honehone
from honehone import Context, Parallel, Skeleton, repeat


class Ticker(Skeleton):
    clocks = Parallel()

    @clocks
    @repeat(every=0.1)
    def fast(self, ctx: Context) -> None:
        ctx.report("tick")

    @clocks
    @repeat(every=0.5)
    def slow(self, ctx: Context) -> None: ...


run = honehone.start(Ticker())
run.wait_until("fast", "running")
run.pause("fast")  # 要求を出してすぐ戻る。次の区切りで止まる
run.wait_until("fast", "paused")
run.resume("fast")
run.stop()
result = run.wait()
print(result.outcome, result.nodes["fast"].calls > 0)  # stopped True
```

| 操作 | 内容 |
| --- | --- |
| `pause(name)` / `resume(name)` | 一時停止と再開。名前を省くと本体全体 |
| `stop()` | 全体の停止。一時停止中のものも起こして止める |
| `wait(timeout)` | 実行の終わりを待ち、結果を返す |
| `wait_until(name, state, timeout)` | ノードが指定の状態になるまで待つ |
| `state(name)` | ノードの今の状態 |

`pause()` は要求を出してすぐ戻ります。ノードは `pausing` を経て、次の区切り(繰り返しの次の回の前、手順の移り目、子の起動前)で `paused` になります。準備の後も動き続ける service だけは区切りを持たないので、一時停止させたいときはワーカーの中で `ctx.checkpoint()` を呼びます。

## 結果と報告

`run()` と `Run.wait()` は、例外を送出せず、かならず結果 `Result` を返します。`result.outcome` は `"completed"`、`"failed"`、`"stopped"` のどれかで、失敗は停止より優先します。`result.nodes["名前"]` で各ノードの状態、例外、呼ばれた回数、最後の戻り値、所要時間を見られます。失敗を例外として扱いたいときは `result.raise_if_failed()` を呼ぶと、`SkeletonFailed`(`ExceptionGroup`)が送出されます。

`run()` と `start()` に `listener` を渡すと、実行の出来事が報告されます。報告は [fport](https://github.com/minoru-jp/fport) の送信口を通るので、受け手が失敗しても実行には影響しません。ワーカーは `ctx.report()` で自分の進捗も送れます。

## gpframe と fport との関係

`honehone` は、[gpframe](https://github.com/minoru-jp/gpframe) と同じ原則で動きます。停止は上から下へ伝わる協調的な要求で、失敗は上へまとまり、止まらなかった処理は強制的に止めずに報告します。ワーカーの間の受け渡しには gpframe の `Channel` と `Shared` をそのまま使います。ただし `honehone` の公開面には gpframe の型は現れず、スケルトンを書く人は gpframe を知らなくても使えます。

使い分けは、構造が**いつ決まるか**です。接続やリクエストごとにワーカーが増減するサーバーのように、構造が実行時に決まるものは gpframe で書きます。手順や形がクラスを書いた時点で決まっているものは `honehone` で書きます。両者は組み合わせられ、gpframe の木の中にスケルトンを入れるときは `s.spawn(honehone.gpframe.routine, obj)` を使います。たとえば、サーバーが接続ごとに「1 接続分の手順」をスケルトンとして起動できます。

## 例

[`examples/`](https://github.com/minoru-jp/honehone/tree/main/examples) には、`honehone` ならではの性質を一つずつ見せる例を置いています。どれも標準ライブラリだけで動き、`python examples/<名前>.py` で実行できます。

- [`cooking.py`](https://github.com/minoru-jp/honehone/blob/main/examples/cooking.py): **形の使い回しと一時停止。** 麺の鍋とソースの鍋を並行に進めて盛り付ける、というレシピの形を一つ書き、カルボナーラとアラビアータがその中身だけを埋めます。作業の途中で `ctx.checkpoint()` を呼ぶので、`pause()` で台所を離れている間はどの鍋も進まず、`resume()` で続きから進みます。報告の受け手が、そのまま調理の表示になります。
- [`instrument.py`](https://github.com/minoru-jp/honehone/blob/main/examples/instrument.py): **service と後始末の順序。** 装置に接続し、温度を見張る service を動かしながら計測し、`@pinned` のワーカーが sqlite に記録して、最後に切断します。正常に終わっても、過熱で失敗しても、Ctrl+C で止めても、記録を締め、見張りを止めてから切断する、という順番が守られます。どの装置を使うかだけを実装クラスが決めます。
- [`console.py`](https://github.com/minoru-jp/honehone/blob/main/examples/console.py): **操作盤としての CLI。** 裏で動く仕事(バックアップの模擬)を、`status` / `pause` / `resume` / `quit` で操作します。Ctrl+C を受けて止める判断は管理役(`honehone.run()` を呼んだメインスレッド)が持ち、入力は `@isolated` のワーカーが別スレッドで読みます。入力の途中で止まることになっても、打ちかけの行は消さず、Enter で戻ったところで止まります。コマンドは `honehone.control(self)` の操作盤を呼ぶだけです。

## インストール

```bash
pip install honehone
```

依存パッケージとして [gpframe](https://github.com/minoru-jp/gpframe) と [fport](https://github.com/minoru-jp/fport) が入ります。

## 開発

開発に使う道具は `dev` extra にまとめています。すべての検査は `tools/check.py` で走らせ、CI とリリースも同じものを使います。

```console
pip install -e ".[dev]"
python tools/check.py            # すべての検査
python tools/check.py lint tests # 選んだ検査だけ
```

振る舞いの規則は `devdocs/canonical_sources/` の正本(日本語)に書き、`python scripts/render_devdocs.py` で canonical document を生成します。英語の公開文書は canonical document の翻訳です。

## 関連文書

- [STATUS.md](https://github.com/minoru-jp/honehone/blob/main/STATUS.md): 開発段階、範囲、決まっていること、今後の方向
- [docs/specification/INDEX.md](https://github.com/minoru-jp/honehone/blob/main/docs/specification/INDEX.md): 振る舞いの規則(Specification)
- [CHANGELOG.md](https://github.com/minoru-jp/honehone/blob/main/CHANGELOG.md): 版ごとの変更
