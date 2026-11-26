from dataclasses import dataclass
import numpy as np

from .contracts import LearningRow, Probe


@dataclass(frozen=True)
class HeatDemand:
    coefficients: np.ndarray
    weather_memory: dict[str, float]
    lambda_value: float
    condition: float

    def predict(self, probe: Probe) -> float:
        shape = load_shape(probe.standard)
        return max(0., float(shape @ self.coefficients) + self.weather_memory.get(probe.region, 0.0))

    def describe(self) -> dict:
        names = ['intercept', 'heating_degree', 'return_loss', 'wind', 'reserve', 'heated_area', 'deep_cold', 'wind_by_area']
        return {'parameters': dict(zip(names, self.coefficients.tolist(), strict=True)), 'regularization': self.lambda_value,
                'linear_system_condition': self.condition, 'regional_corrections': self.weather_memory}


def load_shape(standard: tuple[float, ...]):
    degree, loss, wind, reserve, area = standard
    return np.array([1., degree, loss, wind, reserve, area, max(0, degree - .37), wind * max(0, area)])


def solve(features: np.ndarray, outcome: np.ndarray, penalty: float, eyes: np.ndarray):
    gram = features.T @ features + penalty * eyes
    return np.linalg.solve(gram, features.T @ outcome), float(np.linalg.cond(gram))


def fit_estimator(rows: tuple[LearningRow, ...]) -> HeatDemand:
    shape = np.stack([load_shape(r.probe.standard) for r in rows])
    actual = np.array([r.outcome for r in rows])
    split = max(8, int(len(rows)*.73))
    diagonals = np.diag([0, 1, 1, 1, .65, 1, 1.6, 1.8])
    tested = []
    for strength in (.1, .6, 2.5, 7.0, 18.0):
        coefficients, _ = solve(shape[:split], actual[:split], strength, diagonals)
        rejection = np.maximum(0, shape[split:] @ coefficients) - actual[split:]
        tested.append((float(np.mean(np.abs(rejection))), strength))
    _, strength = min(tested)
    coefficients, condition = solve(shape, actual, strength, diagonals)
    coefficients[4] = min(0.0, coefficients[4])
    remaining = actual - shape @ coefficients
    site_adjustment = {}
    for site in sorted({record.probe.region for record in rows}):
        indices = [i for i, record in enumerate(rows) if record.probe.region == site]
        if len(indices) >= 4:
            site_adjustment[site] = float(sum(remaining[indices])/(len(indices)+8))
    return HeatDemand(coefficients, site_adjustment, strength, condition)
