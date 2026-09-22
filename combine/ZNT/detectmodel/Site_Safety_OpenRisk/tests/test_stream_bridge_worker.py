from __future__ import annotations

import cv2

from stream_bridge_worker import (
    FrameSubmissionThrottle,
    capture_source,
    file_frame_step,
    is_live_capture,
)


class FakeCapture:
    def __init__(self, frame_count: float):
        self.frame_count = frame_count

    def get(self, prop: int) -> float:
        assert prop == cv2.CAP_PROP_FRAME_COUNT
        return self.frame_count


def test_throttle_only_waits_for_remaining_interval() -> None:
    now = [10.0]
    sleeps: list[float] = []

    def sleep(delay: float) -> None:
        sleeps.append(delay)
        now[0] += delay

    throttle = FrameSubmissionThrottle(2.0, clock=lambda: now[0], sleeper=sleep)
    assert throttle.ready()
    throttle.mark_submitted()

    # 网络/检测已经消耗 1.5 秒，只需等待余下 0.5 秒，而不是再固定等待 2 秒。
    now[0] = 11.5
    assert not throttle.ready()
    assert throttle.wait_until_ready() == 0.5
    assert sleeps == [0.5]
    assert throttle.ready()


def test_throttle_does_not_sleep_after_slow_submission() -> None:
    now = [20.0]
    sleeps: list[float] = []
    throttle = FrameSubmissionThrottle(2.0, clock=lambda: now[0], sleeper=sleeps.append)
    throttle.mark_submitted()

    # 上一次提交自身耗时已经超过间隔，不再追加一次 interval sleep。
    now[0] = 23.5
    assert throttle.wait_until_ready() == 0.0
    assert sleeps == []


def test_capture_kind_and_file_step() -> None:
    assert capture_source("0") == 0
    assert capture_source("rtsp://camera/live") == "rtsp://camera/live"
    assert is_live_capture("rtsp://camera/live", FakeCapture(900))
    assert is_live_capture("0", FakeCapture(0))
    assert is_live_capture("camera.mjpg", FakeCapture(0))
    assert not is_live_capture("example.mp4", FakeCapture(900))
    assert file_frame_step(25.0, 2.0) == 50
    assert file_frame_step(0.0, 0.1) == 5
