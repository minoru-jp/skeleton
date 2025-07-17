

ロジック実行の前後にイベントを挿入し、状態・ログ・アクションの管理、コード生成・試行実行までを支援する、汎用的な実行スケルトン。


モード
このスケルトンは、用途に応じて2つのモードで動作します。

🚀 実行モード
一定の呼び出し形式をもつ（関数）をラップして、イベント・状態・ログ・アクション付きで実行します。

make_skeleton_handle(routine) に、実行したい処理（関数やコルーチン）を渡します。

.start() で実行開始。

.stop()、.pause()、.resume()、イベントハンドラ登録などで制御可能。


🛠 コード生成モード
実行用の雛形コードを自動生成したり、テスト的に実行するためのモードです。

make_skeleton_handle(context_type) に、Context の型を渡します。

.code(CodeTemplate) でコード生成。

.trial(CodeTemplate) で生成したコードをコンパイルして即座に試行実行。

.code_on_trial(CodeTemplate) は安全な名前マッピング付きでコードを生成します。



🔷 主な役割とプロトコル

driver:
- make_skeleton_handle()から得られるハンドルを操作するもの
- environmentに書き込むことで、EventHandler、SubRoutineにメッセージを伝達できる

EventHandler:
- .set_on_start()などで対応するイベントに設定されたハンドラ
- event_messageに書き込むことで、driver、SubRoutineにメッセージを伝達できる

Routine:
- routine(context: Context[T])の呼び出し形式を持ち、skeletonがラップの対象にする関数
- ユーザーによる定義のほか、CodeTemplateによる自動生成によって生み出される

SubRoutine:
- .append_subroutine()で任意の数登録できる
- Routine内でContext[T]を通して使用する関数
- routine_messageに書き込むことで、driver、EventHandlerにメッセージを伝達できる

Context[T]:
- Routine / SubRoutine に渡される、メッセージや状態へのアクセス、フィールド共有のためのインターフェース。
- Context[T]のT型はRoutine,SubRoutineの共有オブジェクトである.fieldの型を指す


🚀 実行の流れ

.start()
   │
   ▼
 ACTIVE
   │
   │  on_start
   │
   ▼
[Execute Routine]
   │
   ├─── context.signal.Continue
   │         │
   │         ▼
   │     on_continue
   │         │
   │       （loop）
   │
   ├─── Normal termination
   │         │
   │         ▼
   │      on_end
   │
   ├─── Cancelled
   │         │
   │         ▼
   │     on_cancel
   │
   ▼
on_close
   │
   ▼
TERMINATED

正常終了・キャンセルいずれの場合も、最後は必ず on_close が呼ばれます。
例外でroutineを抜けた場合も on_close の呼び出しを試みます。

```python
async def routine(context: Context[Any]):
    print("hello world.")
    context.caller.subroutine()
    print(f"{context.prev.process} result: {context.prev.result}")

def subroutine(context: Context[Any]):
    return "hello small world."

handle = make_skeleton_handle(routine)

handle.log.set_role("example")

# 各EventHandlerはデフォルトでイベント名をロギングする

handle.append_subroutine(subroutine)

task = handle.start()
await task

```

Routine の動作について、確実に保証されるのは .start() による開始のみです。
停止・一時停止・再開が想定通りに動作するかどうかは Routine の実装に依存します。
そのため、これらのインターフェースは .request 内にまとめられています。