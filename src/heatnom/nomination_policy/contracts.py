from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LocalBand:
    """本片区旧班实测验过的误差带。"""

    region: str
    radius: float | None
    samples: int
    source: str

    def view(self) -> dict:
        return {'region': self.region, 'radius': None if self.radius is None else round(self.radius, 5),
                'samples': self.samples, 'source': self.source}


@dataclass(frozen=True, slots=True)
class PolicyVerdict:
    """单条单据的峰段申报裁决。

    confirmed_units: 拿得准、照常保供申报的量（含必须兑现的保供下限）
    held_units:      拿不准先缓报的量
    """

    key: str
    region: str
    evidence: str            # local | analog | insufficient
    band_crosses_minimum: bool
    lower_need: float
    upper_need: float
    requested: int
    minimum: int
    confirmed_units: int
    held_units: int
    reasons: tuple[str, ...]

    def view(self) -> dict:
        return {'key': self.key, 'region': self.region, 'evidence': self.evidence,
                'band_crosses_minimum': self.band_crosses_minimum,
                'need_interval': [round(self.lower_need, 5), round(self.upper_need, 5)],
                'requested': self.requested, 'minimum': self.minimum,
                'confirmed_units': self.confirmed_units, 'held_units': self.held_units,
                'reasons': list(self.reasons)}
