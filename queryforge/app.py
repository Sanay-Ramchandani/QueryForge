"""HTTP API and minimal interactive UI. Run: uvicorn queryforge.app:app --reload"""
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from .engine import QueryEngine, QueryError
from .demo import make_demo_db

DB = Path(os.environ.get('QUERYFORGE_DB', str(Path(__file__).resolve().parents[1] / 'data' / 'finance.sqlite')))
if not DB.exists():
    make_demo_db(DB)
app = FastAPI(title='QueryForge', description='Explainable offline text-to-SQL, with parameterized queries')

class Question(BaseModel):
    question: str = Field(min_length=1, max_length=500)

@app.post('/ask')
def ask(item: Question):
    try:
        return QueryEngine(DB).ask(item.question).as_dict()
    except QueryError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

@app.get('/schema')
def schema():
    from .schema import Schema
    engine = QueryEngine(DB)
    with engine._connection() as conn:
        s = Schema(conn)
        return {t: [{'name': c.name, 'type': c.type} for c in cols] for t, cols in s.columns.items()}

@app.get('/', response_class=HTMLResponse)
def home():
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>QueryForge</title>
<style>*{box-sizing:border-box}body{background:#101521;color:#f0f3fa;font:16px system-ui;margin:0}main{max-width:880px;margin:9vh auto;padding:0 20px}h1{font-size:48px;margin:0}p{color:#aab4c8}form{display:flex;gap:10px;margin:35px 0}input{flex:1;padding:16px;font-size:16px;border:1px solid #37445f;border-radius:10px;background:#1c2534;color:white}button{padding:0 25px;background:#78b7fc;color:#061526;border:0;border-radius:10px;font-weight:700;cursor:pointer}pre{white-space:pre-wrap;overflow:auto;background:#1b2535;padding:18px;border-radius:10px}.pane{background:#182131;padding:20px;border-radius:12px;margin-bottom:15px;overflow:auto}table{border-collapse:collapse;width:100%}td,th{text-align:left;border-bottom:1px solid #37445f;padding:10px}small{color:#9cbbd8}</style></head>
<body><main><small>RESEARCH ENGINEERING PROJECT</small><h1>QueryForge</h1><p>Ask questions about a fictional company database. Inspect parameterized SQL and the reasoning trace. Offline, deterministic, and read-only.</p>
<form id="form"><input id="question" value="top 5 companies by revenue in 2024" aria-label="Question" /><button>Run query</button></form>
<div id="out"></div></main><script>const form=document.querySelector('#form'),out=document.querySelector('#out');form.onsubmit=async e=>{e.preventDefault();out.textContent='Running...';try{const r=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:document.querySelector('#question').value})});const d=await r.json();if(!r.ok)throw Error(d.detail);out.innerHTML='';const box=(title,text)=>{const p=document.createElement('div');p.className='pane';const h=document.createElement('h3');h.textContent=title;p.append(h);const pre=document.createElement('pre');pre.textContent=text;p.append(pre);out.append(p)};box('SQL',d.sql+'\nParameters: '+JSON.stringify(d.parameters));const p=document.createElement('div');p.className='pane';const h=document.createElement('h3');h.textContent='Results';p.append(h);const table=document.createElement('table');let tr=document.createElement('tr');d.columns.forEach(c=>{const th=document.createElement('th');th.textContent=c;tr.append(th)});table.append(tr);d.rows.forEach(row=>{let tr=document.createElement('tr');d.columns.forEach(c=>{const td=document.createElement('td');td.textContent=row[c];tr.append(td)});table.append(tr)});p.append(table);out.append(p);box('Reasoning trace',d.reasoning.join('\n'))}catch(err){out.textContent=err.message}};</script></body></html>'''
