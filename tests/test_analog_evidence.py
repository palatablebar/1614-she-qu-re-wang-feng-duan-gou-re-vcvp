from dataclasses import replace
from math import isclose

import pytest

from heatnom.analog_evidence.service import (MATCH_LIMIT, MIN_CASES, MIN_DONOR_REGIONS,
                                             WeatherLibrary, build_library)
from heatnom.degree_features.service import prepare_all


def _library(prepared):
    history = (prepared.vintage.train.evaluated + prepared.vintage.calibration.evaluated
               + prepared.vintage.holdout.evaluated)
    return build_library(prepare_all(prepared.profile, history))


def _live(prepared):
    return prepare_all(prepared.profile, prepared.vintage.live)


def test_library_only_keeps_complete_confirmed_history(prepared):
    library = _library(prepared)
    assert library.donors
    assert all(donor.record.complete and donor.record.target is not None for donor in library.donors)
    assert all(donor.record.phase == 'history' for donor in library.donors)


def test_analog_never_uses_the_probes_own_region(prepared):
    library = _library(prepared)
    for probe in _live(prepared):
        evidence = library.lookup(probe, 5.0)
        assert probe.record.region not in evidence.donor_regions
        assert all(case.region != probe.record.region for case in evidence.cases)


def test_supported_analog_requires_enough_cases_and_two_donor_regions(prepared):
    library = _library(prepared)
    supported = [probe for probe in _live(prepared)
                 if library.lookup(probe, 5.0).status == 'supported']
    assert supported
    for probe in supported:
        evidence = library.lookup(probe, 5.0)
        assert evidence.case_count >= MIN_CASES
        assert len(evidence.donor_regions) >= MIN_DONOR_REGIONS
        assert evidence.nearest_distance is not None and evidence.nearest_distance <= MATCH_LIMIT
        assert evidence.proxy is not None and evidence.radius is not None
        assert evidence.radius > 0


def test_unseen_region_gets_cross_region_evidence_not_a_fake_local_band(prepared):
    library = _library(prepared)
    unseen = next(probe for probe in _live(prepared) if not probe.can_score())
    evidence = library.lookup(unseen, None)
    assert evidence.key == unseen.record.key
    assert evidence.status in {'supported', 'weak', 'no_analog'}
    if evidence.status == 'supported':
        # 未建档片区没有本片区实测，半径只能来自外片区样本离散度。
        assert evidence.radius == pytest.approx(
            max(abs(case.observed - evidence.proxy) for case in evidence.cases))


def test_missing_ambient_has_no_analog(prepared):
    library = _library(prepared)
    probe = replace(_live(prepared)[0], record=replace(_live(prepared)[0].record,
                                                        raw=(None, *_live(prepared)[0].record.raw[1:])))
    evidence = library.lookup(probe, 5.0)
    assert evidence.status == 'no_analog' and evidence.cases == () and evidence.proxy is None


def test_tightening_distance_weakens_or_removes_evidence(prepared):
    library = _library(prepared)
    probe = _live(prepared)[0]
    full = library.lookup(probe, 5.0)
    # 只保留距离极近的 donor，强制触发弱证据或无证据分支。
    stripped = WeatherLibrary.__new__(WeatherLibrary)
    stripped.ambient_scale = library.ambient_scale
    stripped.wind_scale = library.wind_scale
    stripped.donors = tuple(d for d in library.donors
                            if d.record.region != probe.record.region
                            and library.distance(probe, d) < 0.01)
    weak = stripped.lookup(probe, 5.0)
    if full.status == 'no_analog':
        assert weak.status == 'no_analog'
    else:
        assert weak.status in {'weak', 'no_analog'}
        if weak.status == 'weak':
            assert weak.proxy is None and weak.radius is None


def test_analog_view_is_json_ready(prepared):
    library = _library(prepared)
    evidence = library.lookup(_live(prepared)[0], 5.0)
    view = evidence.view()
    assert set(view) >= {'key', 'region', 'status', 'proxy', 'analog_radius', 'cases',
                         'case_count', 'donor_regions', 'nearest_distance'}
    assert all(set(case) >= {'key', 'region', 'weather_distance', 'observed'} for case in view['cases'])
    import json
    assert json.dumps(view, ensure_ascii=False)


def test_distance_is_symmetric_and_nonnegative(prepared):
    library = _library(prepared)
    probe = _live(prepared)[0]
    donor = next(d for d in library.donors if d.record.region != probe.record.region)
    forward = library.distance(probe, donor)
    backward = library.distance(donor, probe)
    assert forward >= 0 and isclose(forward, backward)
