"""Aula completa a partir das Trilhas anuais (3-4, 5-6, 7+).

Fluxo:
- Pedido de aula completa + idade -> semana da trilha que corresponde à data de hoje (Brasil).
- "outra aula" -> próxima semana da mesma trilha, no mesmo modo (ensaio / sem ensaio).
- Agosto a novembro: antes de entregar, pergunta se a turma está ensaiando para o espetáculo.
  sim -> semana atual (aquecimento + ensaio); não -> semana equivalente de fev-jun (aula completa).
- Sem idade -> pergunta a idade. Semanas especiais (Páscoa, ensaio com figurino) são puladas.
- Brincadeira vazia ("Brincadeira") -> sugere uma brincadeira real da própria trilha daquela idade.
"""
import re, datetime as dt
from indexar import norm
from exercicios import carregar as carregar_exercicios

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo('America/Sao_Paulo')
except Exception:  # sem base de fusos: usa UTC-3
    TZ = dt.timezone(dt.timedelta(hours=-3))

MESES = {'Fev': 2, 'Mar': 3, 'Abr': 4, 'Mai': 5, 'Jun': 6, 'Ago': 8, 'Set': 9, 'Out': 10, 'Nov': 11}
NOME_MES = {2: 'fevereiro', 3: 'março', 4: 'abril', 5: 'maio', 6: 'junho', 8: 'agosto', 9: 'setembro', 10: 'outubro', 11: 'novembro'}
FAIXA_TITULO = {'3-4': '3 a 4 anos (VBK 1)', '5-6': '5 a 6 anos (VBK 2)', '7+': '7 anos ou mais (Passo 1)'}

PEDIDO = re.compile(
    r'aula (completa|pronta|inteira|toda|do dia|da semana|para (amanha|hoje|essa semana|esta semana))'
    r'|plano de aula|planejamento da aula|roteiro de aula|roteiro da aula|planejar (uma |a )?aula|montar (uma |a )?aula'
    r'|(monta|manda|mandar|me da|me de|me traga|me traz|traz|traga|passa|passar|sugere|sugerir|preciso de|quero|tem) (uma |a )?aula\b'
    r'|^\s*(uma )?aula (de ballet |de bale |de bale infantil )?(para|pra|p/) (criancas|alunas|turma|minha|meninas|\d)'
    r'|o que (eu )?(dou|faco|vou dar|posso dar) (na|de|em|nessa|na minha) aula|(tem|existe|qual) (uma |a )?trilha (a seguir|para seguir|pra seguir)'
    r'|exercicios (desta|dessa|da) aula|qual aula (eu )?(dou|faco|vou dar|posso dar|darei|aplico)')
NAO_E = re.compile(r'experimental|tematic|pascoa|dia das maes|dia dos pais|junina|natal|halloween|carnaval|coringa|cantad|ensaio geral|figurino')
OUTRA = re.compile(r'^\s*(e )?(outra|mais uma|a proxima|proxima|me da outra|manda outra|quero outra|outra aula|outra opcao|mais uma aula|tem outra|tem mais)\b'
                   r'|^\s*(sim,? )?(manda|quero|pode mandar|me manda) (outra|mais uma)'
                   r'|^\s*(nao|n)\s*[.!]?\s*$|^\s*nao[, ]+(ajudou|ajuda|serviu|serve|funcionou|funciona|gostei)'
                   r'|preciso de outra|quero ver outra|outra opcao|outra sugestao|outra alternativa')
SIM = re.compile(r'^\s*(sim|s|ss|isso|esta|estamos|ja|ja estamos|estou|to|ta|com certeza|claro)\b|esta(mos)? ensaiando|ja comecamos|temos espetaculo|vai ter espetaculo')
NAO = re.compile(r'^\s*(nao|n|ainda nao|nem)\b|sem (espetaculo|ensaio)|nao (tem(?! problema)|temos(?! problema)|vai ter|vamos ter|estamos|esta|estou)|nao ensai')
ESPECIAL = re.compile(r'aula especial|aula tematica|ensaio com figurino')
AGE_PAT = [(r'\b(3|tres|4|quatro) anos|kids ?1|vbk ?1', '3-4'), (r'\b(5|cinco|6|seis) anos|kids ?2|vbk ?2|pre[ -]?bal+e?t?', '5-6'),
           (r'\b(7|sete|8|oito|9|nove|10|dez|11|onze|12|doze) anos|\b7 ?\+|passo ?1', '7+'), (r'\b(2|dois) anos|\bbaby\b|\bbebe|ano e meio|\b(1|um) ano\b|\b(12|15|18|20|22) meses', '2-3')]


