from dataclasses import dataclass
from enum import StrEnum


class Readiness(StrEnum):
    READY = 'ready'
    REVIEW = 'review'
    BLOCK = 'blocked'


@dataclass(frozen=True, slots=True)
class DriftBand:
    feature: str
    psi: float
    reference: tuple[int,...]
    live: tuple[int,...]
    unseen_outside: int

    def rows(self) -> dict:
        return {'feature': self.feature, 'psi': self.psi, 'reference': list(self.reference),
                'live': list(self.live), 'outside_seen_axis': self.unseen_outside}


@dataclass(frozen=True, slots=True)
class ColdWave:
    detected: bool
    ambient_threshold: float | None
    live_cold_cases: int
    live_cases: int
    live_cold_share: float
    reason: str

    def view(self) -> dict:
        return {'detected': self.detected, 'ambient_threshold': self.ambient_threshold,
                'live_cold_cases': self.live_cold_cases, 'live_cases': self.live_cases,
                'live_cold_share': self.live_cold_share, 'reason': self.reason}


@dataclass(frozen=True, slots=True)
class MarketShift:
    rows: int
    unknown_regions: dict[str,int]
    missing_fields: dict[str,int]
    by_region: dict[str,dict]
    flags: dict[str,int]
    bands: tuple[DriftBand,...]
    readiness: Readiness
    reasons: tuple[str,...]
    cold: ColdWave

    def view(self) -> dict:
        return {'live_count': self.rows,'unknown_regions': self.unknown_regions,'missing_fields': self.missing_fields,
                'affected_regions': self.by_region,'flags': self.flags, 'bands':[band.rows() for band in self.bands],
                'status': self.readiness, 'reasons': list(self.reasons), 'cold_wave': self.cold.view()}
