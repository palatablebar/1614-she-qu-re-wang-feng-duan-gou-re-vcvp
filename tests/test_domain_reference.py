from dataclasses import replace
from math import isclose, isfinite
from csv import DictReader
from io import StringIO

import numpy as np
import pytest
from fastapi.testclient import TestClient

from heatnom.intertie_demand.contracts import Probe
from heatnom.degree_features.indicators import derive
from heatnom.heat_contracts.contracts import Scenario
from heatnom.heat_contracts.calendar import WindowBook
from heatnom.grid_settlement.service import manifest
from heatnom.api import application
from heatnom.process import preview
from heatnom.settings import DEFAULT_BUDGET, FIELDS, SAMPLE_NAME

COUNTER = (-7.0, 33.0, 44.0, 15.0, 10.0, 79.0)
VARY_AXIS = 3
VARY_FACTOR = 1.4


def test_native_domain_estimator_against_reference(prepared):
    model = prepared.fitted.estimator
    basis = model.describe()
    assert basis['parameters']['reserve']<=0
    assert basis['regularization']>0
    mild = Probe((0.,0.,0.,0.,0.),COUNTER,'外部测试区','储热仓',125,'counter')
    colder = replace(mild,standard=(1.2,0.,0.,0.,0.))
    buffered = replace(colder,standard=(1.2,0.,0.,1.7,0.))
    assert model.predict(buffered) <= model.predict(colder)
    assert model.predict(mild) == pytest.approx(max(0,basis['parameters']['intercept']))


def test_raw_observation_moves_domain_signals():
    before = derive(COUNTER)
    setback = list(COUNTER)
    setback[VARY_AXIS] *= VARY_FACTOR
    after = derive(tuple(setback))
    assert len(before)==len(after)==5
    assert before!=after
    assert all(map(isfinite,(*before,*after)))


def test_case_brief_uses_measurement_and_native_units(source_bytes):
    approved = preview(source_bytes,Scenario(DEFAULT_BUDGET)).payload
    complete = [row for row in approved['decisions'] if not row['missing']]
    assert complete and all(len(row['business_evidence']['checks'])==4 for row in complete)
    for row in complete:
        evidence = row['business_evidence']
        values = evidence['checks']
        assert len({point['field'] for point in values})==4
        assert all(point['unit'] and point['label'] and isfinite(point['value']) for point in values)
        if row['status']=='booked':
            assert evidence['work']>0
    assert any(point['exceeded'] for row in complete for point in row['business_evidence']['checks'])


def test_case_brief_export_round_trip(source_bytes):
    approved = preview(source_bytes,Scenario(DEFAULT_BUDGET))
    lookup = {row['key']:row for row in approved.payload['decisions']}
    reader = DictReader(StringIO(manifest(approved.payload)))
    exported = list(reader)
    assert {row['key'] for row in exported} == lookup.keys()
    for row in exported:
        assert row['source_sha256']==approved.source
        business = lookup[row['key']]['business_evidence']
        if business['exposure'] is None:
            assert row['exposure_quantity']==''
        else:
            assert isclose(float(row['exposure_quantity']),business['exposure'])


def test_limited_service_can_still_use_mature_replays(source_bytes):
    earliest=preview(source_bytes,Scenario(DEFAULT_BUDGET,start=440,stop=470))
    control=preview(source_bytes,Scenario(DEFAULT_BUDGET))
    assert earliest.identifier!=control.identifier
    assert earliest.model==control.model
    assert earliest.payload['replay']==control.payload['replay']
    assert earliest.payload['ledger']['booked_units']<=control.payload['ledger']['booked_units']
    assert all(440<=item['start']<item['end']<=470 for item in earliest.payload['decisions'] if item['start'] is not None)


def test_compare_http_returns_business_impact(tmp_path):
    from pathlib import Path
    source = Path(__file__).resolve().parent.parent/'sample_data'/SAMPLE_NAME
    with TestClient(application(source,tmp_path)) as client:
        base = client.get('/api/briefing').json()
        assert base['work']['exposure_unit']
        assert len(base['coverage']['regional_coverage'])>=4
        conditions = {'baseline':{'budget':DEFAULT_BUDGET},'proposal':{'budget':0}}
        reduced = client.post('/api/compare',json=conditions)
        assert reduced.status_code==200
        result = reduced.json()
        assert result['booked_delta']<0
        assert result['metric_unit']==base['work']['exposure_unit']
        assert all(item['region'] and item['key'] for item in result['changes'])


def test_feed_uses_domain_fields_and_iso_interpretation(source,prepared):
    known = prepared.vintage.live[0]
    assert len(known.raw)==len(FIELDS)
    assert len({field.key for field in FIELDS}) == len(FIELDS)
    assert all(field.allowed(value) for field,value in zip(FIELDS,known.raw,strict=True) if value is not None)
    assert {row.code for row in source.rejected} >= {'nonfinite_reading','live_outcome'}


def test_live_decisions_have_one_reflectable_reason(source_bytes):
    result=preview(source_bytes,Scenario(DEFAULT_BUDGET)).payload
    from collections import Counter
    counts=Counter(row['status'] for row in result['decisions'])
    assert len(counts)>=4
    for case in result['decisions']:
        assert len(case['reason'])>=5
        if case['units']:
            assert case['status']=='booked' and case['resource'] and case['end']>case['start']
        if case['status']=='locked':
            assert case['units']==0 and case['start'] is None


def test_cli_compare_returns_same_business_transition_as_web(prepared,capfd,tmp_path):
    from pathlib import Path
    from json import loads
    from heatnom.cli import run
    source = Path(__file__).resolve().parent.parent/'sample_data'/SAMPLE_NAME
    assert run(['--source',str(source),'compare','--to-budget','0'])==0
    result = loads(capfd.readouterr().out)
    assert result['model']==prepared.fitted.signature
    with TestClient(application(source,tmp_path)) as client:
        condition = {'baseline':{},'proposal':{'budget':0}}
        assert result==client.post('/api/compare',json=condition).json()


def test_archive_mutation_cannot_start_a_new_history(tmp_path):
    from heatnom.grid_settlement.service import freeze, publish, latest
    entry = freeze('weak-identifier','reference-model','ready',{'planned':7})
    entry.payload['planned']=14
    with pytest.raises(RuntimeError,match='不同内容'):
        publish(tmp_path,entry,0)
    assert latest(tmp_path) is None


def test_canonical_digest_is_order_invariant_for_receipt():
    from heatnom.grid_settlement.service import canonical
    key = {'model':'特征版','window':[87,98],'footprint':'单据源'}
    fixed = canonical(key)
    assert '单据源' in fixed and fixed == canonical(dict(reversed(list(key.items()))))
