"""Rafa Assistente — servidor web de teste (FastAPI).
Reaproveita src/retriever.py e src/assistente.py. Logs em app/data/conversas.jsonl.
Env: ANTHROPIC_API_KEY, ACCESS_CODE (código que as professoras digitam), ADMIN_CODE (painel de logs), MAX_MSGS_DIA (padrão 40)."""
import os, sys, json, time, uuid, re, collections, datetime as dt, hmac, hashlib, base64, urllib.request, threading, contextvars
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); os.chdir(HERE); os.makedirs('data',exist_ok=True)
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from pydantic import BaseModel
from assistente import Assistente, ABERTURA, SUPORTE, SYSTEM, montar_mensagem, mensagem_trilha
from trilhas import Trilhas, Fluxo, OUTRA
from indexar import norm

ACCESS=os.environ.get('ACCESS_CODE','bailarina')
ADMIN=os.environ.get('ADMIN_CODE','rafa-admin')
MAXD=int(os.environ.get('MAX_MSGS_DIA','40'))
LOG='data/conversas.jsonl'
# --- Teste gratuito por WhatsApp (só Brasil): 1 entrada por número, sessão de TESTE_HORAS, TESTE_MSGS mensagens ---
TRIAL_H=int(os.environ.get('TESTE_HORAS','24')); MAXT=int(os.environ.get('TESTE_MSGS','15')); TETO=int(os.environ.get('TESTE_TETO_DIA','30'))
SB_URL=os.environ.get('SUPABASE_URL','').rstrip('/'); SB_KEY=os.environ.get('SUPABASE_KEY','')
SECRET=(os.environ.get('TRIAL_SECRET') or (ADMIN+'|'+ACCESS)).encode()
LEADS='data/testes.jsonl'
USAGE_T=collections.defaultdict(int)   # telefone -> msgs no teste
IPS=collections.defaultdict(list)      # ip -> timestamps (freio simples)
app=FastAPI(title='Rafa Assistente')
A=Assistente()
HIST=collections.defaultdict(list)   # session -> [{"role","content"}] (sem trechos)
USAGE=collections.defaultdict(int)   # (session, dia) -> msgs
# --- Registro de uso da IA (tokens) por tipo: 'teste' ou 'assinante'. Vai para o Supabase; falha em silêncio, nunca derruba a resposta. ---
TIPO=contextvars.ContextVar('tipo',default='assinante')
TEL=contextvars.ContextVar('tel',default=None)
def _enviar_uso(tipo,modelo,tin,tout,tel=None):
    try:
        if not (SB_URL and SB_KEY): return
        req=urllib.request.Request(SB_URL+'/rest/v1/rpc/log_uso',data=json.dumps({'p_tipo':tipo,'p_modelo':modelo,'p_in':tin,'p_out':tout,'p_tel':tel}).encode(),
            headers={'apikey':SB_KEY,'Authorization':'Bearer '+SB_KEY,'Content-Type':'application/json'})
        urllib.request.urlopen(req,timeout=10).read()
    except Exception: pass
def _envolver(msgs):
    orig=msgs.create
    def f(*a,**k):
        r=orig(*a,**k)
        try:
            u=r.usage; threading.Thread(target=_enviar_uso,args=(TIPO.get(),str(k.get('model','')),int(u.input_tokens or 0)+int(getattr(u,'cache_creation_input_tokens',0) or 0)+int(getattr(u,'cache_read_input_tokens',0) or 0),int(u.output_tokens or 0),TEL.get()),daemon=True).start()
        except Exception: pass
        return r
    msgs.create=f
try:
    _envolver(A.c.messages)
    _rc=getattr(A.r,'client',None)
    if _rc is not None and _rc is not A.c: _envolver(_rc.messages)
except Exception: pass
FL=Fluxo(Trilhas(A.r.chunks))         # aula completa a partir das trilhas
SEEN=collections.defaultdict(set)    # session -> (doc,section) já entregues no assunto atual
LASTQ={}                             # session -> consulta do assunto atual (para 'outra opção')

class Entrada(BaseModel):
    code: str
class Teste(BaseModel):
    nome: str; whatsapp: str; canal: str|None=None; aceite: bool=False
class Msg(BaseModel):
    session: str; code: str; message: str; nome: str|None=None
    bot_anterior: str|None=None; perguntas: list[str]|None=None   # contexto vindo da página (sobrevive a reinício do servidor)
class Fb(BaseModel):
    session: str; code: str; turn: str; vote: int; comment: str|None=None

