"""
一定間隔での処理を行うためのリアクタ、コンテキスト、アクションの実装

このモジュールは以下の機能を提供します:
- FPS指定による間隔制御
- 実時間指定による間隔制御
- 処理時間の計測と統計
- 適応的な遅延調整
"""

import asyncio
import time
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass
from enum import Enum

# 提供されたモジュールから必要な型をインポート
from loop_engine import (
    Context, Reactor, ReactorFactory, Action, LoopControl
)


class IntervalMode(Enum):
    """間隔制御のモード"""
    FPS = "fps"
    REAL_TIME = "real_time"


@dataclass
class IntervalConfig:
    """間隔制御の設定"""
    mode: IntervalMode
    fps: Optional[float] = None  # FPSモード用
    interval_seconds: Optional[float] = None  # 実時間モード用
    adaptive: bool = True  # 適応的調整の有効化
    max_skip_frames: int = 5  # 最大スキップフレーム数
    
    def __post_init__(self):
        if self.mode == IntervalMode.FPS and self.fps is None:
            raise ValueError("FPS mode requires fps parameter")
        if self.mode == IntervalMode.REAL_TIME and self.interval_seconds is None:
            raise ValueError("Real time mode requires interval_seconds parameter")
        
        if self.mode == IntervalMode.FPS and self.fps <= 0:
            raise ValueError("FPS must be positive")
        if self.mode == IntervalMode.REAL_TIME and self.interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")


@dataclass
class IntervalStats:
    """間隔制御の統計情報"""
    total_iterations: int = 0
    total_time: float = 0.0
    min_frame_time: float = float('inf')
    max_frame_time: float = 0.0
    avg_frame_time: float = 0.0
    skipped_frames: int = 0
    target_interval: float = 0.0
    
    def update(self, frame_time: float):
        """フレーム時間の統計を更新"""
        self.total_iterations += 1
        self.total_time += frame_time
        self.min_frame_time = min(self.min_frame_time, frame_time)
        self.max_frame_time = max(self.max_frame_time, frame_time)
        self.avg_frame_time = self.total_time / self.total_iterations
    
    def reset(self):
        """統計をリセット"""
        self.total_iterations = 0
        self.total_time = 0.0
        self.min_frame_time = float('inf')
        self.max_frame_time = 0.0
        self.avg_frame_time = 0.0
        self.skipped_frames = 0


class IntervalContext:
    """間隔制御用のコンテキスト"""
    
    def __init__(self, config: IntervalConfig):
        self.config = config
        self.stats = IntervalStats()
        self.last_time = time.time()
        self.accumulated_delay = 0.0
        self.user_data: Dict[str, Any] = {}
        
        # 目標間隔を計算
        if config.mode == IntervalMode.FPS:
            self.target_interval = 1.0 / config.fps
        else:
            self.target_interval = config.interval_seconds
        
        self.stats.target_interval = self.target_interval
    
    def get_current_time(self) -> float:
        """現在時刻を取得"""
        return time.time()
    
    def get_elapsed_time(self) -> float:
        """前回からの経過時間を取得"""
        current_time = self.get_current_time()
        elapsed = current_time - self.last_time
        return elapsed
    
    def update_timing(self):
        """タイミングを更新"""
        current_time = self.get_current_time()
        frame_time = current_time - self.last_time
        self.stats.update(frame_time)
        self.last_time = current_time
    
    def calculate_sleep_time(self) -> float:
        """必要な待機時間を計算"""
        elapsed = self.get_elapsed_time()
        sleep_time = self.target_interval - elapsed
        
        if self.config.adaptive:
            # 適応的調整: 遅延が蓄積されている場合は考慮
            sleep_time += self.accumulated_delay
            if sleep_time < 0:
                # 目標より遅れている場合
                skip_frames = min(
                    int(abs(sleep_time) / self.target_interval),
                    self.config.max_skip_frames
                )
                self.stats.skipped_frames += skip_frames
                self.accumulated_delay = sleep_time % self.target_interval
                return 0.0
            else:
                self.accumulated_delay = 0.0
        
        return max(0.0, sleep_time)


