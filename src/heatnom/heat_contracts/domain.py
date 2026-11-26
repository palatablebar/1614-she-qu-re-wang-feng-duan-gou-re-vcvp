from math import ceil

from ..degree_features.contracts import Prepared
from .contracts import Disposition, Draft


def interpret(resolved: Prepared, value: float, uncertainty: float, manual: bool = False) -> Draft:
    probe = resolved.record

    def block(reason: str) -> Draft:
        return Draft(resolved,Disposition.MANUAL,0,0,1,0,0,reason,'')

    def normal(reason: str) -> Draft:
        return Draft(resolved,Disposition.NORMAL,0,0,1,0,0,reason,'')

    def proposal(qty: int, priority: float, minutes: int, reason: str, resource: str,
                 *, minimum: int | None = None, unit: int = 1) -> Draft:
        state = Disposition.MANUAL if manual else Disposition.BOOKED
        return Draft(resolved,state,qty,qty if minimum is None else minimum,
                     unit,priority,minutes,reason,resource)

    outside, area, return_temp, reserve, wind, occupancy = resolved.raw
    if return_temp < 35 and probe.window < 29:
        return block('低回温且缺抄表确认窗，保供侧人工裁定')
    shortage = max(0.0, value)
    if shortage < 7.0 and not manual:
        return normal('预测缺口低于可申报交易块')
    firm_load = 0.5 + occupancy / 210
    mandatory = ceil(shortage * firm_load)
    requested = min(37, ceil(shortage + min(4, max(0, 44-return_temp))))
    if manual:
        # 模型不可用时按可申报块给出保供基线，实际数量由外片区补证裁决后再放开。
        requested = max(7, requested)
        mandatory = max(1, mandatory)
        reason = '模型无法覆盖当前输入，待外片区相近天气补证后核定保供量'
    else:
        reason = f'保供申报基线 {min(mandatory, requested)} MWh，剩余可按外送调度'
    return proposal(max(1, requested), area * .12 + mandatory + max(0, 3-outside) * 1.4,
                    14, reason, '外购合同段',
                    minimum=max(1, min(mandatory, requested)))
