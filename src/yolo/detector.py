"""Detector backend protocol and implementations for Module 2 (YOLO)."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from src.yolo.exceptions import DetectorDependencyError, DetectorError


@dataclass
class DetectorConfig:
    model_name: str = "yolov8n.pt"
    confidence_threshold: float = 0.35
    iou_threshold: float = 0.50
    image_size: int = 640
    max_candidates: int = 30
    device: str = "auto"

    def __post_init__(self) -> None:
        if not (0.0 < self.confidence_threshold <= 1.0) or not math.isfinite(self.confidence_threshold):
            raise ValueError(f"confidence_threshold must be in (0.0, 1.0], got {self.confidence_threshold}")
        if not (0.0 < self.iou_threshold <= 1.0) or not math.isfinite(self.iou_threshold):
            raise ValueError(f"iou_threshold must be in (0.0, 1.0], got {self.iou_threshold}")
        if not isinstance(self.image_size, int) or self.image_size <= 0:
            raise ValueError(f"image_size must be a positive integer, got {self.image_size}")
        if not isinstance(self.max_candidates, int) or self.max_candidates <= 0:
            raise ValueError(f"max_candidates must be a positive integer, got {self.max_candidates}")

        # Validate device string
        dev = self.device.strip().lower()
        if dev not in ("auto", "cpu", "mps", "cuda") and not re.match(r"^cuda:\d+$", dev):
            raise ValueError(f"Invalid device '{self.device}'. Expected auto, cpu, mps, cuda, or cuda:<int>")
        self.device = dev


@dataclass
class RawPrediction:
    class_id: int
    class_name: str
    confidence: float
    bbox_xyxy: tuple[float, float, float, float]

    def __post_init__(self) -> None:
        if not self.class_name or not isinstance(self.class_name, str) or not self.class_name.strip():
            raise ValueError("class_name must be a non-empty string")
        if not math.isfinite(self.confidence) or not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0.0, 1.0], got {self.confidence}")
        if not isinstance(self.bbox_xyxy, (tuple, list)) or len(self.bbox_xyxy) != 4:
            raise ValueError(f"bbox_xyxy must be 4 coordinates, got {self.bbox_xyxy}")
        coords = (
            float(self.bbox_xyxy[0]),
            float(self.bbox_xyxy[1]),
            float(self.bbox_xyxy[2]),
            float(self.bbox_xyxy[3]),
        )
        if not all(math.isfinite(c) for c in coords):
            raise ValueError(f"bbox_xyxy coordinates must be finite, got {coords}")
        x1, y1, x2, y2 = coords
        if x2 <= x1 or y2 <= y1:
            raise ValueError(f"Invalid bbox_xyxy coordinates: x2 ({x2}) <= x1 ({x1}) or y2 ({y2}) <= y1 ({y1})")
        self.bbox_xyxy = coords


@dataclass
class ModelProvenance:
    model_name: str
    model_version: str
    weights_identifier: str
    device_resolved: str
    confidence_threshold: float
    iou_threshold: float
    image_size: int
    built_in_nms: bool


@dataclass
class DetectorOutput:
    predictions: list[RawPrediction]
    provenance: ModelProvenance
    raw_prediction_count: int
    truncated: bool = False
    truncation_warning: str | None = None


def apply_confidence_filter_and_truncation(
    predictions: list[RawPrediction],
    confidence_threshold: float,
    max_candidates: int,
) -> tuple[list[RawPrediction], int, bool, str | None]:
    """Filters predictions by confidence, sorts descending, and applies explicit truncation."""
    filtered = [p for p in predictions if p.confidence >= confidence_threshold]
    sorted_preds = sorted(filtered, key=lambda p: p.confidence, reverse=True)
    raw_count = len(sorted_preds)

    if raw_count > max_candidates:
        kept = sorted_preds[:max_candidates]
        warning = (
            f"Raw predictions ({raw_count}) exceeded max_candidates ({max_candidates}); "
            f"truncated to top {len(kept)} by confidence."
        )
        return kept, raw_count, True, warning

    return sorted_preds, raw_count, False, None


class DetectorBackend(Protocol):
    """Protocol for detector backends."""

    @property
    def is_loaded(self) -> bool: ...

    def load(self) -> None: ...

    def detect(self, image_path: Path | str, config: DetectorConfig | None = None) -> DetectorOutput: ...


class StubDetectorBackend:
    """Deterministic, zero-dependency detector backend for tests and offline workflows."""

    def __init__(
        self,
        predictions: list[RawPrediction] | dict[str, list[RawPrediction]] | Callable[[Path], list[RawPrediction]] | None = None,
        fail_on_load: Exception | None = None,
        fail_on_detect: Exception | None = None,
        model_name: str = "stub-detector",
        model_version: str = "1.0.0",
        weights_identifier: str = "stub-weights-hash",
    ) -> None:
        self.predictions = predictions
        self.fail_on_load = fail_on_load
        self.fail_on_detect = fail_on_detect
        self.model_name = model_name
        self.model_version = model_version
        self.weights_identifier = weights_identifier
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load(self) -> None:
        if self.fail_on_load is not None:
            raise self.fail_on_load
        self._loaded = True

    def detect(self, image_path: Path | str, config: DetectorConfig | None = None) -> DetectorOutput:
        if not self.is_loaded:
            self.load()
        if self.fail_on_detect is not None:
            raise self.fail_on_detect

        img_p = Path(image_path)
        if not img_p.is_file():
            raise DetectorError(f"Image file not found: {image_path}")

        cfg = config or DetectorConfig()

        # Resolve raw predictions
        raw_list: list[RawPrediction] = []
        if callable(self.predictions):
            try:
                raw_list = list(self.predictions(img_p))
            except Exception as exc:
                raise DetectorError(f"Prediction callback failed: {exc}") from exc
        elif isinstance(self.predictions, dict):
            raw_list = list(self.predictions.get(img_p.name, self.predictions.get(str(img_p), [])))
        elif isinstance(self.predictions, list):
            raw_list = list(self.predictions)

        # Validate that items are RawPrediction
        for p in raw_list:
            if not isinstance(p, RawPrediction):
                raise DetectorError(f"Stub prediction must be RawPrediction instance, got {type(p)}")

        kept, raw_count, truncated, warning = apply_confidence_filter_and_truncation(
            raw_list,
            cfg.confidence_threshold,
            cfg.max_candidates,
        )

        provenance = ModelProvenance(
            model_name=self.model_name,
            model_version=self.model_version,
            weights_identifier=self.weights_identifier,
            device_resolved="cpu",
            confidence_threshold=cfg.confidence_threshold,
            iou_threshold=cfg.iou_threshold,
            image_size=cfg.image_size,
            built_in_nms=True,
        )

        return DetectorOutput(
            predictions=kept,
            provenance=provenance,
            raw_prediction_count=raw_count,
            truncated=truncated,
            truncation_warning=warning,
        )


class UltralyticsYOLOBackend:
    """Lazy-loaded Ultralytics YOLO detector backend with model provenance and candidate truncation."""

    def __init__(
        self,
        model_name: str = "yolov8n.pt",
        device: str = "auto",
        _module_loader: Callable[[], Any] | None = None,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self._module_loader = _module_loader
        self._model: Any = None
        self._device_resolved: str = "cpu"
        self._weights_identifier: str = model_name
        self._model_version: str = "unknown"
        self._loaded: bool = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def _resolve_device(self) -> str:
        dev = self.device.strip().lower()
        if dev == "auto":
            try:
                import torch
                if torch.cuda.is_available():
                    return "cuda"
            except Exception:
                pass
            return "cpu"
        return dev

    def _compute_weights_identifier(self) -> str:
        weights_p = Path(self.model_name)
        if weights_p.is_file():
            try:
                data = weights_p.read_bytes()
                return hashlib.sha256(data).hexdigest()
            except Exception:
                pass
        return self.model_name

    def load(self) -> None:
        if self._loaded:
            return

        # Lazy load ultralytics
        if self._module_loader is not None:
            try:
                ultra_mod = self._module_loader()
            except Exception as exc:
                if isinstance(exc, (ImportError, ModuleNotFoundError)):
                    raise DetectorDependencyError("Ultralytics package is not available") from exc
                raise DetectorError(f"Failed to load ultralytics module via loader: {exc}") from exc
        else:
            try:
                import ultralytics  # pyrefly: ignore [missing-import]
                ultra_mod = ultralytics
            except (ImportError, ModuleNotFoundError) as exc:
                raise DetectorDependencyError(
                    "Ultralytics package is not installed. Install via 'pip install ultralytics'."
                ) from exc

        self._model_version = getattr(ultra_mod, "__version__", "unknown")
        self._device_resolved = self._resolve_device()
        self._weights_identifier = self._compute_weights_identifier()

        try:
            yolo_cls = getattr(ultra_mod, "YOLO")
            self._model = yolo_cls(self.model_name)
        except Exception as exc:
            raise DetectorError(f"Failed to load YOLO model '{self.model_name}': {exc}") from exc

        self._loaded = True

    def detect(self, image_path: Path | str, config: DetectorConfig | None = None) -> DetectorOutput:
        if not self.is_loaded:
            self.load()

        img_p = Path(image_path)
        if not img_p.is_file():
            raise DetectorError(f"Image file not found: {image_path}")

        cfg = config or DetectorConfig()

        try:
            results = self._model.predict(
                source=str(img_p),
                conf=cfg.confidence_threshold,
                iou=cfg.iou_threshold,
                imgsz=cfg.image_size,
                device=self._device_resolved,
                verbose=False,
            )
        except Exception as exc:
            raise DetectorError(f"YOLO inference failed on '{image_path}': {exc}") from exc

        raw_predictions: list[RawPrediction] = []
        try:
            if results and len(results) > 0:
                res = results[0]
                boxes = getattr(res, "boxes", None)
                names = getattr(res, "names", {})
                if boxes is not None:
                    if not hasattr(boxes, "xyxy") or not hasattr(boxes, "conf") or not hasattr(boxes, "cls"):
                        raise DetectorError("Malformed YOLO inference result: missing xyxy, conf, or cls attributes")
                    b_xyxy = getattr(boxes, "xyxy", None)
                    b_conf = getattr(boxes, "conf", None)
                    b_cls = getattr(boxes, "cls", None)

                    if b_xyxy is None or b_conf is None or b_cls is None:
                        raise DetectorError("Malformed YOLO inference result: None attribute in xyxy, conf, or cls")

                    # Convert to list if torch tensor or numpy array
                    xyxy_list = b_xyxy.tolist() if hasattr(b_xyxy, "tolist") else list(b_xyxy)
                    conf_list = b_conf.tolist() if hasattr(b_conf, "tolist") else list(b_conf)
                    cls_list = b_cls.tolist() if hasattr(b_cls, "tolist") else list(b_cls)

                    for coords, conf, c_id in zip(xyxy_list, conf_list, cls_list):
                        c_int = int(c_id)
                        c_name = names.get(c_int, str(c_int)) if isinstance(names, dict) else str(c_int)
                        raw_predictions.append(
                            RawPrediction(
                                class_id=c_int,
                                class_name=c_name,
                                confidence=float(conf),
                                bbox_xyxy=tuple(float(c) for c in coords),  # type: ignore[arg-type]
                            )
                        )
        except DetectorError:
            raise
        except Exception as exc:
            raise DetectorError(f"Malformed YOLO inference result: {exc}") from exc

        kept, raw_count, truncated, warning = apply_confidence_filter_and_truncation(
            raw_predictions,
            cfg.confidence_threshold,
            cfg.max_candidates,
        )

        provenance = ModelProvenance(
            model_name=self.model_name,
            model_version=self._model_version,
            weights_identifier=self._weights_identifier,
            device_resolved=self._device_resolved,
            confidence_threshold=cfg.confidence_threshold,
            iou_threshold=cfg.iou_threshold,
            image_size=cfg.image_size,
            built_in_nms=True,
        )

        return DetectorOutput(
            predictions=kept,
            provenance=provenance,
            raw_prediction_count=raw_count,
            truncated=truncated,
            truncation_warning=warning,
        )
