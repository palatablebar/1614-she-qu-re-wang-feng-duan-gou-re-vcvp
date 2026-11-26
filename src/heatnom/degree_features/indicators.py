from math import sqrt


def derive(values: tuple[float, ...]) -> tuple[float, ...]:
    """从换热片区申报原始读数生成五个模型轴。"""
    ambient, area, return_temp, reserve, wind, occupancy = values
    degree_hours = max(0.0, 19 - ambient) * 4.0
    active_area = area * occupancy / 100
    windchill = max(0.0, 7 - ambient) * sqrt(wind) * active_area / 10
    loss = max(0.0, 49 - return_temp) * area / 16
    protected_reserve = min(reserve, area * 3.0)
    return degree_hours * active_area / 40, loss, windchill, protected_reserve, active_area
