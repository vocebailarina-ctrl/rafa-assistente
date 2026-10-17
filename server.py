"""Rafa Assistente — servidor web de teste (FastAPI).
Reaproveita src/retriever.py e src/assistente.py. Logs em app/data/conversas.jsonl.
Env: ANTHROPIC_API_KEY, ACCESS_CODE (código que as professoras digitam), ADMIN_CODE (painel de logs), MAX_MSGS_DIA (padrão 40)."""
import os, sys, json, time, uuid, re, collections, datetime as dt
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); os.chdir(HERE); os.makedirs('data',exist_ok=True)
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from pydantic import BaseModel
from assistente import Assistente, ABERTURA, SUPORTE, SYSTEM

ACCESS=os.environ.get('ACCESS_CODE','bailarina')
ADMIN=os.environ.get('ADMIN_CODE','rafa-admin')
MAXD=int(os.environ.get('MAX_MSGS_DIA','40'))
LOG='data/conversas.jsonl'
app=FastAPI(title='Rafa Assistente')
A=Assistente()
HIST=collections.defaultdict(list)   # session -> [{"role","content"}] (sem trechos)
USAGE=collections.defaultdict(int)   # (session, dia) -> msgs

class Msg(BaseModel):
    session: str; code: str; message: str; nome: str|None=None
class Fb(BaseModel):
    session: str; code: str; turn: str; vote: int; comment: str|None=None

def log(rec):
    rec['ts']=dt.datetime.utcnow().isoformat(timespec='seconds')
    with open(LOG,'a') as f: f.write(json.dumps(rec,ensure_ascii=False)+'\n')

@app.get('/', response_class=HTMLResponse)
def index(): return FileResponse('index.html')

@app.head('/')
def head_ok(): return JSONResponse({'ok':True})

@app.get('/api/abertura')
def abertura(): return {'texto':ABERTURA}

@app.post('/api/chat')
def chat(m:Msg):
    if m.code!=ACCESS: raise HTTPException(401,'código inválido')
    q=m.message.strip()
    if not q or len(q)>1500: raise HTTPException(400,'mensagem vazia ou longa demais')
    day=dt.date.today().isoformat(); k=(m.session,day)
    if USAGE[k]>=MAXD: return {'turn':None,'resposta':f'Por hoje chegamos ao limite de perguntas deste teste. Amanhã eu volto! Se for urgente, fale com a Thay no {SUPORTE}.','fontes':[]}
    USAGE[k]+=1
    hist=HIST[m.session][-6:]
    # contexto para a busca: pergunta atual + última pergunta (perguntas curtas de acompanhamento)
    qbusca=q if len(q.split())>5 or not hist else hist[-2]['content'][:300]+' '+q
    t0=time.time()
    ctx=A.r.retrieve(qbusca,top=6)
    blocks="\n\n".join(f"<trecho fonte=\"{c['title']}\" secao=\"{c['section']}\" faixa=\"{c['faixa']}\">\n{c['text']}\n</trecho>" for c in ctx)
    msgs=hist+[{"role":"user","content":f"<trechos>\n{blocks}\n</trechos>\n\nPergunta da professora: {q}"}]
    try:
        r=A.c.messages.create(model="claude-sonnet-5-5",max_tokens=1200,thinking={"type":"between_tools"},system=SYSTEM,messages=msgs)
        txt="".join(b.text for b in r.content if b.type=="text")
    except Exception as e:
        log({'session':m.session,'nome':m.nome,'q':q,'erro':str(e)})
        return {'turn':None,'resposta':f'Tive um problema técnico agora. Tente de novo em um minuto ou fale com a Thay no {SUPORTE}.','fontes':[]}
    HIST[m.session]+= [{"role":"user","content":q},{"role":"assistant","content":txt}]
    turn=uuid.uuid4().hex[:10]
    fontes=sorted(set(c['title'] for c in ctx))
    log({'session':m.session,'nome':m.nome,'turn':turn,'q':q,'a':txt,'fontes':fontes,'seg':round(time.time()-t0,1)})
    return {'turn':turn,'resposta':txt,'fontes':fontes}

@app.post('/api/feedback')
def feedback(f:Fb):
    if f.code!=ACCESS: raise HTTPException(401)
    log({'session':f.session,'feedback':f.turn,'vote':f.vote,'comment':f.comment}); return {'ok':True}

@app.get('/admin', response_class=HTMLResponse)
def admin(code:str=''):
    if code!=ADMIN: raise HTTPException(401)
    rows=[json.loads(l) for l in open(LOG)] if os.path.exists(LOG) else []
    fb={r['feedback']:r for r in rows if 'feedback' in r}
    convs=[r for r in rows if 'q' in r]
    h=['<meta charset=utf-8><style>body{font-family:system-ui;max-width:900px;margin:2rem auto;padding:0 1rem;color:#222}.q{background:#fdf2f6;padding:.6rem .8rem;border-radius:8px;margin-top:1.4rem}.a{white-space:pre-wrap;padding:.6rem .8rem}.m{color:#888;font-size:.8rem}.bad{color:#b00}</style>',
       f'<h1>Rafa Assistente — {len(convs)} respostas, {len(set(r["session"] for r in convs))} sessões, {sum(1 for r in fb.values() if r["vote"]>0)} 👍 / {sum(1 for r in fb.values() if r["vote"]<0)} 👎</h1>']
    for r in reversed(convs):
        v=fb.get(r.get('turn'))
        tag=('<b class=bad>👎 '+(v.get('comment') or '')+'</b>' if v and v['vote']<0 else '👍' if v else '')
        h.append(f"<div class=q><span class=m>{r['ts']} · {r.get('nome') or r['session'][:6]} · {r.get('seg','')}s {tag}</span><br><b>{r['q']}</b></div><div class=a>{r.get('a') or ('ERRO: '+r.get('erro',''))}</div><div class=m>{', '.join(r.get('fontes',[]))}</div>")
    return ''.join(h)