def _assina(payload):
    return hmac.new(SECRET,payload.encode(),hashlib.sha256).hexdigest()[:32]
def emitir_token(tel):
    exp=int(time.time())+TRIAL_H*3600
    p=base64.urlsafe_b64encode(f'{tel}|{exp}'.encode()).decode().rstrip('=')
    return f'T.{p}.{_assina(p)}'
def ler_token(code):
    """-> telefone se o token de teste é válido e não expirou; None caso contrário"""
    try:
        _,p,sig=code.strip().split('.')
        if not hmac.compare_digest(sig,_assina(p)): return None
        tel,exp=base64.urlsafe_b64decode(p+'='*(-len(p)%4)).decode().split('|')
        return tel if time.time()<int(exp) else None
    except Exception: return None
def acesso(code):
    """'assinante' | ('teste',tel) | None"""
    c=(code or '').strip()
    if c==ACCESS.strip(): return 'assinante'
    if c.startswith('T.'):
        t=ler_token(c)
        if t: return ('teste',t)
    return None
def tel_br(x):
    d=re.sub(r'\D','',x or '')
    if d.startswith('00'): d=d[2:]
    if d.startswith('55') and len(d)==13: d=d[2:]
    if len(d)!=11 or d[0]=='0' or d[1]=='0' or d[2]!='9': return None   # celular brasileiro: DDD + 9 + 8 dígitos
    return '55'+d
CANAIS={'instagram','site','exassinantes','assinantes','teste-claude'}
def _canal(x):
    """Canal do link (?c=): minúsculas, sem pontuação; só aceita a lista fixa, o resto vira 'outro' (vazio = 'site')."""
    c=re.sub(r'[^a-z0-9_-]','',(x or '').lower())[:30]
    if not c: return 'site'
    return c if c in CANAIS else 'outro'
