"""Busca de exercícios nas apostilas (Kids 1, Kids 2, Passo 1) por título E corpo.
Regras: nunca devolve Entrada/Révérence/Marcha salvo pedido explícito; conceito só conta se aparece de fato
no título ou no corpo (ex.: 'Trabalho de pés' sem a palavra tendu no corpo NÃO é tendu)."""
import re, json, random
from indexar import norm

# conceito -> (regex na pergunta, regex no texto do exercício [norm])
CONCEITOS = {
 'tendu':      (r'tendu|tandi|tendi',            r'\btendus?\b'),
 'plie':       (r'\bplies?\b|plie',               r'\bplies?\b'),
 'salto':      (r'salt|sautes?|skip|echappe|assemble|spring',  r'\bsautes?\b|\bsaltos?\b|\bskips?\b|echappe|assemble|spring pointe'),
 'alongamento':(r'along|flexibilidade|espacate|borboleta',     r'along|flexibilidade|espacate|borboleta|posteriores'),
 'releve':     (r'releve|ponta|meia ponta',       r'\breleve\b|\beleve\b|meia ponta'),
 'port de bras':(r'port de bras|bracos',          r'port de bras'),
 'cambre':     (r'cambre|costas',                 r'cambre'),
 'abdomen':    (r'abdom|barriga|forca',           r'abdomen|abdominal'),
 'souplesse':  (r'souplesse',                     r'souplesse'),
 'temps lie':  (r'temps lie',                     r'temps lie'),
 'passe':      (r'\bpasse\b|equilibrio',          r'\bpasse\b|equilibrio'),
 'coreografia':(r'coreograf|apresentacao|espetaculo', r'coreograf'),
 'pes':        (r'trabalho de pes|pezinho|dedos dos pes|forca nos pes|\bpes? (ruim|ruins|fraco|fracos|mole|moles|torto|tortos)|pontear|esticar o pe|esticar os pes|pe esticado', r'trabalho de pes|dedos dos pes|pes e posteriores'),
 'postura':    (r'postura',                       r'postura'),
 'en dehors':  (r'en dehors|rotacao',             r'en dehors|rotacao'),
 'diagonal':   (r'diagonal|deslocamento',         r'diagonal|desloc'),
 'giro':       (r'\bgiros?\b|girar|pirueta',      r'\bgiros?\b|pirueta'),
 'equilibrio': (r'equilibrio',                    r'equilibrio'),
}
FORMATO = {  # palavras de formato que reforçam títulos
 'sequencia': (r'sequencia|exercicio|atividade', r'sequencia'),
 'barra': (r'\bbarra\b', r'\bbarra\b'),
 'centro': (r'\bcentro\b', r'\bcentro\b'),
}
EXCLUIR = r'\bentrada\b|marcha|reverence'   # no TÍTULO
PEDIU_EXCLUIDO = r'entrada|marcha|reverence|reverencia|cumprimento|despedida|final da aula'

APOSTILAS = {'apostila-kids-modulos-a-h':'Apostila Kids 1/2', 'apostila-kids-2-5-6-anos':'Apostila Kids 2 (5 a 6 anos)', 'apostila-passo-1-7-anos':'Apostila Passo 1 (7+ anos)'}
ORDEM_FAIXA = ['3-4','5-6','7+']

EH2={'A':'E','B':'F','C':'G','D':'H'}
def carregar(chunks):
    """Une os chunks de cada exercício (### Mód. X · Ex. N — Título). Mód. E–H da apostila Kids A–H = Apostila 2 (A–D): mantém só a Apostila 2."""
    ex={}
    for c in chunks:
        if c['tipo']!='apostila' or not re.match(r'Mód\.',c['section']): continue
        if c['doc']=='apostila-kids-modulos-a-h' and re.match(r'Mód\.\s*[E-H]',c['section']): continue
        k=(c['doc'],c['section'])
        if k not in ex: ex[k]={'doc':c['doc'],'section':c['section'],'faixa':c['faixa'],'title':c['title'],'text':'', 'fonte':c['fonte']}
        ex[k]['text']+=('\n\n' if ex[k]['text'] else '')+c['text']
    out=list(ex.values())
    for e in out:
        e['titulo_norm']=norm(e['section']); e['corpo_norm']=norm(e['text'])
        m=re.match(r'Mód\.\s*(\w)\s*·\s*Ex\.\s*(\d+)\s*—\s*(.*)',e['section']); e['mod'],e['num'],e['nome']=(m.groups() if m else ('','',e['section']))
        if e['doc']=='apostila-kids-modulos-a-h': e['apostila']='Apostila Kids 1 (3 a 4 anos)'; e['rotulo']=f"Apostila Kids 1, Mód. {e['mod']} · Ex. {e['num']} — {e['nome']}"
        elif e['doc']=='apostila-kids-2-5-6-anos': e['apostila']='Apostila Kids 2 (5 a 6 anos)'; e['rotulo']=f"Apostila Kids 2, Mód. {e['mod']} · Ex. {e['num']} — {e['nome']} (nas apostilas Kids A–H é o Mód. {EH2.get(e['mod'],'?')})"
        else: e['apostila']='Apostila Passo 1 (7 anos em diante)'; e['rotulo']=f"Apostila Passo 1, Mód. {e['mod']} · Ex. {e['num']} — {e['nome']}"
    return out

