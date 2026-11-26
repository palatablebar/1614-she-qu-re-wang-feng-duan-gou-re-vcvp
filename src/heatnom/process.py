from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

from .settings import FIELDS, MODE, RESOURCE, SIGNAL_NAMES, TITLE, TARGET, WORKFLOW
from .exchange_register.service import MAX_BYTES, inspect_feed, isolation_counts
from .thermal_cutoff.contracts import Windows
from .thermal_cutoff.service import split, temporal_report
from .thermal_cutoff.visibility import exposure
from .degree_features.service import fit, prepare_all, profile_evidence
from .degree_features.audit import compare_support
from .intertie_demand.service import describe, estimate, explain, fit_model
from .nomination_replay.service import backcheck
from .nomination_replay.replay_shift import reconstruct
from .weather_drift.service import drift
from .weather_drift.coverage import confidence, missing_alignment
from .analog_evidence.service import build_library, cross_region_evidence
from .nomination_policy.service import local_bands, plan as policy_plan
from .heat_contracts.contracts import Candidate, Scenario
from .heat_contracts.service import allocate, draft
from .grid_settlement.service import decision_line, freeze
from .grid_settlement.briefing import summarize, tally


@dataclass(frozen=True, slots=True)
class PreparedBatch:
    report: object
    vintage: object
    profile: object
    fitted: object
    replay: object
    shift: object
    candidates: tuple[Candidate,...]
    analogs: object
    bands: object
    verdicts: object
    cover_ledger: object


@lru_cache(maxsize=3)
def prepare_batch(content: bytes, windows: Windows) -> PreparedBatch:
    feed = inspect_feed(content)
    vintage = split(feed.tickets,windows)
    profile = fit(vintage.train.evaluated)
    train = prepare_all(profile,vintage.train.evaluated)
    calibration = prepare_all(profile,vintage.calibration.evaluated)
    holdout = prepare_all(profile,vintage.holdout.evaluated)
    incoming = prepare_all(profile,vintage.live)
    fitted = fit_model(train,profile)
    replay = backcheck(fitted,calibration,holdout)
    shift = drift(train,incoming,replay)
    items = []
    adjustment = replay.adjustment
    for item in incoming:
        raw = estimate(fitted,item) if item.can_score() else None
        value = adjustment.apply(raw) if raw is not None else None
        sensitivity = explain(fitted,item,raw).contributions if raw is not None else ()
        interval = adjustment.interval(value) if value is not None and adjustment.native_scale else None
        plan = draft(item,value,adjustment.radius)
        items.append(Candidate(plan,value,interval,sensitivity))
    candidates = tuple(items)
    # 寒潮补证：外片区相近天气实测库 + 本片区旧班实测误差带。
    history = train + calibration + holdout
    library = build_library(history)
    bands = local_bands(replay.points, adjustment.radius)
    radius_by_region = {region: band.radius or adjustment.radius for region, band in bands.items()}
    analogs = cross_region_evidence(library, incoming, radius_by_region)
    verdicts, cover_ledger = policy_plan(candidates, bands, analogs, interruptible_off=False)
    return PreparedBatch(feed,vintage,profile,fitted,replay,shift,candidates,analogs,bands,verdicts,cover_ledger)


def load_path(path: Path) -> bytes:
    with path.open('rb') as document:
        return document.read(MAX_BYTES+1)


def scenario_view(scenario: Scenario) -> dict:
    return asdict(scenario)


def baseline_rows(batch: PreparedBatch) -> list[dict]:
    adjustment = batch.replay.adjustment
    return [{'id':row.key,'region':row.region,'day':row.day,
             'observed':row.observed,'estimate':round(adjustment.apply(row.estimate),5),
             'matured':row.confirmed} for row in batch.replay.points]


def preview(content: bytes, scenario: Scenario, windows: Windows = Windows()):
    batch = prepare_batch(content,windows)
    if scenario.region and scenario.region not in batch.shift.by_region:
        raise ValueError('所选片区在当班批次中没有单据')
    if scenario.interruptible_off:
        verdicts, cover_ledger = policy_plan(batch.candidates, batch.bands, batch.analogs, interruptible_off=True)
    else:
        verdicts, cover_ledger = batch.verdicts, batch.cover_ledger
    caps = {verdict.key: verdict.confirmed_units for verdict in verdicts}
    schedule = allocate(batch.candidates,scenario,caps)
    verdict_by_key = {verdict.key: verdict for verdict in verdicts}
    analog_by_key = batch.analogs
    report = batch.report
    isolated = [asdict(row) for row in report.rejected]
    decisions = [decision_line(row) for row in schedule.rows]
    decision_keys = {line['key'] for line in decisions}
    for line in decisions:
        line['business_evidence'] = summarize(line)
        verdict = verdict_by_key.get(line['key'])
        line['nomination_policy'] = None if verdict is None else verdict.view()
        analog = analog_by_key.get(line['key'])
        line['analog_evidence'] = None if analog is None else analog.view()
    counts = {status:sum(row['status']==status for row in decisions)
              for status in ('booked','wait','manual','normal','locked')}
    model = describe(batch.fitted)
    signal_support = compare_support((candidate.draft.signal for candidate in batch.candidates),batch.profile)
    shift = batch.shift.view()
    if missing_alignment(signal_support,shift):
        raise RuntimeError('单据缺测与漂移统计无法对账')
    visible_claims = [claim for claim in cover_ledger.claims if claim['key'] in decision_keys]
    payload = {'context':{'title':TITLE,'target':TARGET,'estimate_type':MODE,'resource':RESOURCE,'workflow':WORKFLOW,
                          'fields':[asdict(field) for field in FIELDS],'features':list(SIGNAL_NAMES)},
               'windows':windows.bounds(),'scenario':scenario_view(scenario),
               'ledger':{'booked_units':schedule.used,'free_units':schedule.left,'reserved_units':schedule.protected,
                         'by_region':schedule.by_region,'by_resource':schedule.by_resource,'status_counts':counts},
               'decisions':decisions, 'cohorts':temporal_report(batch.vintage), 'model':model,
               'replay':batch.replay.report(),'holdout_points':baseline_rows(batch), 'drift':shift,
               'intake':{**report.counts(),'isolation_reasons':isolation_counts(report),'rejected':isolated[:100]},
               'features':profile_evidence(batch.profile), 'signal_support':signal_support,
               'coverage':confidence(decisions,batch.replay.points), 'visibility':exposure(report.tickets,batch.vintage,windows),
               'business':tally(decisions),
               'cold_wave':batch.shift.cold.view(),
               'local_bands':[band.view() for band in batch.bands.values()],
               'analog_evidence':[analog_by_key[candidate.draft.signal.record.key].view()
                                  for candidate in batch.candidates
                                  if candidate.draft.signal.record.key in decision_keys],
               'nomination_policy':[verdict.view() for verdict in verdicts
                                    if verdict.key in decision_keys],
               'cover_ledger':{'storage_total':round(sum(claim['storage'] for claim in visible_claims),5),
                               'source_total':round(sum(claim['source'] for claim in visible_claims),5),
                               'claims':visible_claims},
               'shift_replay':reconstruct(report.tickets,windows).view()}
    return freeze(report.dataset_hash,batch.fitted.signature,batch.shift.readiness,payload)
