from dataclasses import replace

import pytest

from heatnom.analog_evidence.contracts import AnalogCase, AnalogEvidence
from heatnom.heat_contracts.contracts import Scenario
from heatnom.nomination_policy.contracts import LocalBand, PolicyVerdict
from heatnom.nomination_policy.service import (LOCAL_MIN_SAMPLES, CoverLedger, evaluate,
                                               local_bands, plan)
from heatnom.process import prepare_batch, preview
from heatnom.settings import DEFAULT_BUDGET
from heatnom.thermal_cutoff.contracts import Windows


@pytest.fixture(scope='session')
def batch(source_bytes):
    return prepare_batch(source_bytes, Windows())


def _bookable(batch):
    return next(c for c in batch.candidates if c.estimate is not None and c.draft.units >= 15)


def test_local_band_uses_only_same_region_actuals(batch):
    bands = local_bands(batch.replay.points, batch.replay.adjustment.radius)
    regions = {point.region for point in batch.replay.points if point.confirmed}
    assert set(bands) == regions
    for region, band in bands.items():
        own = [p for p in batch.replay.points if p.confirmed and p.region == region]
        assert band.samples == len(own)
        if len(own) >= LOCAL_MIN_SAMPLES:
            assert band.source == '本片区旧班实测分位'
            assert band.radius is not None


def test_local_band_falls_back_when_region_has_too_few_samples(batch):
    # 只保留每个片区至多 2 条确认点，全部低于本片区最低样本数。
    kept: dict[str, list] = {}
    for point in batch.replay.points:
        if point.confirmed:
            kept.setdefault(point.region, []).append(point)
    sparse = tuple(item for rows in kept.values() for item in rows[:2])
    bands = local_bands(sparse, 7.5)
    assert bands and len(bands) == len(kept)
    for band in bands.values():
        assert band.samples < LOCAL_MIN_SAMPLES
        assert band.radius == 7.5 and '全局' in band.source


def test_band_crossing_minimum_holds_the_uncertain_top_slice(batch):
    candidate = _bookable(batch)
    # 极宽误差带必然跨过最小申报量。
    wide = LocalBand(candidate.draft.signal.record.region, 10_000.0, 20, '本片区旧班实测分位')
    verdict = evaluate(candidate, wide, None, False, CoverLedger())
    assert verdict.band_crosses_minimum
    assert verdict.confirmed_units == candidate.draft.minimum
    assert verdict.held_units == candidate.draft.units - candidate.draft.minimum
    assert any('跨过最小申报量' in reason for reason in verdict.reasons)


def test_tight_band_confirms_full_request(batch):
    candidate = replace(_bookable(batch), estimate=float(_bookable(batch).draft.units + 8))
    tight = LocalBand(candidate.draft.signal.record.region, 0.5, 20, '本片区旧班实测分位')
    verdict = evaluate(candidate, tight, None, False, CoverLedger())
    assert not verdict.band_crosses_minimum
    assert verdict.confirmed_units == candidate.draft.units and verdict.held_units == 0


def test_interruptible_shutdown_keeps_firm_minimum_but_holds_flexible_volume(batch):
    candidate = replace(_bookable(batch), estimate=float(_bookable(batch).draft.units + 8))
    tight = LocalBand(candidate.draft.signal.record.region, 0.5, 20, '本片区旧班实测分位')
    normal = evaluate(candidate, tight, None, False, CoverLedger())
    stopped = evaluate(candidate, tight, None, True, CoverLedger())
    assert normal.confirmed_units == candidate.draft.units
    assert stopped.confirmed_units == candidate.draft.minimum
    assert stopped.held_units == candidate.draft.units - candidate.draft.minimum
    assert any('可中断合同全停' in reason for reason in stopped.reasons)


def test_insufficient_evidence_still_reports_firm_minimum(batch):
    candidate = replace(_bookable(batch), estimate=None)
    verdict = evaluate(candidate, None, None, False, CoverLedger())
    assert verdict.evidence == 'insufficient'
    assert verdict.confirmed_units == candidate.draft.minimum
    assert verdict.held_units == candidate.draft.units - candidate.draft.minimum