def reivindicar(tel,nome,canal):
    """Registra o número. Devolve 'ok' | 'ja_usado' | 'teto'. Supabase se configurado; senão arquivo local (apagado a cada deploy)."""
    if SB_URL and SB_KEY:
        req=urllib.request.Request(SB_URL+'/rest/v1/rpc/claim_trial',data=json.dumps({'p_tel':tel,'p_nome':nome,'p_canal':canal or '','p_teto':TETO}).encode(),
            headers={'apikey':SB_KEY,'Authorization':'Bearer '+SB_KEY,'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=10) as r: return json.loads(r.read().decode())
    hoje=dt.date.today().isoformat(); regs=[]
    if os.path.exists(LEADS): regs=[json.loads(l) for l in open(LEADS) if l.strip()]
    if any(r['tel']==tel for r in regs): return 'ja_usado'
    if sum(1 for r in regs if r['ts'][:10]==hoje)>=TETO: return 'teto'
    with open(LEADS,'a') as f: f.write(json.dumps({'tel':tel,'nome':nome,'canal':canal or '','ts':dt.datetime.utcnow().isoformat(timespec='seconds')},ensure_ascii=False)+'\n')
    return 'ok'

def log(rec):
    rec['ts']=dt.datetime.utcnow().isoformat(timespec='seconds')
    with open(LOG,'a') as f: f.write(json.dumps(rec,ensure_ascii=False)+'\n')

@app.get('/', response_class=HTMLResponse)
def index(): return FileResponse('index.html')

@app.get('/logo.png')
def logo(): return FileResponse('logo.png')

@app.head('/')
def head_ok(): return JSONResponse({'ok':True})

@app.get('/api/abertura')
def abertura(): return {'texto':ABERTURA}

@app.post('/api/entrar')
def entrar(e:Entrada):
    # confere o código ANTES de abrir o chat (comparação exata: maiúscula conta)
    if not acesso(e.code): raise HTTPException(401,'código inválido')
    return {'ok':True}

@app.post('/api/teste')
def teste(t:Teste,request:Request):
    ip=(request.headers.get('x-forwarded-for') or request.client.host or '?').split(',')[0].strip(); agora=time.time()
    IPS[ip]=[x for x in IPS[ip] if agora-x<3600]
    if len(IPS[ip])>=6: raise HTTPException(429,'Muitas tentativas. Tente de novo mais tarde.')
    IPS[ip].append(agora)
    nome=t.nome.strip()
    if not t.aceite: raise HTTPException(400,'Para entrar, marque que aceita receber contato do Você Bailarina.')
    if not (2<=len(nome)<=60): raise HTTPException(400,'Digite seu nome.')
    tel=tel_br(t.whatsapp)
    if not tel: raise HTTPException(400,'Por enquanto o teste é só para números do Brasil. Digite o DDD e o número, por exemplo (11) 91234-5678.')
    try: r=reivindicar(tel,nome,_canal(t.canal))
    except Exception as e:
        log({'erro_teste':str(e)}); raise HTTPException(503,'Não consegui registrar seu teste agora. Tente de novo em um minuto.')
    if r=='ja_usado': raise HTTPException(409,'Esse WhatsApp já usou o teste gratuito. Para continuar, conheça a assinatura: vocebailarina.com/assinatura')
    if r=='teto': raise HTTPException(429,'Os testes de hoje acabaram. Volte amanhã ou conheça a assinatura: vocebailarina.com/assinatura')
    log({'teste_entrada':True,'nome':nome,'tel_final':tel[-4:],'canal':t.canal or ''})
    return {'token':emitir_token(tel),'horas':TRIAL_H}

@app.post('/api/chat')
def chat(m:Msg):
    ac=acesso(m.code)
    if not ac: raise HTTPException(401,'código inválido')
    q=m.message.strip()
    if not q or len(q)>1500: raise HTTPException(400,'mensagem vazia ou longa demais')
    day=dt.date.today().isoformat(); k=(m.session,day)
    TIPO.set('teste' if isinstance(ac,tuple) else 'assinante'); TEL.set(ac[1] if isinstance(ac,tuple) else None)
    if isinstance(ac,tuple):
        if USAGE_T[ac[1]]>=MAXT: return {'turn':None,'resposta':f'Chegamos ao fim das {MAXT} perguntas do seu teste gratuito. Para continuar com a Rafa Assistente, conheça a assinatura do Você Bailarina: vocebailarina.com/assinatura. Qualquer dúvida, fale com a Thay no {SUPORTE}.','fontes':[]}
        USAGE_T[ac[1]]+=1
    elif USAGE[k]>=MAXD: return {'turn':None,'resposta':f'Por hoje chegamos ao limite de perguntas deste teste. Amanhã eu volto! Se for urgente, fale com a Thay no {SUPORTE}.','fontes':[]}
    USAGE[k]+=1
    hist=HIST[m.session][-6:]
    t0=time.time(); modo='normal'
    ant=next((h['content'] for h in reversed(hist) if h['role']=='user'),'')
    bot_ant=next((h['content'] for h in reversed(hist) if h['role']=='assistant'),'') or (m.bot_anterior or '')[:2000]
    usuarias=[h['content'] for h in hist if h['role']=='user'] or [x[:500] for x in (m.perguntas or [])[-4:]]
    if not ant and usuarias: ant=usuarias[-1]
    res=FL.tratar(m.session,q,anterior=ant,bot_anterior=bot_ant,usuarias=usuarias)
    if res and res[0]=='perguntar':      # pergunta fixa (idade / está ensaiando?), sem chamar a IA
        txt=res[1]; HIST[m.session]+=[{"role":"user","content":q},{"role":"assistant","content":txt}]
        log({'session':m.session,'nome':m.nome,'q':q,'a':txt,'modo':'trilha-pergunta','seg':0})
        return {'turn':None,'resposta':txt,'fontes':[]}
    if res and res[0]=='aula':          # aula completa montada direto da trilha + apostilas (texto exato, sem IA)
        _,txt,w,fontes,est=res; LASTQ.pop(m.session,None); turn=uuid.uuid4().hex[:10]
        HIST[m.session]+=[{"role":"user","content":q},{"role":"assistant","content":txt[:1500]}]
        log({'session':m.session,'nome':m.nome,'turn':turn,'q':q,'a':txt,'fontes':fontes,'modo':'trilha','semana':w['n'],'seg':round(time.time()-t0,1)})
        return {'turn':turn,'resposta':txt,'fontes':fontes,'aula':est}
    else:
        FL.ult.pop(m.session,None)
        outra=bool(OUTRA.search(norm(q))) and m.session in LASTQ
        if outra:
            qbusca=LASTQ[m.session]; modo='outra-opcao'
        else:
            # contexto para a busca: pergunta atual + última pergunta (perguntas curtas de acompanhamento)
            qbusca=q if len(q.split())>5 or not hist else hist[-2]['content'][:300]+' '+q
            SEEN[m.session]=set(); LASTQ[m.session]=qbusca
        content,ctx,exs=montar_mensagem(A.r,q,qbusca,SEEN[m.session],outra)
        SEEN[m.session]|={(c['doc'],c['section']) for c in ctx}|{(e['doc'],e['section']) for _,e,_ in exs}
        fontes=sorted(set(c['title'] for c in ctx))
    msgs=hist+[{"role":"user","content":content}]
    try:
        r=A.c.messages.create(model="claude-sonnet-5-5",max_tokens=1600,thinking={"type":"between_tools"},system=[{"type":"text","text":SYSTEM,"cache_control":{"type":"ephemeral"}}],messages=msgs)
        txt="".join(b.text for b in r.content if b.type=="text")
    except Exception as e:
        log({'session':m.session,'nome':m.nome,'q':q,'erro':str(e),'modo':modo})
        return {'turn':None,'resposta':f'Tive um problema técnico agora. Tente de novo em um minuto ou fale com a Thay no {SUPORTE}.','fontes':[]}
    HIST[m.session]+= [{"role":"user","content":q},{"role":"assistant","content":txt}]
    turn=uuid.uuid4().hex[:10]
    log({'session':m.session,'nome':m.nome,'turn':turn,'q':q,'a':txt,'fontes':fontes,'modo':modo,'seg':round(time.time()-t0,1)})
    return {'turn':turn,'resposta':txt,'fontes':fontes}

@app.post('/api/feedback')
def feedback(f:Fb):
    if not acesso(f.code): raise HTTPException(401)
    log({'session':f.session,'feedback':f.turn,'vote':f.vote,'comment':f.comment}); return {'ok':True}

def _admin_ok(code): return code.strip()==ADMIN.strip()

FORM='<meta charset=utf-8><style>body{font-family:system-ui;max-width:400px;margin:4rem auto;padding:0 1rem}input,button{font-size:1rem;padding:.6rem;width:100%;box-sizing:border-box;margin-top:.5rem}button{background:#cd7990;color:#fff;border:0;border-radius:8px}</style><h2>Painel — Rafa Assistente</h2><form method=post action=/admin><input type=password name=code placeholder="Código de administração" autofocus><button>Entrar</button></form>{err}'

@app.get('/admin', response_class=HTMLResponse)
def admin_get(code:str=''):
    if not code: return FORM.replace('{err}','')
    if not _admin_ok(code): return FORM.replace('{err}','<p style="color:#b00">Código incorreto.</p>')
    return _panel(code)

@app.post('/admin', response_class=HTMLResponse)
async def admin_post(request:Request):
    form=await request.form(); code=str(form.get('code',''))
    if not _admin_ok(code): return FORM.replace('{err}','<p style="color:#b00">Código incorreto.</p>')
    return _panel(code)

@app.get('/admin/download')
def admin_download(code:str=''):
    if not _admin_ok(code): raise HTTPException(401)
    if not os.path.exists(LOG): raise HTTPException(404,'sem registros ainda')
    return FileResponse(LOG, filename=f'conversas-{dt.date.today().isoformat()}.jsonl', media_type='application/json')

def _panel(code):
    rows=[json.loads(l) for l in open(LOG)] if os.path.exists(LOG) else []
    fb={r['feedback']:r for r in rows if 'feedback' in r}
    convs=[r for r in rows if 'q' in r]
    h=['<meta charset=utf-8><style>body{font-family:system-ui;max-width:900px;margin:2rem auto;padding:0 1rem;color:#222}.q{background:#fdf2f6;padding:.6rem .8rem;border-radius:8px;margin-top:1.4rem}.a{white-space:pre-wrap;padding:.6rem .8rem}.m{color:#888;font-size:.8rem}.bad{color:#b00}</style>',
       f'<h1>Rafa Assistente — {len(convs)} respostas, {len(set(r["session"] for r in convs))} sessões, {sum(1 for r in fb.values() if r["vote"]>0)} 👍 / {sum(1 for r in fb.values() if r["vote"]<0)} 👎</h1><p class=m><a href="/admin/download?code={code}">⬇️ Baixar todos os registros (.jsonl)</a> — baixe antes de cada atualização do site; o arquivo é apagado a cada novo deploy.</p>']
    for r in reversed(convs):
        v=fb.get(r.get('turn'))
        tag=('<b class=bad>👎 '+(v.get('comment') or '')+'</b>' if v and v['vote']<0 else '👍' if v else '')
        h.append(f"<div class=q><span class=m>{r['ts']} · {r.get('nome') or r['session'][:6]} · {r.get('seg','')}s {tag}</span><br><b>{r['q']}</b></div><div class=a>{r.get('a') or ('ERRO: '+r.get('erro',''))}</div><div class=m>{', '.join(r.get('fontes',[]))}</div>")
    return ''.join(h)