def create_interval_reactor_factory(config: IntervalConfig) -> ReactorFactory:
    """間隔制御用のReactorFactoryを作成"""
    
    def factory(control: LoopControl) -> tuple[Reactor, Context]:
        context = IntervalContext(config)
        
        async def reactor(next_proc: str) -> Optional[asyncio.Task]:
            # アクション実行前の処理
            if next_proc.startswith('action_'):
                context.update_timing()
            
            # アクション実行後の処理
            elif next_proc == 'post_action':
                sleep_time = context.calculate_sleep_time()
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
            
            return None
        
        return reactor, context
    
    return factory


class IntervalStatsAction:
    """統計情報を出力するアクション"""
    
    def __init__(self, output_callback: Optional[Callable[[IntervalStats], None]] = None):
        self.output_callback = output_callback or self._default_output
    
    def _default_output(self, stats: IntervalStats):
        """デフォルトの統計出力"""
        print(f"=== Interval Statistics ===")
        print(f"Total iterations: {stats.total_iterations}")
        print(f"Total time: {stats.total_time:.3f}s")
        print(f"Target interval: {stats.target_interval:.3f}s")
        print(f"Avg frame time: {stats.avg_frame_time:.3f}s")
        print(f"Min frame time: {stats.min_frame_time:.3f}s")
        print(f"Max frame time: {stats.max_frame_time:.3f}s")
        print(f"Skipped frames: {stats.skipped_frames}")
        if stats.total_iterations > 0:
            actual_fps = stats.total_iterations / stats.total_time
            print(f"Actual FPS: {actual_fps:.2f}")
        print("===========================")
    
    def __call__(self, ctx: Context) -> None:
        if isinstance(ctx, IntervalContext):
            self.output_callback(ctx.stats)


class IntervalResetAction:
    """統計をリセットするアクション"""
    
    def __call__(self, ctx: Context) -> None:
        if isinstance(ctx, IntervalContext):
            ctx.stats.reset()


class IntervalUserAction:
    """ユーザー定義の処理を実行するアクション"""
    
    def __init__(self, user_callback: Callable[[IntervalContext], None]):
        self.user_callback = user_callback
    
    def __call__(self, ctx: Context) -> None:
        if isinstance(ctx, IntervalContext):
            self.user_callback(ctx)


class IntervalAsyncUserAction:
    """非同期ユーザー定義処理を実行するアクション"""
    
    def __init__(self, user_callback: Callable[[IntervalContext], asyncio.Task]):
        self.user_callback = user_callback
    
    async def __call__(self, ctx: Context) -> None:
        if isinstance(ctx, IntervalContext):
            await self.user_callback(ctx)


# 使用例とヘルパー関数

def create_fps_system(fps: float, adaptive: bool = True) -> tuple[ReactorFactory, IntervalConfig]:
    """FPS制御システムを作成"""
    config = IntervalConfig(
        mode=IntervalMode.FPS,
        fps=fps,
        adaptive=adaptive
    )
    factory = create_interval_reactor_factory(config)
    return factory, config


def create_realtime_system(interval_seconds: float, adaptive: bool = True) -> tuple[ReactorFactory, IntervalConfig]:
    """実時間制御システムを作成"""
    config = IntervalConfig(
        mode=IntervalMode.REAL_TIME,
        interval_seconds=interval_seconds,
        adaptive=adaptive
    )
    factory = create_interval_reactor_factory(config)
    return factory, config


# 使用例
def example_usage():
    """使用例"""
    
    # 60FPSでの処理
    reactor_factory, config = create_fps_system(60.0)
    
    # ユーザー定義の処理
    def my_process(ctx: IntervalContext):
        print(f"Processing... (iteration: {ctx.stats.total_iterations})")
        # ここにメイン処理を書く
        ctx.user_data['counter'] = ctx.user_data.get('counter', 0) + 1
    
    user_action = IntervalUserAction(my_process)
    stats_action = IntervalStatsAction()
    
    # 1秒間隔での統計出力
    def stats_output(ctx: IntervalContext):
        if ctx.stats.total_iterations % 60 == 0:  # 60FPSなら1秒毎
            stats_action(ctx)
    
    periodic_stats = IntervalUserAction(stats_output)
    
    # ループエンジンでの使用方法:
    # handle.set_action_reactor_factory(reactor_factory)
    # handle.append_action("main_process", user_action)
    # handle.append_action("stats_output", periodic_stats)
    
    print("Setup complete. Use these with your loop engine.")


if __name__ == "__main__":
    example_usage()