def faixa_ordem(f): return ORDEM_FAIXA.index(f) if f in ORDEM_FAIXA else 9

class Exercicios:
    def __init__(s, chunks): s.ex=carregar(chunks)
    def conceitos(s,q):
        n=norm(q); return [k for k,(pq,_) in CONCEITOS.items() if re.search(pq,n)]
    def buscar(s,q,age,top=3,excluir=None):
        """Retorna (lista de exercícios [(score,ex,exato)], conceitos). Só roda se houver idade + conceito/formato.
        excluir: chaves (doc,section) já entregues nesta conversa (pedido de 'outra opção')."""
        n=norm(q); cons=s.conceitos(q); exc=excluir or set()
        fmts=[k for k,(pq,_) in FORMATO.items() if re.search(pq,n)]
        if not age or not (cons or 'sequencia' in fmts): return [],cons
        if re.search(r'music|playlist|trilha sonora|cancao',n): return [],cons   # pergunta sobre música, não sobre exercício
        pediu_exc=bool(re.search(PEDIU_EXCLUIDO,n))
        def score(e):
            if not pediu_exc and re.search(EXCLUIR,e['titulo_norm']): return 0
            sc=0
            for k in cons:
                rx=CONCEITOS[k][1]
                t=len(re.findall(rx,e['titulo_norm'])); b=len(re.findall(rx,e['corpo_norm']))
                if t: sc+=6
                if b: sc+=2+min(b,4)*0.5      # corpo confirma
            for f in fmts:
                if f!='sequencia' and re.search(FORMATO[f][1],e['titulo_norm']): sc+=1.5
                if f=='sequencia' and re.search(r'sequencia',e['titulo_norm']): sc+=1
            return sc
        res=[(score(e),e) for e in s.ex if (e['doc'],e['section']) not in exc]
        res=[(sc,e) for sc,e in res if sc>0]
        if not cons:   # pedido genérico (sequência/circuito): sorteia entre os exercícios de centro/barra/diagonal/sequência da faixa
            pool=[e for e in s.ex if (e['doc'],e['section']) not in exc and e['faixa']==age and (pediu_exc or not re.search(EXCLUIR,e['titulo_norm']))
                  and re.search(r'sequencia|centro|diagonal|barra|coreograf|salto|sautes|skips',e['titulo_norm'])]
            if fmts and 'sequencia' not in fmts: pool=[e for e in pool if any(re.search(FORMATO[f][1],e['titulo_norm']) for f in fmts)] or pool
            random.shuffle(pool); return [(1.0,e,True) for e in pool[:2]],cons
        exatos=sorted([(sc,e,True) for sc,e in res if e['faixa']==age],key=lambda x:-x[0])
        if exatos and exatos[0][0]>=2: return [x for x in exatos[:top] if x[0]>=0.6*exatos[0][0]],cons
        # sem exercício na faixa: melhor da faixa mais próxima abaixo e acima (o modelo avisa a faixa de origem)
        o=faixa_ordem(age); out=[]
        for lado in (-1,1):
            cand=sorted([(sc,e,False) for sc,e in res if (faixa_ordem(e['faixa'])-o)*lado>0],key=lambda x:(abs(faixa_ordem(x[1]['faixa'])-o),-x[0]))
            if cand: out.append(cand[0])
        out.sort(key=lambda x:(x[1]['faixa']>age,))   # mais novo primeiro (mais simples de adaptar)
        return out,cons
