from __future__ import annotations

from app.models.settings import ClassificationThresholds
from app.services.quality_service import classify

T = ClassificationThresholds()


def test_classify_excellent():
    assert classify(10, 0, T) == "excellent"


def test_classify_good():
    assert classify(45, 1.5, T) == "good"


def test_classify_fair_by_latency():
    assert classify(80, 0, T) == "fair"


def test_classify_fair_by_loss():
    assert classify(200, 3, T) == "fair"


def test_classify_poor():
    assert classify(500, 10, T) == "poor"


def test_classify_unknown_without_data():
    assert classify(None, None, T) == "unknown"


def test_classify_respects_custom_thresholds():
    custom = ClassificationThresholds(excellent_latency_ms=500, excellent_packet_loss_pct=50)
    assert classify(400, 10, custom) == "excellent"
