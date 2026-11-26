from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AnalogCase:
    """一条外片区相近天气的历史实测。"""

    key: str
    region: str
    pool: str
    day: int
    distance: float
    observed: float
    ambient: float
    wind: float

    def row(self) -> dict:
        return {'key': self.key, 'region': self.region, 'pool': self.pool, 'day': self.day,
                'weather_distance': round(self.distance, 5), 'observed': round(self.observed, 5),
                'ambient': round(self.ambient, 3), 'wind': round(self.wind, 3)}


@dataclass(frozen=True, slots=True)
class AnalogEvidence:
    """当班单据的外片区补证结论。

    status:
      supported    外片区实测足以补证，proxy 可作为模型失真时的旁证预测
      weak         有近似样本但数量或贴近度不足，只能留档不能定量
      no_analog    没有跨片区的相近天气样本
    """

    key: str
    region: str
    status: str
    proxy: float | None
    radius: float | None
    case_count: int
    donor_regions: tuple[str, ...]
    nearest_distance: float | None
    cases: tuple[AnalogCase, ...]

    def view(self) -> dict:
        return {'key': self.key, 'region': self.region, 'status': self.status,
                'proxy': None if self.proxy is None else round(self.proxy, 5),
                'analog_radius': None if self.radius is None else round(self.radius, 5),
                'case_count': self.case_count, 'donor_regions': list(self.donor_regions),
                'nearest_distance': None if self.nearest_distance is None else round(self.nearest_distance, 5),
                'cases': [case.row() for case in self.cases]}
