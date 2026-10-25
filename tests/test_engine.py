import json
import re
import sqlite3
import hashlib
from pathlib import Path
import pytest
from queryforge.demo import make_demo_db
from queryforge.engine import QueryEngine, QueryError
from queryforge.benchmark import run_benchmark

@pytest.fixture
def database(tmp_path):
    return make_demo_db(tmp_path/'demo.sqlite')

@pytest.fixture
def engine(database):
    return QueryEngine(database)

@pytest.mark.parametrize('question,expect',[
    ('how many companies are in UK',4),
    ('how many companies in technology',4),
    ('how many companies in healthcare',3),
    ('total profit in 2024',396200000),
])
def test_scalar_questions(engine,question,expect):
    assert engine.ask(question).rows[0]['value']==expect


def test_schema_joins_and_year(engine):
    result=engine.ask('top 5 companies by revenue in 2024')
    assert ' JOIN ' in result.sql
    assert result.parameters==[2024]
    assert len(result.rows)==5
    assert result.rows[0]['entity']=='Orbit Markets'
    assert result.rows[0]['value']>result.rows[-1]['value']


def test_grouped_aggregations(engine):
    result=engine.ask('average revenue by sector in 2024')
    assert 'GROUP BY' in result.sql
    assert len(result.rows)==5
    assert all(isinstance(x['value'],float) for x in result.rows)


def test_implicit_sector_linking(engine):
    assert set(x['entity'] for x in engine.ask('list technology companies').rows)=={'Aster Labs','Cobalt Systems','Fjord Analytics','Lumen Cloud'}


def test_inequality_and_units(engine):
    result=engine.ask('companies with revenue above 100 million in 2024')
    assert result.parameters==[100000000,2024]
    assert result.rows and all('entity' in item for item in result.rows)


def test_injection_is_data_not_sql(engine,database):
    before=hashlib.sha256(database.read_bytes()).hexdigest()
    for question in ["show companies; DROP TABLE companies", "companies with revenue above 100 million; DELETE FROM companies", "", "x"*501]:
        try:
            result=engine.ask(question)
            assert result.sql.startswith('SELECT ')
            assert ';' not in result.sql
        except QueryError:
            pass
    after=hashlib.sha256(database.read_bytes()).hexdigest()
    assert before==after
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT COUNT(*) FROM companies').fetchone()[0]==15


def test_reject_unsupported_question(engine):
    with pytest.raises(QueryError):
        engine.ask('Why is the sky blue?')


def test_file_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        QueryEngine(tmp_path/'missing.db')


def test_benchmark_regression(database):
    root=Path(__file__).resolve().parents[1]
    result=run_benchmark(database,root/'data'/'benchmark.json')
    assert result['sample_count']>=60
    assert result['engine_accuracy']>=.95
    assert result['engine_accuracy']>result['baseline_accuracy']


def test_fastapi_http(tmp_path,monkeypatch):
    try:
        from fastapi.testclient import TestClient
    except ImportError:
        pytest.skip('Install queryforge[web] to test API')
    db=make_demo_db(tmp_path/'http.sqlite')
    from queryforge import app as service
    monkeypatch.setattr(service,'DB',db)
    client=TestClient(service.app)
    assert 'QueryForge' in client.get('/').text
    assert 'companies' in client.get('/schema').json()
    response=client.post('/ask',json={'question':'how many companies are in UK'})
    assert response.status_code==200
    assert response.json()['rows'][0]['value']==4
    assert client.post('/ask',json={'question':'banana spaceship'}).status_code==422


def test_content_grounded_typo_repair(engine):
    result=engine.ask('list companies with sector technlogy')
    assert len(result.rows)==4
    assert result.parameters==['Technology']
    assert any('Resolved value' in note for note in result.reasoning)


def test_paraphrase_challenge(database):
    root=Path(__file__).resolve().parents[1]
    result=run_benchmark(database,root/'data'/'paraphrase_challenge.json')
    assert result['sample_count']==20
    assert result['engine_accuracy']>=.9
