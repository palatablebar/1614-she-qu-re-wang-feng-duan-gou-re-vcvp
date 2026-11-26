from math import sqrt
from statistics import median

from ..degree_features.contracts import Prepared
from ..settings import FIELDS
from .contracts import AnalogCase, AnalogEvidence

# 天气相近判定：外温为主轴（寒潮核心驱动），风速为次轴。
AMBIENT_SCALE_FALLBACK = 8.0
WIND_SCALE_FALLBACK = 6.0
MATCH_LIMIT = 1.0           # 标准化天气距离上限，超过即不算相近
NEAREST_COUNT = 5           # 留档的最近邻条数
MIN_CASES = 3               # 少于该数量只能弱证据留档
WEAK_DISTANCE = .55         # 最近邻贴近度不足时降为弱证据
MIN_DONOR_REGIONS = 2       # 单一外片区不足以独立补证
PROXY_COVERAGE = .82        # 旁证误差带沿用本地校准带的名义覆盖水平


def _index(key: str) -> int:
    return next(i for i, field in enumerate(FIELDS) if field.key == key)


AMBIENT_I = _index('ambient')
WIND_I = _index('wind')
AREA_I = _index('area')


def _robust_scale(values: list[float], fallback: float) -> float:
    if not values:
        return fallback
    center = median(values)
    spread = 1.4826 * median(abs(v - center) for v in values)
    return spread if spread > 1e-9 else fallback


class WeatherLibrary:
    """跨片区历史实测库，只收录完整且结果已确认的历史单据。"""

    def __init__(self, history: tuple[Prepared, ...]):
        donors = [item for item in history
                  if item.record.region and item.record.target is not None and item.record.complete
                  and item.record.raw[AMBIENT_I] is not None and item.record.raw[WIND_I] is not None]
        ambients = [item.record.raw[AMBIENT_I] for item in donors]
        winds = [item.record.raw[WIND_I] for item in donors]
        self.ambient_scale = _robust_scale(ambients, AMBIENT_SCALE_FALLBACK)
        self.wind_scale = _robust_scale(winds, WIND_SCALE_FALLBACK)
        self.donors = tuple(donors)

    def distance(self, probe: Prepared, donor: Prepared) -> float:
        ambient = (probe.raw[AMBIENT_I] - donor.record.raw[AMBIENT_I]) / self.ambient_scale
        wind = (probe.raw[WIND_I] - donor.record.raw[WIND_I]) / self.wind_scale
        return sqrt(ambient * ambient + wind * wind)

    def lookup(self, probe: Prepared, local_radius: float | None) -> AnalogEvidence:
        record = probe.record
        if record.raw[AMBIENT_I] is None:
            return AnalogEvidence(record.key, record.region, 'no_analog', None, None, 0, (), None, ())
        ranked = sorted(((self.distance(probe, donor), donor) for donor in self.donors
                         if donor.record.region != record.region),
                        key=lambda pair: (pair[0], pair[1].record.key))
        close = [(distance, donor) for distance, donor in ranked if distance <= MATCH_LIMIT]
        if not close:
            return AnalogEvidence(record.key, record.region, 'no_analog', None, None, 0, (), None, ())
        chosen = close[:NEAREST_COUNT]
        cases = tuple(AnalogCase(donor.record.key, donor.record.region, donor.record.pool, donor.record.day,
                                 distance, float(donor.record.target), donor.record.raw[AMBIENT_I],
                                 donor.record.raw[WIND_I])
                      for distance, donor in chosen)
        donor_regions = tuple(sorted({donor.record.region for _, donor in chosen}))
        nearest = chosen[0][0]
        if len(close) < MIN_CASES or nearest > WEAK_DISTANCE or len(donor_regions) < MIN_DONOR_REGIONS:
            return AnalogEvidence(record.key, record.region, 'weak', None, None, len(close),
                                  donor_regions, nearest, cases)
        # 旁证预测取相近样本实测的加权均值，距离越近权重越高。
        weights = [1.0 / (distance + .25) for distance, _ in chosen]
        proxy = sum(w * donor.record.target for w, (_, donor) in zip(weights, chosen, strict=True)) / sum(weights)
        # 旁证误差带来自相近样本本身的离散度；本片区误差带仅在可用时兜底，
        # 未建档片区没有本片区实测，不得把零值或全局带直接当作旁证带宽。
        spread = max(abs(donor.record.target - proxy) for _, donor in chosen)
        radius = max(spread, local_radius) if local_radius else spread
        return AnalogEvidence(record.key, record.region, 'supported', float(proxy), float(radius),
                              len(close), donor_regions, nearest, cases)


def build_library(history: tuple[Prepared, ...]) -> WeatherLibrary:
    return WeatherLibrary(history)


def cross_region_evidence(library: WeatherLibrary, probes: tuple[Prepared, ...],
                          local_radius: dict[str, float]) -> dict[str, AnalogEvidence]:
    return {probe.record.key: library.lookup(probe, local_radius.get(probe.record.region))
            for probe in probes}
