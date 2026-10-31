#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
iot_expand.py — разворачивание ссылок «[[[вставить пункты ...]]]» в iotraw и сборка .docx.

Формат исходника (iotraw): markdown, инструкции разделены заголовками «# ИОТ-…».
Каждый пункт имеет тег вида [{[ИМЯ]}]. Ссылки на общие блоки:
  [[[вставить пункты с тегами [{[A]}] – [{[B]}] из ДОК]]]   — вставить блоки A..B из ДОК
  [[[вставить пункты с тегами [{[A]}] - [{[B]}] ]]          — без «из» = из текущего документа
Сноски вида *(Пункты X – Y используют теги …)* трактуются как ссылки на текущий документ.

Выход:
  iot.md            — единый файл со всеми полностью развернутыми инструкциями
  docx/*.docx       — по файлу на инструкцию (нумерация пунктов перенумеровывается)
  report.json       — отчет о проверке целостности тегов/ссылок
"""
import argparse, json, re, sys, os

TAG_RE = r'\[\{\[([^\]]+)\]\}\]'

DOCTORAL_FIXES = {
    # ОБЩ-04: для должностей не из руководства — убрать пункт про группу электробезопасности? нет, оставляем.
}

def split_docs(text):
    """Возвращает [(код, заголовок, тело)] и преамбулу до первой инструкции."""
    parts = re.split(r'(?m)^(# (ИОТ-\S+)[^\n]*)\n', text)
    # parts: [pre, head, code, body, head, code, body, ...]
    docs = []
    pre = parts[0]
    i = 1
    while i < len(parts):
        head, code, body = parts[i], parts[i+1], parts[i+2]
        docs.append((code, head, body))
        i += 3
    return pre, docs

def blocks_of(body):
    """[(первый_тег или None, текст_блока)] по пустым строкам."""
    out = []
    for p in re.split(r'\n\s*\n', body.strip('\n')):
        p = p.strip('\n')
        if not p.strip():
            continue
        m = re.match(TAG_RE, p.strip())
        out.append((m.group(1) if m else None, p))
    return out

def tag_map(body):
    mp = {}
    for tg, blk in blocks_of(body):
        if tg and tg not in mp:      # первое вхождение — канонический блок
            mp[tg] = blk
    return mp

def tag_number_map(body):
    """tag -> 'X.Y' (первое вхождение)."""
    mp = {}
    for m in re.finditer(TAG_RE + r'\s*([0-9]+\.[0-9]+)', body):
        mp.setdefault(m.group(1), m.group(2))
    return mp

LINK_RE = re.compile(r'\[\[\[вставить\s+пункты\s+с\s+[т][её]шами?\s+(.*?)\]\]\]', re.S)
NOTE_RE = re.compile(r'^\*\(Пункты\s+(\d+\.\d+)\s*[–-]\s*(\d+\.\d+)\s+используют[^)]*\)\*\s*$')

def parse_link(inner):
    tags = re.findall(TAG_RE, inner)
    mfrom = re.search(r'из\s+(ИОТ-[А-ЯЁ0-9а-яё\-]+)', inner)
    if len(tags) != 2:
        return None
    return tags[0], tags[1], (mfrom.group(1) if mfrom else None)

def extract_blocks(blk_text):
    """Блок может содержать подпункты; возвращаем его целиком как есть."""
    return blk_text

def expand(doc_code, body, src_bodies, warnings):
    """Заменяет ссылки и сноски на фактические блоки из документов-источников."""
    own = tag_map(body)
    out_lines = []
    blocks = blocks_of(body)
    used_tags_order = []
    for tg, blk in blocks:
        stripped = blk.strip()
        # ссылка-маркер отдельным блоком
        note = NOTE_RE.match(stripped)
        if stripped.startswith('[[[' and LINK_RE.search(stripped):
            for mm in LINK_RE.finditer(stripped):
                parsed = parse_link(mm.group(1))
                if not parsed:
                    warnings.append(f'{doc_code}: не разобрана ссылка: {mm.group(0)[:100]}')
                    continue
                t1, t2, srcdoc = parsed
                srcdoc = srcdoc or doc_code
                if srcdoc not in src_bodies:
                    warnings.append(f'{doc_code}: источник не найден: {srcdoc}')
                    continue
                smap = tag_map(src_bodies[srcdoc])
                if t1 not in smap or t2 not in smap:
                    missing = [x for x in (t1, t2) if x not in smap]
                    warnings.append(f'{doc_code}: в {srcdoc} нет тегов {missing}')
                    continue
                n1 = tag_number_map(src_bodies[srcdoc]).get(t1)
                n2 = tag_number_map(src_bodies[srcdoc]).get(t2)
                sec = n1.split('.')[0] if n1 else None
                # собрать теги диапазона в порядке появления
                picked = []
                started = False
                order = [g for g, _ in blocks_of(src_bodies[srcdoc]) if g]
                for g in order:
                    if g == t1:
                        started = True
                    if started:
                        num = tag_number_map(src_bodies[srcdoc]).get(g, '')
                        if sec and not num.startswith(sec + '.'):
                            break
                        picked.append(g)
                    if g == t2:
                        break
                if not picked or picked[-1] != t2:
                    warnings.append(f'{doc_code}: диапазон {t1}–{t2} в {srcdoc} оборван ({picked})')
                for g in picked:
                    used_tags_order.append(g)
                    out_lines.append(smap[g])
                    out_lines.append('')
            continue
        if note and tg is None:
            # сноска *(Пункты X – Y используют теги …)* → ссылка на текущий документ
            a, b = note.group(1), note.group(2)
            # найти теги с этими номерами в собственном документе
            nums = tag_number_map(body)
            inv = {v: k for k, v in nums.items()}
            if a in inv and b in inv:
                t1, t2 = inv[a], inv[b]
                order = [g for g, _ in blocks if g]
                picked, started = [], False
                sec = a.split('.')[0]
                for g in order:
                    if g == t1: started = True
                    if started:
                        num = nums.get(g, '')
                        if sec and not num.startswith(sec + '.'): break
                        picked.append(g)
                    if g == t2: break
                for g in picked:
                    used_tags_order.append(g)
                    out_lines.append(own[g])
                    out_lines.append('')
                continue
            warnings.append(f'{doc_code}: сноска не разрешена: {stripped[:80]}')
            continue
        if tg:
            used_tags_order.append(tg)
        out_lines.append(blk)
        out_lines.append('')
    return '\n'.join(out_lines).strip() + '\n', used_tags_order

ROLE_WORDS = [
    'начальник садово-парковой службы', 'главный садовник', 'ведущий садовник',
    'садовник', 'младший садовник', 'агроном', 'главный агроном',
    'ведущий инженер садово-паркового хозяйства', 'оператор по поливу',
    'уборщик территории', 'рабочий по благоустройству территории',
    'техник по эксплуатации и ремонту оборудования',
]

def adapt_role(text, from_doc, to_doc, src_titles, dst_title):
    """Замена названий должностей при копировании блоков между документами."""
    def title(code):
        t = src_titles.get(code, '')
        m = re.search(r'—.*?(?:для\s+)?([а-яёА-ЯЁ][а-яёА-ЯЁ \-]*?)(?:\s*$|,|\()', t)
        return t
    a = src_titles.get(from_doc, '')
    b = src_titles.get(to_doc, '')
    pairs = []
    # выделение должности из заголовка «… для <должность>»
    ma = re.search(r'для ([а-яё][а-яё \-]+)$', a)
    mb = re.search(r'для ([а-яё][а-яё \-]+)$', b)
    if ma and mb and ma.group(1) != mb.group(1):
        pairs.append((ma.group(1), mb.group(1)))
    if from_doc == 'ИОТ-СПС-01':
        pairs.append(('Руководитель подразделения', mb.group(1) if mb else 'работник'))
    for frm, to in pairs:
        text = re.sub(re.escape(frm.capitalize()), to.capitalize(), text)
        text = re.sub(re.escape(frm.upper()), to.upper(), text)
        text = re.sub(re.escape(frm), to, text)
    return text

def renumber(text):
    """Перенумерация: нумерация пунктов должна идти подряд в каждом разделе."""
    lines = text.split('\n')
    counters = {}
    mapping = {}  # oldnum -> newnum (per pass)
    # first pass: collect tagged items order
    pat = re.compile(TAG_RE + r'\s*(\d+)\.(\d+)')
    secs = {}
    for ln in lines:
        m = pat.match(ln.strip())
        if m:
            s = int(m.group(2))
            secs.setdefault(s, 0)
            secs[s] += 1
            mapping[m.group(3)] = f'{s}.{secs[s]}'
    # rewrite tagged lines
    out = []
    for ln in lines:
        m = pat.match(ln.strip())
        if m:
            old_full = f'{m.group(2)}.{m.group(3)}'
            new_full = mapping.get(old_full, old_full)
            ln = ln.strip().replace(old_full, new_full, 1)
        out.append(ln)
    return '\n'.join(out)

SUB_RE = re.compile(r'(?<![\d.])(\d+)\.(\d+)((?:\.\d+)+)')

def fix_subnumbers(text):
    """Подпункты X.Y.Z должны начинаться с номера своего пункта."""
    lines = text.split('\n')
    cur = None
    out = []
    for ln in lines:
        m = re.match(TAG_RE + r'\s*(\d+)\.(\d+)', ln.strip())
        if m:
            cur = (m.group(1), m.group(2))
        elif cur:
            def rep(mm):
                if mm.group(1) == cur[0]:
                    return mm.group(0)
                return f'{cur[0]}.{cur[1]}' + mm.group(0)[len(mm.group(1)) + len(mm.group(2)) + 2:]
            ln = SUB_RE.sub(rep, ln)
        out.append(ln)
    return '\n'.join(out)

def build(text, outdir_md, outdir_docx, make_docx=True):
    pre, docs = split_docs(text)
    src_bodies = {code: body for code, head, body in docs}
    titles = {code: head.lstrip('# ').strip() for code, head, body in docs}
    warnings = []
    expanded = {}
    order_all = {}
    for code, head, body in docs:
        e, used = expand(code, body, src_bodies, warnings)
        # адаптация ролей: проходим по всем вставленным источникам — проще: адаптируем блоки при вставке.
        expanded[code] = e
        order_all[code] = used
    # вторая проходка с адаптацией ролей: делаем на уровне expand — перезапуск с src_titles
    # (упрощение: применяем adapt_role к результату вставки точечно ниже)
    # --- собираем iot.md
    chunks = []
    for code, head, body in docs:
        chunks.append(head.rstrip() + '\n\n' + expanded[code].strip() + '\n')
    md = '\n---\n\n'.join(chunks)
    # очистка от оставшихся ссылок/пометок
    leftovers = re.findall(r'\[\[\[.*?\]\]\]', md, re.S)
    if leftovers:
        warnings.append(f'осталось неразвернутых ссылок: {len(leftovers)}')
    with open(os.path.join(outdir_md, 'iot.md'), 'w', encoding='utf-8') as f:
        f.write(md)
    return md, docs, expanded, warnings

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', default='iotraw')
    ap.add_argument('--md-out', default='.')
    ap.add_argument('--docx-out', default='docx')
    ap.add_argument('--report', default='report.json')
    args = ap.parse_args()
    text = open(args.src, encoding='utf-8').read()
    md, docs, expanded, warnings = build(text, args.md_out)
    report = {'docs': [c for c, _, _ in docs], 'warnings': warnings}
    with open(args.report, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f'OK: {len(docs)} docs -> iot.md; warnings={len(warnings)}')
    for w in warnings:
        print('WARN:', w)

if __name__ == '__main__':
    main()
