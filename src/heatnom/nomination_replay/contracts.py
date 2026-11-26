from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ValidationPoint:
    key: str
    region: str
    day: int
    estimate: float
    observed: float
    confirmed: bool


@dataclass(frozen=True, slots=True)
class Block:
    end: float
    count: int
    positive: float

    @property
    def fraction(self) -> float:
        return self.positive / self.count


@dataclass(frozen=True, slots=True)
class Adjustment:
    name: str
    buckets: tuple[Block, ...]
    radius: float
    samples: int
    native_scale: bool

    def apply(self, value: float) -> float:
        if not self.buckets:
            return value
        previous = None
        for current in self.buckets:
            if value <= current.end:
                if previous is None or current.end <= previous.end:
                    return current.fraction
                weight = (value - previous.end) / (current.end - previous.end)
                return (1-weight)*previous.fraction + weight*current.fraction
            previous = current
        return self.buckets[-1].fraction

    def interval(self, prediction: float) -> tuple[float, float]:
        threshold = prediction + self.radius
        if not self.native_scale:
            threshold = min(1., threshold)
        return max(0., prediction - self.radius), threshold


@dataclass(frozen=True, slots=True)
class Validation:
    adjustment: Adjustment
    holdout_metrics: dict
    regions: dict
    excluded: tuple[tuple[str, int], ...]
    points: tuple[ValidationPoint, ...]

    def report(self) -> dict:
        return {'adjustment': self.adjustment.name, 'calibration_count': self.adjustment.samples,
                'radius': self.adjustment.radius,
                'calibration_blocks': [{'through': b.end, 'risk': b.fraction, 'weight': b.count}
                                       for b in self.adjustment.buckets],
                'holdout': self.holdout_metrics, 'regions': self.regions,
                'excluded': dict(self.excluded)}


@dataclass(frozen=True, slots=True)
class ReplayShift:
    """按决策时点冻结的当班购热量回放。"""

    asof: int
    train_end: int
    calibration_end: int
    holdout_end: int
    nominated_quantity: float
    visible_matured: int
    late_actual_keys: tuple[str, ...]
    late_actual_count: int
    global_radius: float
    local_bands: tuple[dict, ...]
    nominated_by_region: dict
    model_signature: str

    def view(self) -> dict:
        return {'asof': self.asof, 'windows': {'train_end': self.train_end,
                                                'calibration_end': self.calibration_end,
                                                'holdout_end': self.holdout_end},
                'nominated_quantity': self.nominated_quantity,
                'nominated_by_region': self.nominated_by_region,
                'visible_matured': self.visible_matured,
                'late_actual_count': self.late_actual_count,
                'late_actual_keys': list(self.late_actual_keys),
                'global_radius': self.global_radius, 'local_bands': list(self.local_bands),
                'model_signature': self.model_signature}
