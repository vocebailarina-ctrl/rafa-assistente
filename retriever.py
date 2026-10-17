import json, re, unicodedata, anthropic
from rank_bm25 import BM25Okapi
from indexar import norm

SYN = {  # expansão simples de consulta
 'mais alunas':'marketing divulgacao boca a boca aula experimental indicacao google whatsapp instagram retencao plano rapido','alunas novas':'marketing divulgacao boca a boca aula experimental indicacao retencao','conseguir aluna':'marketing divulgacao boca a boca aula experimental indicacao retencao','encher a turma':'marketing divulgacao boca a boca aula experimental retencao','divulga':'marketing boca a boca google instagram aula experimental plano rapido','marketing':'divulgacao boca a boca aula experimental indicacao google whatsapp instagram retencao plano rapido',
 'mista':'turma mista idades misturadas mesclando kids 1 kids 2','misturad':'turma mista mesclando kids 1 kids 2','4 e 5 anos':'turma mista mesclando kids 1 kids 2 sentindo a turma','3 e 5':'turma mista mesclando','4 a 6':'turma mista mesclando kids 1 kids 2','planejamento':'guia de aplicacao planner planejamento express formula da aula trilha anual modulo',
 'sem material':'musicas cantadas cantiga aula coringa qualquer objeto nenhum material','nao tenho material':'musicas cantadas cantiga aula coringa','cantada':'musicas cantadas cantiga elefante borboletinha','cantiga':'musicas cantadas','que aula':'aula coringa musicas cantadas hora de brincar aula tematica','aula experimental':'musicas cantadas mini baby circuito hora de brincar',
 'certificado':'marcas da danca certificados conclusao','lembrancinha':'lacinho certificado marcas da danca maozinha','meninos':'menino soldadinho saltos reverence','menino':'meninos soldadinho','espelho':'autopercepcao imagem movimento','auxiliar':'assistente em sala auxiliar','horario':'manha tarde turma lista de interessados','drt':'registro profissional cref sated','mei':'cnpj cnae regularizar','sistema':'gestao matricula cobranca app digidanca','contrato':'advogado matricula taxa','ferias':'julho dezembro mensalidade calendario','playlist':'musicas drive link curso apostila','login':'kiwify acesso senha app','senha':'kiwify acesso login',
 'preco':'cobrar valor aula cobrança parceria porcentagem','cobrar':'preco valor parceria','valor':'preco cobrar',
 'birra':'choro chorar teimosia','autista':'autismo neurodivergente neurodivergencia tea','autismo':'neurodivergente tea sinais de atencao observar','neurodivergente':'autismo sinais de atencao psicomotricidade',
 'espetaculo':'apresentacao show roteiro tema','coreografia':'desenho coreografico deslocamento sequencia',
 'baby':'mini baby 2 anos 3 anos pequenas','bebe':'baby 2 anos','pais':'mae familia responsaveis','mae':'pais familia',
 'lembrancinha':'material lembranca presente mimo','datas':'comemorativas tematica dia das maes pascoa festa junina',
 'planejamento':'planner formula trilha semana modulo','musica':'trilha sonora playlist andamento',
}
AGE = [(r'\b(2|dois) anos|\bbaby\b|\bbebe','2-3'),(r'\b(3|tres) anos|\b(4|quatro) anos','3-4'),(r'\b(5|cinco) anos|\b(6|seis) anos','5-6'),(r'\b(7|sete|8|oito|9|nove|10|dez) anos|\b(7|sete)\+','7+')]
COMPAT = {'2-3':{'2-3','3-4','3-6','todas','3-7'},'3-4':{'3-4','3-6','todas','3-7','2-3'},'5-6':{'5-6','3-6','4-6','todas','3-7'},'7+':{'7+','todas'}}

class Retriever:
    def __init__(s, path='base_chunks.json'):
        s.chunks=json.load(open(path))
        s.bm25=BM25Okapi([c['norm'].split() for c in s.chunks])
        s.client=anthropic.Anthropic()
    def _expand(s,q):
        n=norm(q); extra=' '.join(v for k,v in SYN.items() if k in n)
        return (n+' '+norm(extra)).split()
    def _age(s,q):
        n=norm(q)
        # "4 e 5 anos", "de 3 a 6 anos": aplica o padrão a cada número citado
        n=re.sub(r'\b(\d|dois|tres|quatro|cinco|seis|sete|oito|nove|dez)\s*(e|a|ou|,)\s*(\d|dois|tres|quatro|cinco|seis|sete|oito|nove|dez)\s*anos', r'\1 anos \3 anos', n)
        found={a for pat,a in AGE if re.search(pat,n)}
        return found.pop() if len(found)==1 else None
    def search(s,q,k=25):
        toks=s._expand(q); scores=s.bm25.get_scores(toks)
        age=s._age(q)
        ranked=sorted(range(len(s.chunks)),key=lambda i:-scores[i])
        out=[]
        for i in ranked:
            c=s.chunks[i]
            if c['tipo'] in ('secundario','sistema'): continue
            if age and c['faixa'] not in COMPAT[age]: continue
            if c['tipo']=='artigo' and scores[i]<max(scores)*0.6: continue
            key=(c['doc'],c['section'])
            if sum(1 for _,x in out if (x['doc'],x['section'])==key)>=2: continue
            out.append((scores[i],c))
            if len(out)>=k: break
        return out
    def rerank(s,q,cands,top=6):
        if not cands: return []
        lst="\n".join(f"[{j}] ({c['doc']} › {c['section'][:60]}) {c['text'][:400].replace(chr(10),' ')}" for j,(sc,c) in enumerate(cands))
        r=s.client.messages.create(model="claude-sonnet-5-5",max_tokens=200,thinking={"type":"between_tools"},
            system="Você seleciona trechos de uma base de conhecimento sobre ballet infantil que respondem a uma pergunta de professora. Responda SOMENTE com os índices dos trechos mais úteis, do mais ao menos útil, separados por vírgula (até 6). Prefira trechos da Rafa (lives, orientações, cursos) a artigos genéricos; respeite a faixa etária da pergunta.",
            messages=[{"role":"user","content":f"Pergunta: {q}\n\nTrechos:\n{lst}"}])
        txt="".join(b.text for b in r.content if b.type=="text")
        idx=[int(x) for x in re.findall(r'\d+',txt) if int(x)<len(cands)]
        seen=[];[seen.append(i) for i in idx if i not in seen]
        return [cands[i][1] for i in seen[:top]]
    def retrieve(s,q,top=6):
        return s.rerank(q,s.search(q),top)
