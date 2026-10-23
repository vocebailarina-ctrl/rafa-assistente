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
    r'|exercicios (desta|dessa|da) aula')
NAO_E = re.compile(r'experimental|tematic|pascoa|dia das maes|dia dos pais|junina|natal|halloween|carnaval|coringa|cantad|ensaio geral|figurino')
OUTRA = re.compile(r'^\s*(e )?(outra|mais uma|a proxima|proxima|me da outra|manda outra|quero outra|outra aula|outra opcao|mais uma aula|tem outra|tem mais)\b'
                   r'|^\s*(sim,? )?(manda|quero|pode mandar|me manda) (outra|mais uma)'
                   r'|^\s*(nao|n)\s*[.!]?\s*$|^\s*nao[, ]+(ajudou|ajuda|serviu|serve|funcionou|funciona|gostei)'
                   r'|preciso de outra|quero ver outra|outra opcao|outra sugestao|outra alternativa')
SIM = re.compile(r'^\s*(sim|s|ss|isso|esta|estamos|ja|ja estamos|estou|to|ta|com certeza|claro)\b|esta(mos)? ensaiando|ja comecamos|temos espetaculo|vai ter espetaculo')
NAO = re.compile(r'^\s*(nao|n|ainda nao|nem)\b|sem (espetaculo|ensaio)|nao (tem|temos|vai ter|vamos ter|estamos|esta|estou)|nao ensai')
ESPECIAL = re.compile(r'aula especial|aula tematica|ensaio com figurino')
AGE_PAT = [(r'\b(3|tres|4|quatro) anos|kids ?1|vbk ?1', '3-4'), (r'\b(5|cinco|6|seis) anos|kids ?2|vbk ?2', '5-6'),
           (r'\b(7|sete|8|oito|9|nove|10|dez|11|onze|12|doze) anos|\b7 ?\+|passo ?1', '7+'), (r'\b(2|dois) anos|\bbaby\b|\bbebe', '2-3')]


def idades(q):
    n = re.sub(r'(\d)(e|a)(\d)', r'\1 \2 \3', norm(q))
    n = re.sub(r'\b(\d+|dois|tres|quatro|cinco|seis|sete|oito|nove|dez)\s*(e|a|ou|,)\s*(\d+|dois|tres|quatro|cinco|seis|sete|oito|nove|dez)\s*anos', r'\1 anos \3 anos', n)
    return {a for p, a in AGE_PAT if re.search(p, n)}


class Trilhas:
    def __init__(s, chunks):
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
                if norm(b) not in ('brincadeira', 'festa junina (ludico)') and b not in s.brinc.setdefault(faixa, []):
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

    def bloco(s, faixa, w):
        vazia = bool(re.search(r'\*\*Brincadeira[^*]*:\*\*\s*Brincadeira\s*$', w['texto'], re.M))
        sug = s.brincadeira(faixa, w['n']) if vazia else None
        mes = NOME_MES.get(w['mes'], '')
        attrs = f'fonte="{w["fonte"]}" semana="{w["n"]}" mes="{mes}" faixa="{FAIXA_TITULO[faixa]}" ensaio="{"sim" if w["ensaio"] else "nao"}"'
        if sug: attrs += f' brincadeira_sugerida="{sug.replace(chr(34), chr(39))}"'
        return f'<aula_trilha {attrs}>\n{w["texto"]}\n</aula_trilha>'


def eh_pedido(q):
    n = norm(q)
    return bool(PEDIDO.search(n)) and not NAO_E.search(n)


class Fluxo:
    """Estado por sessão do pedido de aula completa. Devolve ('perguntar', texto) | ('aula', bloco, w) | None."""
    def __init__(s, trilhas):
        s.t = trilhas
        s.pend = {}   # session -> {'etapa': 'idade'|'ensaio', 'faixa', 'n'}
        s.ult = {}    # session -> {'faixa', 'n', 'ensaio'}  (última aula entregue)

    def _entregar(s, sess, faixa, n_ref, ensaio, avancar=False):
        w = s.t.escolher(faixa, n_ref, ensaio, avancar)
        if not w: return None
        s.ult[sess] = {'faixa': faixa, 'n': w['n'], 'ensaio': ensaio}
        s.pend.pop(sess, None)
        return ('aula', s.t.bloco(faixa, w), w)

    def _com_faixa(s, sess, faixa, q, hoje=None):
        n = s.t.semana_hoje(faixa, hoje)
        w = next(x for x in s.t.semanas[faixa] if x['n'] == n)
        if w['mes'] in (8, 9, 10, 11):
            nq = norm(q)
            if NAO.search(nq) or re.search(r'sem (espetaculo|ensaio)', nq):
                return s._entregar(sess, faixa, s.t.equivalente_sem_ensaio(faixa, n), False)
            if re.search(r'ensai|espetaculo', nq) and not NAO.search(nq):
                return s._entregar(sess, faixa, n, True)
            s.pend[sess] = {'etapa': 'ensaio', 'faixa': faixa, 'n': n}
            return ('perguntar', 'Antes de eu te mandar a aula: a sua turma já está ensaiando para o espetáculo de fim de ano? '
                    'Se estiver, te mando a aula da semana com aquecimento e ensaio; se não, te mando uma aula completa.')
        return s._entregar(sess, faixa, n, False)

    def tratar(s, sess, q, hoje=None, anterior=''):
        """anterior: última mensagem da professora (para achar a idade quando ela não repete)."""
        nq = norm(q)
        p = s.pend.get(sess)
        if p and p['etapa'] == 'ensaio':
            if SIM.search(nq) and not NAO.search(nq): return s._entregar(sess, p['faixa'], p['n'], True)
            if NAO.search(nq): return s._entregar(sess, p['faixa'], s.t.equivalente_sem_ensaio(p['faixa'], p['n']), False)
            s.pend.pop(sess, None)               # respondeu outra coisa: segue o fluxo normal
        if p and p['etapa'] == 'idade':
            ids = idades(q) - {'2-3'}
            if len(ids) == 1: return s._com_faixa(sess, ids.pop(), q, hoje)
            s.pend.pop(sess, None)
        u = s.ult.get(sess)
        if u and OUTRA.search(nq):
            return s._entregar(sess, u['faixa'], u['n'], u['ensaio'], avancar=True)
        if not eh_pedido(q): return None
        ids = idades(q) or idades(anterior)
        if ids == {'2-3'} or len(ids) > 1: return None    # baby e turma mista: fluxo normal (há conteúdo próprio)
        if not ids:
            s.pend[sess] = {'etapa': 'idade'}
            return ('perguntar', 'Me conta a idade da turma (3 a 4, 5 a 6 ou 7 anos ou mais) que eu te mando a aula da semana.')
        return s._com_faixa(sess, ids.pop(), q, hoje)
