from math import ceil

from ..analog_evidence.contracts import AnalogEvidence
from ..heat_contracts.contracts import Candidate
from ..nomination_replay.calibration import conformal_radius
from ..nomination_replay.contracts import ValidationPoint
from .contracts import LocalBand, PolicyVerdict

LOCAL_MIN_SAMPLES = 7          # 本片区旧班实测低于该数，误差带不可用，转全局带并标注
COVERAGE = .82


def local_bands(points: tuple[ValidationPoint, ...], global_radius: float,
                min_samples: int = LOCAL_MIN_SAMPLES) -> dict[str, LocalBand]:
    """误差带只用本片区旧班实测分位；样本不足时退回全局带并显式标注。"""

    grouped: dict[str, list[ValidationPoint]] = {}
    for point in points:
        if point.confirmed:
            grouped.setdefault(point.region, []).append(point)
    bands: dict[str, LocalBand] = {}
    for region in sorted(grouped):
        rows = grouped[region]
        if len(rows) >= min_samples:
            bands[region] = LocalBand(region, conformal_radius(rows, COVERAGE), len(rows), '本片区旧班实测分位')
        else:
            bands[region] = LocalBand(region, global_radius, len(rows), '本片区样本不足，借用全局校准带')
    return bands


class CoverLedger:
    """储热与热源保证量各只占一次。

    两个保证资源池跨单据记账：同一资源池已经被前面单据占用的容量，不能在
    后续单据上再次抵扣。每次 claim 返回本次实际占用量和被拒的重复量，
    供审计核对「各只占一次」。
    """

    def __init__(self) -> None:
        self.storage_used = 0.0
        self.source_used = 0.0
        self.claims: list[dict] = []

    def claim(self, key: str, storage_want: float, source_want: float,
              storage_cap: float, source_cap: float) -> dict:
        storage = max(0.0, min(storage_want, max(0.0, storage_cap - self.storage_used)))
        storage_duplicate = max(0.0, storage_want - storage)
        self.storage_used += storage
        source = max(0.0, min(source_want, max(0.0, source_cap - self.source_used)))
        source_duplicate = max(0.0, source_want - source)
        self.source_used += source
        entry = {'key': key, 'storage': storage, 'source': source,
                 'storage_duplicate': storage_duplicate, 'source_duplicate': source_duplicate}
        self.claims.append(entry)
        return entry


def _resource_caps(candidate: Candidate) -> tuple[float, float]:
    raw = candidate.draft.signal.raw
    # raw 顺序与 FIELDS 一致：ambient, area, return_temp, reserve, wind, occupancy
    # 储热保证量取储热余量；热源保证量按面积折成单位面积保证（0.06 MWh/万㎡）。
    reserve = raw[3] or 0.0
    area = raw[1] or 0.0
    return max(0.0, reserve), max(0.0, area * 0.06)


def evaluate(candidate: Candidate, band: LocalBand | None, analog: AnalogEvidence | None,
             interruptible_off: bool, ledger: CoverLedger) -> PolicyVerdict:
    draft = candidate.draft
    record = draft.signal.record
    requested, minimum = draft.units, draft.minimum
    reasons: list[str] = []
    storage_cap, source_cap = _resource_caps(candidate)
    # 保证量先在本单据内各占一次，再由 ledger 拦截跨单据重复占用。
    ledger.claim(record.key, min(storage_cap, requested), min(source_cap, requested),
                 storage_cap, source_cap)

    def finish(evidence: str, lower: float, upper: float, confirmed: int,
               extra: tuple[str, ...] = ()) -> PolicyVerdict:
        held = requested - confirmed
        crosses = minimum > 0 and lower < minimum < upper
        notes = list(extra)
        if crosses:
            notes.append(f'误差带跨过最小申报量 {minimum} MWh，超出保供下限的量先缓报')
        if held > 0 and not crosses:
            notes.append('证据不足，超出已确认保供的量先缓报')
        return PolicyVerdict(record.key, record.region, evidence, crosses, lower, upper,
                             requested, minimum, confirmed, held, tuple(dict.fromkeys(notes)))

    def apply_firm(confirmed: int) -> int:
        if interruptible_off:
            # 可中断合同全停：保供必须兑现，可中断补量一律缓报。
            reasons.append('可中断合同全停，仅兑现保供下限，可中断补量缓报')
            return min(confirmed, minimum)
        return confirmed

    # 模型可评分：以本片区误差带判定拿得准的区间。
    if candidate.estimate is not None and band is not None and band.radius is not None:
        lower_need = max(0.0, candidate.estimate - band.radius)
        upper_need = candidate.estimate + band.radius
        evidence = 'local' if band.samples >= LOCAL_MIN_SAMPLES else 'analog'
        if band.samples < LOCAL_MIN_SAMPLES:
            reasons.append('本片区旧班实测不足，误差带借用全局校准，定量结论降级')
        # 误差带下界支撑多少，就确认多少；保供下限始终兜底。
        confirmed = min(requested, max(minimum, ceil(lower_need)))
        return finish(evidence, lower_need, upper_need, apply_firm(confirmed), tuple(reasons))

    # 模型失真（偏暖分布/未建档/越支撑）：外片区相近天气实测只能补证，
    # 且旁证强度必须达到 supported；weak/no_analog 一律按证据不足处理。
    if analog is not None and analog.status == 'supported' and analog.proxy is not None:
        lower_need = max(0.0, analog.proxy - analog.radius)
        upper_need = analog.proxy + analog.radius
        confirmed = min(requested, max(minimum, ceil(lower_need)))
        reasons.append(f'模型无法覆盖，采用 {len(analog.donor_regions)} 个外片区 {analog.case_count} 条相近天气实测补证')
        return finish('analog', lower_need, upper_need, apply_firm(confirmed), tuple(reasons))

    # 证据不够：保供下限照常报（保供责任不因证据不足而免除），其余缓报。
    fallback_need = max(0.0, candidate.estimate or 0.0)
    confirmed = min(requested, minimum)
    reasons.append('模型与外片区补证均不足，仅按已确认保供下限申报')
    return finish('insufficient', 0.0, max(fallback_need, float(minimum)),
                  apply_firm(confirmed), tuple(reasons))


def plan(candidates: tuple[Candidate, ...], bands: dict[str, LocalBand],
         analogs: dict[str, AnalogEvidence], interruptible_off: bool = False
         ) -> tuple[tuple[PolicyVerdict, ...], CoverLedger]:
    ledger = CoverLedger()
    verdicts = []
    for candidate in sorted(candidates, key=lambda item: (-item.draft.minimum, item.draft.signal.record.key)):
        region = candidate.draft.signal.record.region
        verdict = evaluate(candidate, bands.get(region), analogs.get(candidate.draft.signal.record.key),
                           interruptible_off, ledger)
        verdicts.append(verdict)
    order = {candidate.draft.signal.record.key: index for index, candidate in enumerate(candidates)}
    return tuple(sorted(verdicts, key=lambda verdict: order[verdict.key])), ledger
