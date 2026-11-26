import pytest

from heatnom.exchange_register.service import inspect_feed
from heatnom.nomination_replay.replay_shift import reconstruct
from heatnom.thermal_cutoff.contracts import Windows


def test_replay_restores_on_duty_nominated_quantity(source_bytes):
    tickets = inspect_feed(source_bytes).tickets
    shift = reconstruct(tickets, Windows(asof=126))
    view = shift.view()
    assert view['asof'] == 126
    assert view['visible_matured'] >= 1
    assert view['nominated_quantity'] > 0
    # 分区合计与总量一致。
    assert sum(view['nominated_by_region'].values()) == pytest.approx(view['nominated_quantity'])


def test_late_actuals_are_hidden_from_current_shift(source_bytes):
    tickets = inspect_feed(source_bytes).tickets
    shift = reconstruct(tickets, Windows(asof=126))
    late = [t for t in tickets if t.outcome_day is not None and t.outcome_day >= 126]
    assert shift.late_actual_count == len(late)
    assert set(shift.late_actual_keys) == {t.key for t in late}
    # 迟到实测不能计入当班已成熟的回放购热量。
    visible = {t.key for t in tickets
               if t.outcome_day is not None and t.outcome_day < 126 and t.complete}
    assert not (set(shift.late_actual_keys) & visible)


def test_advancing_asof_only_adds_evidence_never_rewrites_prior_shift(source_bytes):
    tickets = inspect_feed(source_bytes).tickets
    early = reconstruct(tickets, Windows(asof=120)).view()
    later = reconstruct(tickets, Windows(asof=126)).view()
    assert early['visible_matured'] <= later['visible_matured']
    assert len(early['late_actual_keys']) >= len(later['late_actual_keys'])
    # 早期时点隐藏的单据，在后期才可能可见。
    assert set(later['late_actual_keys']).issubset(set(early['late_actual_keys']))


def test_replay_uses_only_visible_revisions(source_bytes):
    from dataclasses import replace
    tickets = inspect_feed(source_bytes).tickets
    base = reconstruct(tickets, Windows(asof=126))
    # 插入一条决策时点之后才到达的修订，不得改变当班回放。
    anchor = next(t for t in tickets if t.phase == 'history' and t.complete)
    late_revision = replace(anchor, revision=anchor.revision + 1, received=130, target=anchor.target + 50)
    shifted = reconstruct((*tickets, late_revision), Windows(asof=126))
    assert shifted.nominated_quantity == base.nominated_quantity
    assert shifted.model_signature == base.model_signature


def test_replay_carries_local_bands(source_bytes):
    tickets = inspect_feed(source_bytes).tickets
    view = reconstruct(tickets, Windows(asof=126)).view()
    assert view['local_bands']
    for band in view['local_bands']:
        assert band['region'] and band['source'] and band['samples'] >= 0
    assert view['global_radius'] >= 0
