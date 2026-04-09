from __future__ import annotations

from dataclasses import dataclass
import time
from typing import TYPE_CHECKING

try:
    from typing import Protocol
except ImportError:
    class Protocol:  # type: ignore[too-many-ancestors]
        pass

from .config import CameraConfig

if TYPE_CHECKING:
    import numpy as np


@dataclass(frozen=True)
class CaptureRuntimeInfo:
    backend: str
    source: str
    actual_width: int | None = None
    actual_height: int | None = None
    actual_fps: float | None = None


class FrameCapture(Protocol):
    def read(self) -> tuple[bool, "np.ndarray | None"]:
        ...

    def release(self) -> None:
        ...

    def runtime_info(self) -> CaptureRuntimeInfo:
        ...


def is_picamera2_source(source: int | str) -> bool:
    if not isinstance(source, str):
        return False
    return source.strip().lower() in {"picamera2", "picam", "rpi-camera", "libcamera"}


def open_capture(config: CameraConfig, *, cv2: object) -> FrameCapture:
    if is_picamera2_source(config.source):
        return Picamera2Capture(config, cv2=cv2)
    return OpenCvCapture(config, cv2=cv2)


class OpenCvCapture:
    def __init__(self, config: CameraConfig, *, cv2: object) -> None:
        self._capture = cv2.VideoCapture(config.source)
        self._cv2 = cv2
        self._source = config.source

        if not self._capture.isOpened():
            raise RuntimeError(f"Video source could not be opened: {config.source}")

        if config.width:
            self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, config.width)
        if config.height:
            self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, config.height)
        if config.fps:
            self._capture.set(cv2.CAP_PROP_FPS, config.fps)

    def read(self) -> tuple[bool, "np.ndarray | None"]:
        ok, frame = self._capture.read()
        return ok, frame if ok else None

    def release(self) -> None:
        self._capture.release()

    def runtime_info(self) -> CaptureRuntimeInfo:
        return CaptureRuntimeInfo(
            backend="opencv",
            source=str(self._source),
            actual_width=_safe_int(self._capture.get(self._cv2.CAP_PROP_FRAME_WIDTH)),
            actual_height=_safe_int(self._capture.get(self._cv2.CAP_PROP_FRAME_HEIGHT)),
            actual_fps=_safe_float(self._capture.get(self._cv2.CAP_PROP_FPS)),
        )


class Picamera2Capture:
    def __init__(self, config: CameraConfig, *, cv2: object) -> None:
        try:
            from picamera2 import Picamera2
        except ImportError as exc:
            raise RuntimeError(
                "Picamera2 source requested but python3-picamera2 is not installed. "
                "On Raspberry Pi OS use: sudo apt install -y python3-picamera2"
            ) from exc

        self._cv2 = cv2
        self._source = config.source
        self._requested_width = config.width
        self._requested_height = config.height
        self._requested_fps = float(config.fps) if config.fps else None
        self._last_shape: tuple[int, int] | None = None
        self._camera = Picamera2()

        main_config: dict[str, object] = {"format": "RGB888"}
        if config.width and config.height:
            main_config["size"] = (config.width, config.height)

        preview_config = self._camera.create_preview_configuration(main=main_config)
        self._camera.configure(preview_config)
        if self._requested_fps is not None:
            self._camera.set_controls({"FrameRate": self._requested_fps})
        self._camera.start()
        time.sleep(0.2)

    def read(self) -> tuple[bool, "np.ndarray | None"]:
        try:
            frame = self._camera.capture_array()
        except Exception:
            return False, None

        if frame is None:
            return False, None

        if len(frame.shape) == 3 and frame.shape[2] == 4:
            bgr_frame = self._cv2.cvtColor(frame, self._cv2.COLOR_RGBA2BGR)
        else:
            bgr_frame = self._cv2.cvtColor(frame, self._cv2.COLOR_RGB2BGR)

        self._last_shape = (int(bgr_frame.shape[1]), int(bgr_frame.shape[0]))
        return True, bgr_frame

    def release(self) -> None:
        try:
            self._camera.stop()
        finally:
            self._camera.close()

    def runtime_info(self) -> CaptureRuntimeInfo:
        width = self._last_shape[0] if self._last_shape else self._requested_width
        height = self._last_shape[1] if self._last_shape else self._requested_height
        return CaptureRuntimeInfo(
            backend="picamera2",
            source=str(self._source),
            actual_width=width,
            actual_height=height,
            actual_fps=self._requested_fps,
        )


def _safe_int(value: object) -> int | None:
    try:
        integer = int(value)
    except Exception:
        return None
    return integer if integer > 0 else None


def _safe_float(value: object) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    return number if number > 0 else None
