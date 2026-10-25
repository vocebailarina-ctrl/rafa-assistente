import json, re, unicodedata, anthropic
from rank_bm25 import BM25Okapi
from indexar import norm
from exercicios import Exercicios, EXCLUIR, PEDIU_EXCLUIDO

SYN = {  # expansão simples de consulta
 'mais alunas':'marketing divulgacao boca a boca aula experimental indicacao google whatsapp instagram retencao plano rapido','alunas novas':'marketing divulgacao boca a boca aula experimental indicacao retencao','conseguir aluna':'marketing divulgacao boca a boca aula experimental indicacao retencao','encher a turma':'marketing divulgacao boca a boca aula experimental retencao','divulga':'marketing boca a boca google instagram aula experimental plano rapido','marketing':'divulgacao boca a boca aula experimental indicacao google whatsapp instagram retencao plano rapido',
 'mista':'turma mista idades misturadas mesclando kids 1 kids 2','misturad':'turma mista mesclando kids 1 kids 2','4 e 5 anos':'turma mista mesclando kids 1 kids 2 sentindo a turma','3 e 5':'turma mista mesclando','4 a 6':'turma mista mesclando kids 1 kids 2','planejamento':'guia de aplicacao planner planejamento express formula da aula trilha anual modulo',
 'sem material':'musicas cantadas cantiga aula coringa qualquer objeto nenhum material','nao tenho material':'musicas cantadas cantiga aula coringa','cantada':'musicas cantadas cantiga elefante borboletinha','cantiga':'musicas cantadas','que aula':'aula coringa musicas cantadas hora de brincar aula tematica','aula experimental':'musicas cantadas mini baby circuito hora de brincar',
 'certificado':'marcas da danca certificados conclusao','lembrancinha':'lacinho certificado marcas da danca maozinha','meninos':'menino soldadinho saltos reverence','menino':'meninos soldadinho','espelho':'autopercepcao imagem movimento','auxiliar':'assistente em sala auxiliar','horario':'manha tarde turma lista de interessados','drt':'registro profissional cref sated','mei':'cnpj cnae regularizar','sistema':'gestao matricula cobranca app digidanca','contrato':'advogado matricula taxa','ferias':'julho dezembro mensalidade calendario','playlist':'musicas drive link curso apostila','login':'kiwify acesso senha app','senha':'kiwify acesso login',
 'preco':'cobrar valor aula cobrança parceria porcentagem','cobrar':'preco valor parceria','valor':'preco cobrar',
 'birra':'choro chorar teimosia live como lidar com a birra nao quero fazer autoridade','barulho':'medo som sensibilidade birra como lidar com a birra autoridade musicas cantadas','atencao':'concentracao foco dispersa brincadeira combinados','prestando atencao':'concentracao foco dispersa brincadeira combinados autoridade','nao presta':'atencao concentracao foco autoridade combinados','dispers':'atencao concentracao foco','agitad':'tonicidade atencao energia brincadeira','bagunca':'autoridade combinados atencao','pe ruim':'trabalho de pes forca dos pes dedos dos pes pointe','pes ruins':'trabalho de pes forca dos pes dedos dos pes pointe','autista':'autismo neurodivergente neurodivergencia tea','autismo':'neurodivergente tea sinais de atencao observar','neurodivergente':'autismo sinais de atencao psicomotricidade',
 'espetaculo':'apresentacao show roteiro tema coreografia de sucesso 7 recursos','coreografia':'desenho coreografico deslocamento sequencia',
 'baby':'mini baby 2 anos 3 anos pequenas','ano e meio':'psicomotricidade guia observacao mini baby 2 anos','1 ano':'psicomotricidade guia observacao mini baby 2 anos','18 meses':'psicomotricidade guia observacao mini baby 2 anos','bebe':'baby 2 anos','pais':'mae familia responsaveis','mae':'pais familia',
 'lembrancinha':'material lembranca presente mimo','datas':'comemorativas tematica dia das maes pascoa festa junina',
 'planejamento':'planner formula trilha semana modulo','musica':'trilha sonora playlist andamento',
}
AGE = [(r'\b(2|dois) anos|\bbaby\b|\bbebe|ano e meio|\b(1|um) ano\b|\b(12|15|18|20|22) meses','2-3'),(r'\b(3|tres) anos|\b(4|quatro) anos','3-4'),(r'\b(5|cinco) anos|\b(6|seis) anos|pre[ -]?bal+e?t?\b','5-6'),(r'\b(7|sete|8|oito|9|nove|10|dez) anos|\b(7|sete)\+','7+')]
COMPAT = {'2-3':{'2-3','3-4','3-6','todas','3-7'},'3-4':{'3-4','3-6','todas','3-7','2-3'},'5-6':{'5-6','3-6','4-6','todas','3-7'},'7+':{'7+','todas'}}

class Retriever:
    def __init__(s, path='base_chunks.json'):
        s.chunks=json.load(open(path))
        s.bm25=BM25Okapi([c['norm'].split() for c in s.chunks])
        s.client=anthropic.Anthropic()
        s.ex=Exercicios(s.chunks)
    def _expand(s,q):
        n=norm(q); extra=' '.join(v for k,v in SYN.items() if k in n)
        return (n+' '+norm(extra)).split()
    def _age(s,q):
        n=norm(q)
        # "4 e 5 anos", "de 3 a 6 anos": aplica o padrão a cada número citado
        n=re.sub(r'\b(\d|dois|tres|quatro|cinco|seis|sete|oito|nove|dez)\s*(e|a|ou|,)\s*(\d|dois|tres|quatro|cinco|seis|sete|oito|nove|dez)\s*anos', r'\1 anos \3 anos', n)
        found={a for pat,a in AGE if re.search(pat,n)}
        return found.pop() if len(found)==1 else None
    def search(s,q,k=25,excluir=None):
        exc=excluir or set()
        toks=s._expand(q); scores=s.bm25.get_scores(toks)
        age=s._age(q); pediu_exc=bool(re.search(PEDIU_EXCLUIDO,norm(q)))
        ranked=sorted(range(len(s.chunks)),key=lambda i:-scores[i])
        out=[]
        for i in ranked:
            c=s.chunks[i]
            if c['tipo'] in ('secundario','sistema'): continue
            if (c['doc'],c['section']) in exc: continue   # já entregue: pedido de outra opção
            if age and c['faixa'] not in COMPAT[age]: continue
            if c['tipo']=='apostila' and not pediu_exc and re.search(EXCLUIR,norm(c['section'])): continue   # nunca entrega entrada/révérence sem pedido
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
    def retrieve(s,q,top=6,excluir=None):
        return s.rerank(q,s.search(q,excluir=excluir),top)

    def exercicios(s,q,excluir=None):
        """Pedido de exercício/sequência para uma idade -> (lista [(score,ex,exato)], idade)."""
        age=s._age(q)
        r,_=s.ex.buscar(q,age,top=2,excluir=excluir) if age else ([],[])
        return r,age
