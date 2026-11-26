from collections import defaultdict

from ..exchange_register.contracts import Hold
from ..thermal_cutoff.contracts import Windows
from ..thermal_cutoff.revisions import resolve_revisions
from ..degree_features.service import fit, prepare_all
from ..intertie_demand.service import fit_model
from ..nomination_replay.calibration import fit_adjustment
from ..nomination_replay.service import valid_points
from ..nomination_policy.service import local_bands
from .contracts import ReplayShift


def reconstruct(tickets, windows: Windows) -> ReplayShift:
    """按指定决策时点回放：只使用该时点可见的单据与结果，还原当班购热量。

    迟到的实测（outcome_day >= asof）在该时点不可见，只能进入后续班次，
    因此本回放不允许它们改变当班误差带或申报结论。
    """

    snapshot = resolve_revisions(tickets, windows.asof)
    accepted = snapshot.accepted
    early = resolve_revisions(tickets, windows.train_end)
    train_tickets = tuple(t for t in early.accepted if t.phase == 'history' and t.hold == Hold.CLEAR
                          and t.complete and t.outcome_day is not None and t.outcome_day < windows.train_end)
    profile = fit(train_tickets)
    train_prepared = prepare_all(profile, train_tickets)
    model = fit_model(train_prepared, profile)

    mid = resolve_revisions(tickets, windows.calibration_end)
    calibration_tickets = tuple(t for t in mid.accepted if t.phase == 'history' and t.hold == Hold.CLEAR)
    calibration = prepare_all(profile, calibration_tickets)
    cal_points = valid_points(model, calibration)
    adjustment = fit_adjustment(cal_points, True, False)

    history_prepared = prepare_all(profile, tuple(t for t in accepted if t.phase == 'history'))
    hold_points = valid_points(model, history_prepared)
    bands = local_bands(tuple(hold_points), adjustment.radius)

    visible_outcomes = [p for p in hold_points
                        if p.confirmed and p.day < windows.asof and p.day >= windows.holdout_end]
    nominated = sum(p.observed for p in visible_outcomes)
    late_actuals = [t for t in accepted
                    if t.phase == 'history' and t.outcome_day is not None and t.outcome_day >= windows.asof]
    by_region: dict[str, float] = defaultdict(float)
    for point in visible_outcomes:
        by_region[point.region] += point.observed

    return ReplayShift(
        asof=windows.asof,
        train_end=windows.train_end,
        calibration_end=windows.calibration_end,
        holdout_end=windows.holdout_end,
        nominated_quantity=round(nominated, 5),
        visible_matured=len(visible_outcomes),
        late_actual_keys=tuple(sorted(t.key for t in late_actuals)),
        late_actual_count=len(late_actuals),
        global_radius=round(adjustment.radius, 5),
        local_bands=tuple(band.view() for band in bands.values()),
        nominated_by_region={region: round(total, 5) for region, total in sorted(by_region.items())},
        model_signature=model.signature,
    )
