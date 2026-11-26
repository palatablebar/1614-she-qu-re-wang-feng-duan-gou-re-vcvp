from bisect import bisect_right
from collections.abc import Iterable, Sequence
from math import log

from ..degree_features.contracts import Prepared
from .contracts import ColdWave, DriftBand

CUTS = (-2.,-1.,-.25,.25,1.,2.)


def frequency(values: Iterable[float], edges: Sequence[float] = CUTS) -> tuple[int,...]:
    bins = [0] * (len(edges)+1)
    for value in values:
        bins[bisect_right(edges,value)] += 1
    return tuple(bins)


def stability_index(reference: Sequence[int], current: Sequence[int], smoothing: float = .6) -> float:
    if len(reference) != len(current) or len(reference) == 0:
        raise ValueError('分布带须有一致的上下界')
    if smoothing <= 0 or any(size < 0 for size in (*reference,*current)):
        raise ValueError('频数和平滑设置无效')
    n = len(reference)
    baseline = sum(reference)+n*smoothing
    recent = sum(current)+n*smoothing
    contribution = 0.
    for before,after in zip(reference,current,strict=True):
        previous = (before+smoothing)/baseline
        next_value = (after+smoothing)/recent
        contribution += (next_value-previous)*log(next_value/previous)
    return contribution


def draw(name: str, index: int, train: tuple[Prepared,...], probes: tuple[Prepared,...]) -> DriftBand:
    current = [signal.values[index] for signal in probes]
    reference = frequency(signal.values[index] for signal in train)
    incoming = frequency(current)
    outside = sum(abs(value)>2. for value in current)
    return DriftBand(name,stability_index(reference,incoming),reference,incoming,outside)


# 寒潮判定：外温是寒潮核心驱动。用训练窗外温的下十分位作为历史偏暖基线，
# 当班单据中跌破该基线的比例显著高于历史尾部（10%）时，判定历史样本分布偏暖。
COLD_TAIL_RATIO = .10
COLD_SHARE_TRIGGER = .25
MIN_LIVE_FOR_COLD = 5


def _ambient(signal: Prepared) -> float | None:
    return signal.record.raw[0]


def cold_wave(train: tuple[Prepared,...], live: tuple[Prepared,...]) -> ColdWave:
    history = [value for signal in train if (value := _ambient(signal)) is not None]
    current = [value for signal in live if (value := _ambient(signal)) is not None]
    if len(history) < 20 or len(current) < MIN_LIVE_FOR_COLD:
        return ColdWave(False, None, 0, len(current), 0.0, '样本不足，寒潮信号仅供观测')
    ordered = sorted(history)
    rank = int(COLD_TAIL_RATIO * (len(ordered) - 1))
    threshold = ordered[rank]
    historical_hits = sum(value <= threshold for value in history) / len(history)
    live_hits = sum(value <= threshold for value in current)
    live_share = live_hits / len(current)
    detected = live_share >= COLD_SHARE_TRIGGER and live_share > historical_hits * 2
    reason = ('历史样本分布偏暖，常规模型对寒潮峰段会低估，需外片区补证与缓报'
              if detected else '当班冷度未越过历史偏暖基线')
    return ColdWave(detected, round(threshold, 5), live_hits, len(current), round(live_share, 5), reason)