def idades(q):
    n = re.sub(r'(\d)(e|a)(\d)', r'\1 \2 \3', norm(q))
    n = re.sub(r'\b(\d+|dois|tres|quatro|cinco|seis|sete|oito|nove|dez)\s*(e|a|ou|,)\s*(\d+|dois|tres|quatro|cinco|seis|sete|oito|nove|dez)\s*anos', r'\1 anos \3 anos', n)
    return {a for p, a in AGE_PAT if re.search(p, n)}


class Trilhas:
    def __init__(s, chunks):
        s._montar_indices(chunks)
        s.semanas = {}   # faixa -> [ {n, mes, texto, ensaio, especial} ] ordenado
        s.brinc = {}     # faixa -> [texto de brincadeira real]
        for c in chunks:
            t = c.get('title', '')
            if not t.startswith('Trilha anual'): continue
            faixa = '3-4' if '3-4' in t else '5-6' if '5-6' in t else '7+' if '7+' in t else None
            m = re.match(r'Semana (\d+) — (\w{3})', c.get('section', ''))
            if not faixa or not m: continue
            txt = c['text']
            s.semanas.setdefault(faixa, []).append({
                'n': int(m.group(1)), 'mes': MESES.get(m.group(2)), 'texto': txt,
                'ensaio': '**Ensaio:** Sim' in txt, 'especial': bool(ESPECIAL.search(norm(txt))), 'fonte': t})
            for b in re.findall(r'\*\*Brincadeira[^*]*:\*\*\s*(.+)', txt):
                b = b.strip()
                if _chave(b) not in ('brincadeira', 'festa junina ludico') and b not in s.brinc.setdefault(faixa, []):
                    s.brinc[faixa].append(b)
        for f in s.semanas: s.semanas[f].sort(key=lambda x: x['n'])

    # ---------- escolha da semana ----------
    def _uteis(s, faixa, ensaio):
        return [w for w in s.semanas.get(faixa, []) if not w['especial'] and w['ensaio'] == ensaio]

    def semana_hoje(s, faixa, hoje=None):
        """Semana da trilha que corresponde à data (calendário do ano letivo: fev-jun, ago-nov)."""
        hoje = hoje or dt.datetime.now(TZ).date()
        mes = hoje.month
        if mes in (12, 1): return s.semanas[faixa][0]['n']                     # início do ano: semana 1
        if mes == 7: mes = 6                                                   # julho (férias): última fase de junho
        do_mes = [w for w in s.semanas.get(faixa, []) if w['mes'] == mes]
        if not do_mes: return s.semanas[faixa][0]['n']
        i = min((hoje.day - 1) // 7, len(do_mes) - 1)
        return do_mes[i]['n']

    def escolher(s, faixa, n_ref, ensaio, avancar=False):
        """avancar=True ('outra'): próxima semana útil depois de n_ref, dando a volta no fim.
        Senão: a semana útil mais próxima de n_ref (prefere o mesmo mês; empate -> a anterior),
        para não pular de outubro para agosto quando a semana do dia é especial ou falta."""
        uteis = s._uteis(faixa, ensaio)
        if not uteis: return None
        if avancar:
            cand = [w for w in uteis if w['n'] > n_ref]
            return cand[0] if cand else uteis[0]
        ref = next((w for w in s.semanas[faixa] if w['n'] == n_ref), None)
        mes = ref['mes'] if ref else None
        return min(uteis, key=lambda w: (w['mes'] != mes, abs(w['n'] - n_ref), w['n'] > n_ref))

    def equivalente_sem_ensaio(s, faixa, n):
        """Semana de ago-nov -> mesma posição no semestre fev-jun (ex.: 31 -> 11)."""
        uteis = s._uteis(faixa, False)
        primeira_ago = min((w['n'] for w in s.semanas[faixa] if w['mes'] == 8), default=21)
        return (uteis[0]['n'] + (n - primeira_ago)) if uteis else 1

    def brincadeira(s, faixa, n):
        lst = s.brinc.get(faixa) or []
        return lst[n % len(lst)] if lst else None

    # ---------- cruzamento: trilha -> exercício completo da apostila / brincadeira completa ----------
    def _montar_indices(s, chunks):
        s.ex = {(e['doc'], e['mod'], e['num']): e for e in carregar_exercicios(chunks)}
        s.brinc_txt = {}
        for c in chunks:                                   # explicações da Rafa: parágrafos "**Nome** ..."
            if c['title'].startswith('Trilha'): continue
            for p in re.split(r'\n\s*\n', c['text']):
                m = re.match(r'\s*\*\*(.+?)\*\*\s*(.*)', p, re.S)
                if m and len(p.split()) > 15:
                    k = _chave(m.group(1))
                    if k and k not in s.brinc_txt:
                        s.brinc_txt[k] = (m.group(1).strip(' .:'), _limpa(m.group(2)).lstrip('. '), c['title'])
        ebook = '\n'.join(c['text'] for c in sorted((c for c in chunks if c['title'] == 'brincadeira-dancada'), key=lambda c: c['i']))
        s.ebook = ebook                                    # e-book Brincadeira Dançada: "Nome / OBJETIVO / MATERIAIS / DESCRIÇÃO"
        s.ebook_n = norm(ebook)

    def _brinc_completa(s, nome):
        k = _chave(nome)
        rafa = next((v for kk, v in s.brinc_txt.items() if kk == k or kk.startswith(k) or k.startswith(kk)), None)
        obj = mat = None
        for m in re.finditer(re.escape(nome.split('/')[0].strip()[:14]), s.ebook, re.I):
            bloco = s.ebook[m.start(): m.start() + 1500]
            if 'OBJETIVO' in bloco[:200]:
                bloco = bloco.split('Clique aqui')[0]
                o = re.search(r'OBJETIVO:\s*(.+?)(?=MATERIA|DESCRI)', bloco, re.S)
                ma = re.search(r'MATERIAIS?:\s*(.+?)(?=DESCRI|$)', bloco, re.S)
                obj = _limpa(o.group(1)) if o else None
                mat = _limpa(ma.group(1)) if ma else None
                if not rafa:
                    de = re.search(r'DESCRIÇÃO DA ATIVIDADE\s*(.+)', bloco, re.S)
                    if de: rafa = (nome, _limpa(de.group(1)), 'E-book Brincadeira Dançada')
                break
        if not rafa: return None
        partes = [rafa[1]]
        if obj: partes.insert(0, f'*Objetivo:* {obj}')
        if mat: partes.insert(1 if obj else 0, f'*Materiais:* {mat}')
        return rafa[0], '\n'.join(partes), rafa[2]

    def montar(s, faixa, w, nota=None):
        """Aula completa: cada exercício da trilha vem COMPLETO da apostila; a brincadeira, completa.
        Devolve (texto, fontes, estrutura) — estrutura = {titulo, intro, etapas:[{titulo, ref, corpo}], rodape}."""
        mes = NOME_MES.get(w['mes'], '')
        titulo = f"Aula da semana {w['n']} ({mes}) — Trilha anual, turma de {FAIXA_TITULO[faixa]}"
        intro = ('Nesta fase do ano a aula é aquecimento + ensaio: a coreografia vem do material do espetáculo (5 Temas de Espetáculo). '
                 if w['ensaio'] else '') + 'Toque em cada etapa para ver o exercício completo.'
        if nota: intro = nota + ' ' + intro
        fontes = {w['fonte']}; etapas = []; rodape = []
        for linha in w['texto'].split('\n'):
            m = re.match(r'\s*-\s*\*\*(.+?):\*\*\s*(.*)', linha)
            if not m: continue
            etapa, conteudo = m.group(1).strip(), m.group(2).strip()
            if etapa.lower().startswith('ensaio') or conteudo in ('', '(aula especial)'): continue
            if etapa.lower().startswith(('aula 2', 'foco / aula 2')):
                rodape.append(f'**{etapa}:** {conteudo}'); continue
            r = re.match(r'Mód\.\s*(\w)\s*·\s*Ex\.\s*(\d+)\s*—\s*([^—]+)', conteudo)
            e = s.ex.get((DOC_FAIXA[faixa], r.group(1), r.group(2))) if r else None
            if e:
                tit = etapa if norm(e['nome']) == norm(etapa) else f"{etapa}: {e['nome']}"
                etapas.append({'titulo': tit, 'ref': e['rotulo'], 'corpo': _exercicio_md(e['text'])})
                fontes.add(e['apostila']); continue
            if etapa.lower().startswith('brincadeira'):
                nome = conteudo
                if _chave(conteudo) in ('brincadeira', 'festa junina ludico'):
                    nome = s.brincadeira(faixa, w['n']) or ''
                nome_curto = re.match(r'(.+?)(?=[A-ZÁÉ“"][a-zà-ú ]|$)', nome).group(1).strip() if nome else ''
                b = s._brinc_completa(nome_curto) if nome_curto else None
                if b:
                    extra = ' (sugestão da própria trilha)' if _chave(conteudo) in ('brincadeira', 'festa junina ludico') else ''
                    etapas.append({'titulo': f'{etapa}: {b[0]}{extra}', 'ref': 'Brincadeira Dançada', 'corpo': b[1]})
                    fontes.add('Brincadeira Dançada')
                elif nome:
                    etapas.append({'titulo': f'{etapa}: {nome_curto or nome}', 'ref': '', 'corpo': nome})
                continue
            etapas.append({'titulo': f'{etapa}', 'ref': '', 'corpo': conteudo.lstrip('→ ').capitalize() if conteudo.startswith('→') else conteudo})
        fim = 'Fonte: ' + ' · '.join(sorted(fontes)) + '.\nQuer outra aula? É só pedir "outra" que eu te mando a da semana seguinte.'
        if faixa == '3-4':
            fim += '\nDia sem material? A Rafa também tem a aula coringa Músicas Cantadas, só com cantigas: é só me pedir "aula de músicas cantadas".'
        rodape.append(fim)
        partes = [f'**{titulo}**', intro]
        for et in etapas:
            partes.append(f"\n**{et['titulo']}**" + (f"\n_{et['ref']}_" if et['ref'] else '') + f"\n{et['corpo']}")
        partes.append('\n' + '\n'.join(rodape))
        estrutura = {'titulo': titulo, 'intro': intro, 'etapas': etapas, 'rodape': '\n'.join(rodape)}
        return '\n'.join(partes), sorted(fontes), estrutura


DOC_FAIXA = {'3-4': 'apostila-kids-modulos-a-h', '5-6': 'apostila-kids-2-5-6-anos', '7+': 'apostila-passo-1-7-anos'}


def _chave(t):
    return re.sub(r'[^a-z0-9 ]', ' ', norm(t)).split() and ' '.join(re.sub(r'[^a-z0-9 ]', ' ', norm(t)).split())


def _limpa(t):
    """Junta linhas quebradas do PDF ('...os dois\\nlados' -> '...os dois lados')."""
    t = re.sub(r'[ \t]*\n[ \t]*/?[ \t]*', '\n', t.strip())
    t = re.sub(r'(?<![.:!?])\n(?=[a-zà-ú0-9(])', ' ', t)
    return re.sub(r'\n{2,}', '\n', t).strip()


def _exercicio_md(txt):
    """Texto completo da apostila, só reorganizado para ler no celular (nenhuma palavra trocada)."""
    t = re.sub(r'^###.*\n', '', txt).strip()
    obj = re.search(r'Objetivos:\s*(.+?)(?=\n\s*Desenvolvimento do exerc|\n\s*Materiais:|$)', t, re.S)
    resto = t[obj.end():] if obj else t
    resto = re.sub(r'^\s*Desenvolvimento do exerc[ií]cio\s*', '', resto.strip())
    linhas = []
    if obj:
        itens = [i.strip(' .;') for i in _limpa(obj.group(1)).split('\n') if i.strip(' .;')]
        linhas.append('*Objetivos:* ' + '; '.join(itens) + '.')
    corpo = _limpa(resto)
    for l in corpo.split('\n'):
        l = l.strip()
        if not re.search(r'\w', l): continue
        m = re.match(r'(Materiais|Início|Inicio|Observação|Obs\.?|Dica)\s*:\s*(.*)', l)
        linhas.append(f'*{m.group(1)}:* {m.group(2)}' if m else f'- {l}')
    return '\n'.join(linhas)


def eh_pedido(q):
    n = norm(q)
    return bool(PEDIDO.search(n)) and not NAO_E.search(n)


NOTA_BABY = ('A Trilha anual começa em 3 anos. Para a sua turma mais nova (até 2 anos e meio), esta é a aula da trilha de 3 a 4 anos (Kids 1), '
             'a mais próxima. Para essa idade (inclusive crianças de 1 ano e meio) a Rafa também tem a aula Mini Baby, o circuito mágico até o castelo da Fada Madrinha: é só pedir "Mini Baby" que eu mando completa.')
ROTULO = {'3-4': '3 a 4 anos', '5-6': '5 a 6 anos', '7+': '7 anos ou mais'}


NUM = {'dois': 2, 'tres': 3, 'quatro': 4, 'cinco': 5, 'seis': 6, 'sete': 7, 'oito': 8, 'nove': 9, 'dez': 10, 'onze': 11, 'doze': 12}
PERG_IDADE = 'Me conta a idade da turma que eu te mando a aula da semana completa.'
PERG_ENSAIO = 'Antes de eu te mandar a aula: a sua turma já está ensaiando para o espetáculo de fim de ano?'


def idades_resposta(q):
    """Resposta à pergunta da idade: aceita também número solto ('3 ou 4', '4', 'tres')."""
    ids = idades(q)
    if ids: return ids
    out = set()
    for t in re.findall(r'\d+|[a-z]+', norm(q)):
        n = int(t) if t.isdigit() else NUM.get(t)
        if n is None or not 2 <= n <= 14: continue
        out.add('2-3' if n == 2 else '3-4' if n <= 4 else '5-6' if n <= 6 else '7+')
    return out


def resolver_faixa(ids):
    """{'2-3'} -> ('3-4', nota); idades misturadas -> ('mista', [faixas]); uma faixa -> (faixa, None); nada -> (None, None)."""
    if not ids: return None, None
    nota = NOTA_BABY if '2-3' in ids else None
    fs = sorted({'3-4' if f == '2-3' else f for f in ids}, key=['3-4', '5-6', '7+'].index)
    if len(fs) == 1: return fs[0], nota
    return 'mista', fs


class Fluxo:
    """Estado por sessão do pedido de aula completa. Devolve ('perguntar', texto) | ('aula', texto, w, fontes, estrutura) | None."""
    def __init__(s, trilhas):
        s.t = trilhas
        s.pend = {}   # session -> {'etapa': 'idade'|'ensaio'|'mista', ...}
        s.ult = {}    # session -> {'faixa', 'n', 'ensaio', 'nota'}  (última aula entregue)

    def _entregar(s, sess, faixa, n_ref, ensaio, avancar=False, nota=None):
        w = s.t.escolher(faixa, n_ref, ensaio, avancar)
        if not w: return None
        s.ult[sess] = {'faixa': faixa, 'n': w['n'], 'ensaio': ensaio, 'nota': nota}
        s.pend.pop(sess, None)
        txt, fontes, est = s.t.montar(faixa, w, nota)
        return ('aula', txt, w, fontes, est)

    def _com_faixa(s, sess, faixa, q, hoje=None, nota=None):
        n = s.t.semana_hoje(faixa, hoje)
        w = next(x for x in s.t.semanas[faixa] if x['n'] == n)
        if w['mes'] in (8, 9, 10, 11):
            nq = norm(q)
            if NAO.search(nq) or re.search(r'sem (espetaculo|ensaio)', nq):
                return s._entregar(sess, faixa, s.t.equivalente_sem_ensaio(faixa, n), False, nota=nota)
            if re.search(r'ensai|espetaculo', nq) and not NAO.search(nq):
                return s._entregar(sess, faixa, n, True, nota=nota)
            s.pend[sess] = {'etapa': 'ensaio', 'faixa': faixa, 'n': n, 'nota': nota}
            return ('perguntar', PERG_ENSAIO + ' '
                    'Se estiver, te mando a aula da semana com aquecimento e ensaio; se não, te mando uma aula completa.')
        return s._entregar(sess, faixa, n, False, nota=nota)

    def _por_idades(s, sess, ids, q, hoje):
        f, extra = resolver_faixa(ids)
        if f == 'mista':
            s.pend[sess] = {'etapa': 'mista', 'opcoes': extra}
            nomes = ' ou '.join(ROTULO[x] for x in extra)
            return ('perguntar', f'A Trilha anual é organizada por idade. Para a sua turma misturada, monto pela trilha de {nomes}? '
                    'Se não souber, comece pela da mais nova: fica mais fácil para todas acompanharem.')
        return s._com_faixa(sess, f, q, hoje, nota=extra)

    def tratar(s, sess, q, hoje=None, anterior='', bot_anterior='', usuarias=()):
        """anterior: última mensagem da professora; bot_anterior: última resposta do assistente;
        usuarias: mensagens anteriores da professora. Servem para retomar a conversa se o servidor reiniciou."""
        nq = norm(q)
        p = s.pend.get(sess)
        if not p and bot_anterior.startswith(PERG_IDADE[:30]):
            p = s.pend[sess] = {'etapa': 'idade'}
        if not p and bot_anterior.startswith(PERG_ENSAIO[:30]):
            f, nota = resolver_faixa(next((idades_resposta(u) for u in reversed(list(usuarias)) if idades_resposta(u)), set()))
            if f and f != 'mista':
                p = s.pend[sess] = {'etapa': 'ensaio', 'faixa': f, 'n': s.t.semana_hoje(f, hoje), 'nota': nota}
        if p and p['etapa'] == 'ensaio':
            if SIM.search(nq) and not NAO.search(nq): return s._entregar(sess, p['faixa'], p['n'], True, nota=p.get('nota'))
            if NAO.search(nq): return s._entregar(sess, p['faixa'], s.t.equivalente_sem_ensaio(p['faixa'], p['n']), False, nota=p.get('nota'))
            s.pend.pop(sess, None)               # respondeu outra coisa: segue o fluxo normal
        if p and p['etapa'] == 'mista':
            ids = {'3-4' if f == '2-3' else f for f in idades(q)} & set(p['opcoes'])
            if len(ids) == 1: return s._com_faixa(sess, ids.pop(), q, hoje)
            if re.search(r'mais nova|menor|novinha|pequen|primeira|^\s*(sim|pode|ok|isso)\b', nq): return s._com_faixa(sess, p['opcoes'][0], q, hoje)
            if re.search(r'mais velha|maior|segunda', nq): return s._com_faixa(sess, p['opcoes'][-1], q, hoje)
            s.pend.pop(sess, None)
        if p and p['etapa'] == 'idade':
            ids = idades_resposta(q)
            if ids: return s._por_idades(sess, ids, q, hoje)
            s.pend.pop(sess, None)
        u = s.ult.get(sess)
        if u and OUTRA.search(nq):
            return s._entregar(sess, u['faixa'], u['n'], u['ensaio'], avancar=True, nota=u.get('nota'))
        if not eh_pedido(q): return None
        ids = idades(q) or idades(anterior)
        if not ids:
            s.pend[sess] = {'etapa': 'idade'}
            return ('perguntar', PERG_IDADE)
        return s._por_idades(sess, ids, q, hoje)