def test_supported_analog_revives_otherwise_unscorable_ticket(batch):
    unscored = next(c for c in batch.candidates if c.estimate is None)
    analog = batch.analogs[unscored.draft.signal.record.key]
    if analog.status != 'supported':
        analog = AnalogEvidence(unscored.draft.signal.record.key, unscored.draft.signal.record.region,
                                'supported', 20.0, 4.0, 6, ('河东片区', '林南片区'), 0.3,
                                (AnalogCase('x', '河东片区', 'TIE-1', 1, 0.3, 20.0, -12.0, 8.0),))
    verdict = evaluate(unscored, None, analog, False, CoverLedger())
    assert verdict.evidence == 'analog'
    assert verdict.confirmed_units >= unscored.draft.minimum
    assert any('外片区' in reason for reason in verdict.reasons)


def test_weak_analog_is_treated_as_insufficient(batch):
    unscored = next(c for c in batch.candidates if c.estimate is None)
    weak = AnalogEvidence(unscored.draft.signal.record.key, unscored.draft.signal.record.region,
                          'weak', None, None, 2, ('河东片区',), 0.9, ())
    verdict = evaluate(unscored, None, weak, False, CoverLedger())
    assert verdict.evidence == 'insufficient'
    assert verdict.confirmed_units == unscored.draft.minimum


def test_cover_ledger_counts_each_guarantee_pool_only_once():
    ledger = CoverLedger()
    first = ledger.claim('a', storage_want=8.0, source_want=5.0, storage_cap=8.0, source_cap=5.0)
    second = ledger.claim('b', storage_want=8.0, source_want=5.0, storage_cap=8.0, source_cap=5.0)
    assert first['storage'] == 8 and first['source'] == 5
    assert second['storage'] == 0 and second['source'] == 0
    assert second['storage_duplicate'] == 8 and second['source_duplicate'] == 5
    assert ledger.storage_used == 8 and ledger.source_used == 5


def test_plan_preserves_candidate_order_and_covers_every_key(batch):
    verdicts, ledger = plan(batch.candidates, batch.bands, batch.analogs)
    assert [v.key for v in verdicts] == [c.draft.signal.record.key for c in batch.candidates]
    assert all(isinstance(v, PolicyVerdict) for v in verdicts)
    assert len(ledger.claims) == len(batch.candidates)
    assert all(0 <= v.confirmed_units <= v.requested for v in verdicts)
    assert all(v.confirmed_units + v.held_units == v.requested for v in verdicts)


def test_preview_exposes_policy_and_cover_ledger(source_bytes):
    payload = preview(source_bytes, Scenario(DEFAULT_BUDGET)).payload
    keys = {row['key'] for row in payload['decisions']}
    assert {v['key'] for v in payload['nomination_policy']} == keys
    assert payload['cover_ledger']['storage_total'] >= 0
    assert len(payload['cover_ledger']['claims']) == len(keys)
    # 派工量永远不超过裁决确认量。
    caps = {v['key']: v['confirmed_units'] for v in payload['nomination_policy']}
    assert all(row['units'] <= caps[row['key']] for row in payload['decisions'])


def test_interruptible_off_scenario_reduces_or_keeps_booking(source_bytes):
    normal = preview(source_bytes, Scenario(400)).payload
    stopped = preview(source_bytes, Scenario(400, interruptible_off=True)).payload
    assert stopped['ledger']['booked_units'] <= normal['ledger']['booked_units']
    for verdict in stopped['nomination_policy']:
        assert verdict['confirmed_units'] <= verdict['minimum']
    # 保供下限在两个方案里都被保留。
    normal_min = {v['key']: v['minimum'] for v in normal['nomination_policy']}
    for verdict in stopped['nomination_policy']:
        if normal_min[verdict['key']] > 0:
            assert verdict['confirmed_units'] <= verdict['requested']
