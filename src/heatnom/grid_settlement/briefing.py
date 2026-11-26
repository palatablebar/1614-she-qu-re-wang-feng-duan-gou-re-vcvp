from collections import defaultdict
from math import isfinite, sqrt

from ..settings import EXPOSURE_UNIT, FIELDS


def reading(key: str, label: str, value: float, unit: str, trigger: float, direction: str) -> dict:
    number = float(value)
    boundary = float(trigger)
    if not isfinite(number) or not isfinite(boundary):
        raise ValueError(f'{label} 指标不是有限量')
    if direction not in ('high','low'):
        raise ValueError('证据边界方向不明')
    crossed = number > boundary if direction=='high' else number < boundary
    return {'field':key,'label':label,'value':round(number,3),'unit':unit,'trigger':round(boundary,3),
            'direction':direction,'exceeded':crossed}


def summarize(record: dict) -> dict:
    fields = record['raw']
    if any(fields[item.key] is None for item in FIELDS):
        return {'checks':[],'work':None,'exposure':None, 'work_label':None, 'status':'读数不全'}
    values = tuple(fields[item.key] for item in FIELDS)
    window = record['window']
    prediction = record.get('estimate')
    ambient,area,return_temp,reserve,wind,occupancy = values
    heat = max(0.,float(prediction or 0))
    firm = min(record['requested'], record['minimum'])
    contracted = min(firm,record['units'])
    findings = [
        reading('unfunded_firm','未覆盖保供',firm-contracted,'MWh',0,'high'),
        reading('optional_nomination','可中断已确认',max(0,record['units']-contracted),'MWh',14,'high'),
        reading('cold_degree','峰段暖度需求',max(0,19-ambient)*4,'度时',97,'high'),
        reading('storage_coverage','储热对缺口比',reserve/max(1.,heat),'比值',.37,'low')]
    work=record['units']
    outcome='已安排购热 MWh'
    exposure=max(0,firm-contracted)
    return {'checks':findings,'work':round(work,3),'work_label':outcome,'exposure':round(exposure,3),'status':'可核算'}


def tally(rows: list[dict]) -> dict:
    by_region = defaultdict(lambda: {'measured':0,'missing':0,'work':0.,'exposure':0.,'outside':0})
    for row in rows:
        area = by_region[row['region']]
        note = row['business_evidence']
        if note['work'] is None:
            area['missing'] += 1
        else:
            area['measured'] += 1
            area['work'] += note['work']
            area['exposure'] += note['exposure']
            area['outside'] += sum(check['exceeded'] for check in note['checks'])
    aggregates = {'work':0.,'exposure':0.,'source_missing':0,'outside_count':0}
    for area in by_region.values():
        aggregates['work'] += area['work']
        aggregates['exposure'] += area['exposure']
        aggregates['source_missing'] += area['missing']
        aggregates['outside_count'] += area['outside']
    aggregates['work'] = round(aggregates['work'],3)
    aggregates['exposure'] = round(aggregates['exposure'],3)
    return {**aggregates,'exposure_unit':EXPOSURE_UNIT,'regions':dict(sorted(by_region.items()))}
