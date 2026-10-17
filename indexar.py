"""Indexa base/*.md em chunks com metadados (doc, título, seção, faixa etária, tipo, fonte/vídeo)."""
import re, json, glob, os, unicodedata

META = {  # faixa etária e tipo por documento (prefixo do nome)
 'trilha-3-4':('3-4','trilha'),'trilha-5-6':('5-6','trilha'),'trilha-7mais':('7+','trilha'),
 'apostila-kids-modulos-a-h':('3-4','apostila'),'apostila-kids-2-5-6-anos':('5-6','apostila'),'apostila-passo-1-7-anos':('7+','apostila'),
 'aula-mini-baby':('2-3','aula'),'aula-historiada-fada-madrinha':('3-6','aula'),'aula-tematica-dia-das-maes':('3-6','aula'),
 'guia-psicomotricidade-kids2':('4-6','guia'),'live-':('todas','live'),'ebook-espetaculo':('todas','ebook'),
 'curso-coreografia':('todas','curso'),'curso-musicas-cantadas':('3-6','curso'),'5-temas':('todas','ebook'),'brincadeira-dancada':('3-7','curso'),
 'planner-':('todas','planner'),'planejamento-express':('todas','planner'),'video-':('todas','video'),
 'videoteca-':('todas','video'),'rafa-':('todas','orientacao'),'artigos/':('todas','artigo'),
 'anuncio-':('todas','secundario'),'pesquisa-':('todas','pesquisa'),'_suporte':('todas','suporte'),'_catalogo':('todas','catalogo'),'_':('todas','sistema'),
}
def meta(path):
    rel=path.split('base/')[1]
    for k,v in META.items():
        if rel.startswith(k): return v
    return ('todas','outro')

def norm(s):
    s=unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9 ]+',' ',s)

def chunk_doc(path, max_words=350):
    txt=open(path).read()
    title=re.search(r'^# (.*)',txt,flags=re.M); title=title.group(1).strip() if title else None
    if not title:
        m=re.search(r'^\*\*?([^*\n]{5,120})\*\*?\s*$',txt,flags=re.M)
        title=('Artigo do blog Você Bailarina: '+m.group(1).strip().title()) if m else os.path.basename(path).replace('.md','').replace('_',' ')
    src=re.search(r'^\*(.*?)\*\s*$',txt,flags=re.M|re.S); src=src.group(1).strip()[:300] if src else ''
    faixa,tipo=meta(path)
    # documentos curtos ficam inteiros
    parts=[txt] if len(txt.split())<=500 else re.split(r'^(?=#{2,3} )',txt,flags=re.M)
    chunks=[]; sec='' 
    for part in parts:
        m=re.match(r'^(#{2,3}) (.*)',part)
        if m: sec=m.group(2).strip()
        body=part.strip()
        if not body: continue
        words=body.split()
        if len(words)<=max_words:
            chunks.append((sec,body))
        else:
            # split by paragraphs
            paras=body.split('\n\n')
            if max(len(p.split()) for p in paras)>max_words:
                paras=[p for q in paras for p in re.split(r'(?<=[.!?])\s+(?=[A-ZÀ-Ú•\-])',q)]
            cur=[]; n=0
            for p in paras:
                w=len(p.split())
                if n+w>max_words and cur:
                    chunks.append((sec,'\n\n'.join(cur))); cur=[];n=0
                cur.append(p); n+=w
            if cur: chunks.append((sec,'\n\n'.join(cur)))
    out=[]
    for i,(sec,body) in enumerate(chunks):
        if len(body.split())<25 and i>0: # merge tiny chunks into previous
            out[-1]['text']+='\n\n'+body; continue
        out.append({'doc':os.path.basename(path).replace('.md',''),'title':title,'section':sec,'faixa':faixa,'tipo':tipo,'fonte':src,'i':i,'text':body})
    return out

if __name__=='__main__':
    all_=[]
    for p in sorted(glob.glob('base/**/*.md',recursive=True)):
        all_+=chunk_doc(p)
    for c in all_: c['norm']=norm(f"{c['title']} {c['section']} {c['text']}")
    json.dump(all_,open('base_chunks.json','w'),ensure_ascii=False)
    import collections
    print(len(all_),'chunks;', 'max words', max(len(c['text'].split()) for c in all_))
    print(collections.Counter(c['tipo'] for c in all_))
