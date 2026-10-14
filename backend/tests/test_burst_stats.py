"""
==============================================================================
Module Name:   test_burst_stats.py
Description:   Unit tests for percentile / RFC 3550 jitter / burst reduction.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-14
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         pytest backend/tests/test_burst_stats.py
Notes:         See module docstrings of the code under test.
==============================================================================
"""

from __future__ import annotations

import pytest
from app.monitoring.burst_stats import compute_burst_metric, percentile, rfc3550_jitter


def test_percentile_interpolates_between_ranks():
    assert percentile([10, 20, 30, 40], 25) == 17.5
    assert percentile([10, 20, 30, 40], 50) == 25
    assert percentile([10, 20, 30, 40], 75) == 32.5
    assert percentile([10, 20, 30, 40], 0) == 10
    assert percentile([10, 20, 30, 40], 100) == 40


def test_percentile_single_value_and_empty():
    assert percentile([7.5], 95) == 7.5
    with pytest.raises(ValueError):
        percentile([], 50)


def test_rfc3550_jitter_matches_hand_computation():
    # D = |20-10| = 10, |15-20| = 5, |15-15| = 0
    # J1 = 0 + (10 - 0)/16 = 0.625 ; J2 = 0.625 + (5 - 0.625)/16 = 0.8984375 ; J3 = J2 + (0 - J2)/16 = 0.842285...
    j = rfc3550_jitter([10, 20, 15, 15])
    assert j == pytest.approx(0.8984375 - 0.8984375 / 16)


def test_rfc3550_jitter_constant_rtt_is_zero_and_needs_two_samples():
    assert rfc3550_jitter([5.0] * 15) == 0.0
    assert rfc3550_jitter([5.0]) is None
    assert rfc3550_jitter([]) is None


def test_rfc3550_jitter_only_converges_slowly_from_zero():
    """The 1/16 gain: 14 identical |D| = 10 steps reach 1-(15/16)^14 ~ 59 % of 10, not 10."""
    alternating = [10.0, 20.0] * 8  # 16 samples -> 15 steps of |D| = 10
    expected = 10 * (1 - (15 / 16) ** 15)
    assert rfc3550_jitter(alternating) == pytest.approx(expected)
    assert rfc3550_jitter(alternating) < 10


def test_compute_burst_metric_full_burst():
    rtts = [float(v) for v in range(10, 25)]  # 15 probes: 10..24 ms
    m = compute_burst_metric(rtts, method="icmp")
    assert (m.packet_count, m.received, m.lost, m.loss_percent) == (15, 15, 0, 0.0)
    assert m.success is True
    assert (m.min_rtt, m.max_rtt) == (10.0, 24.0)
    assert m.median_rtt == 17.0
    assert (m.p25_rtt, m.p75_rtt, m.iqr_rtt) == (13.5, 20.5, 7.0)
    assert m.p95_rtt == pytest.approx(23.3)
    assert m.error is None


def test_compute_burst_metric_loss_skips_lost_probes_in_jitter():
    # the lost probe (None) must not create a fake 0 ms sample or a huge jump
    m = compute_burst_metric([10.0, None, 12.0, 11.0], method="tcp")
    assert (m.packet_count, m.received, m.loss_percent) == (4, 3, 25.0)
    assert m.min_rtt == 10.0 and m.max_rtt == 12.0
    # D = |12-10| = 2, |11-12| = 1 -> J1 = 2/16, J2 = J1 + (1-J1)/16
    j1 = 2 / 16
    assert m.jitter_rfc3550 == pytest.approx(j1 + (1 - j1) / 16, abs=1e-3)


def test_compute_burst_metric_all_lost():
    m = compute_burst_metric([None] * 12, method="icmp", error="request timed out")
    assert m.loss_percent == 100.0 and m.success is False
    assert m.median_rtt is None and m.iqr_rtt is None and m.jitter_rfc3550 is None
    assert m.error == "request timed out"


def test_compute_burst_metric_single_reply_has_zero_spread_and_no_jitter():
    m = compute_burst_metric([None, 5.0, None], method="icmp")
    assert m.median_rtt == 5.0 and m.iqr_rtt == 0.0 and m.p95_rtt == 5.0
    assert m.jitter_rfc3550 is None


def test_compute_burst_metric_is_order_independent_for_percentiles_but_not_jitter():
    a = compute_burst_metric([30.0, 10.0, 20.0, 40.0], method="icmp")
    b = compute_burst_metric([10.0, 20.0, 30.0, 40.0], method="icmp")
    assert (a.median_rtt, a.iqr_rtt, a.p95_rtt) == (b.median_rtt, b.iqr_rtt, b.p95_rtt)
    assert a.jitter_rfc3550 != b.jitter_rfc3550


def test_compute_burst_metric_rejects_empty_burst():
    with pytest.raises(ValueError):
        compute_burst_metric([], method="icmp")
