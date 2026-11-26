from dataclasses import replace

from heatnom.degree_features.service import prepare_all
from heatnom.weather_drift.distribution import cold_wave
from heatnom.weather_drift.service import judge
from heatnom.weather_drift.contracts import Readiness


def test_cold_wave_flags_warm_biased_history(prepared):
    train = prepare_all(prepared.profile, prepared.vintage.train.evaluated)
    frozen = tuple(replace(t, raw=(-15.0, *t.raw[1:])) for t in prepared.vintage.live)
    report = cold_wave(train, prepare_all(prepared.profile, frozen))
    assert report.detected
    assert report.live_cold_share >= .25
    assert '偏暖' in report.reason


def test_mild_shift_does_not_raise_cold_wave(prepared):
    train = prepare_all(prepared.profile, prepared.vintage.train.evaluated)
    report = cold_wave(train, prepare_all(prepared.profile, prepared.vintage.live))
    assert not report.detected


def test_cold_wave_needs_enough_live_samples(prepared):
    train = prepare_all(prepared.profile, prepared.vintage.train.evaluated)
    frozen = tuple(replace(t, raw=(-15.0, *t.raw[1:])) for t in prepared.vintage.live[:3])
    report = cold_wave(train, prepare_all(prepared.profile, frozen))
    assert not report.detected and '样本不足' in report.reason


def test_cold_wave_view_round_trips(prepared):
    train = prepare_all(prepared.profile, prepared.vintage.train.evaluated)
    view = cold_wave(train, prepare_all(prepared.profile, prepared.vintage.live)).view()
    assert set(view) == {'detected', 'ambient_threshold', 'live_cold_cases', 'live_cases',
                         'live_cold_share', 'reason'}


def test_judge_surfaces_cold_wave_reason_without_blocking():
    phase, reasons = judge(12, 0, 0, 30, 30, cold_detected=True)
    assert phase == Readiness.REVIEW
    assert any('寒潮' in reason for reason in reasons)


def test_drift_payload_contains_cold_wave(prepared):
    view = prepared.shift.view()
    assert 'cold_wave' in view
    assert set(view['cold_wave']) == {'detected', 'ambient_threshold', 'live_cold_cases',
                                      'live_cases', 'live_cold_share', 'reason'}
