#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Финализация iotraw_expanded перед сборкой DOCX для печати.

Правила тегирования (по требованию заказчика):
  * оставляем только теги в начале пунктов; все артефакты вида [{[...]},
    встречающиеся НЕ в начале строки, удаляются;
  * удалённые служебные строки («новый пункт», битые заголовки «##  itle>...»)
    чистятся;
  * пункты с дублирующими каноническими тегами внутри одной секции документа
    получают уникальные суффиксные имена (ТЕГ-Nn-ДОК), где ДОК — код документа
    без префикса «ИОТ-» (например ОБЩ-10-СПС_04);
  * после всех правок нумерация пунктов перестраивается заново по порядку
    следования в каждой секции: X.1, X.2, ... (включая подпункты X.Y.Z и
    перенумерацию ссылок вида «согласно пункту X.Y» / «пунктов X.Y–X.Z»).

Запуск:  python3 tools/finalize_iot.py          — статистика (без записи)
         python3 tools/finalize_iot.py --write  — запись iotraw_final
"""
import re
import sys
from collections import defaultdict

SRC = 'iotraw_expanded'
DST = 'iotraw_final'

TAG_RE = re.compile(r'^\[\{\[([^\]]+)\]\}\]')
STRAY_TAG_RE = re.compile(r'\[\{\[[^\]]*\]\}\]')
NUM_RE = re.compile(r'^\[\{\[([^\]]+)\]\}\]\s*(\d+(?:\.\d+)*)')
SEC_HEAD_RE = re.compile(r'^##\s+(\d+)\.\s')
DOC_HEAD_RE = re.compile(r'^#\s+(ИОТ-[А-ЯЁ0-9-]+)\s+—')
CANON_FAM_RE = re.compile(r'(ОБЩ|ПЕРЕД|ВОВРЕМЯ|АВАР|ОКОНЧ)-(\d+)$')

JUNK_EXACT = {'новый пункт'}


def doc_suffix(doc_code):
    """ИОТ-СПС-04 -> СПС_04, ИОТ-ВИД-13 -> ВИД_13."""
    return doc_code.replace('ИОТ-', '').replace('-', '_')


def main(write=False):
    lines = open(SRC, encoding='utf-8').read().split('\n')

    # ---------- проход 1: очистка мусора и внутрестрочных артефактов ----------
    out = []
    n_stray = n_junk = 0
    for l in lines:
        if l.strip() in JUNK_EXACT:
            n_junk += 1
            continue
        if l.startswith('## ') and 'itle>' in l:
            l = '## ' + l.split('itle>')[-1].strip()
            n_junk += 1
        if TAG_RE.match(l):
            # тег в начале сохраняем; если в тексте есть ещё [{...}] — убираем
            m_first = TAG_RE.match(l)
            rest = l[m_first.end():]
            cleaned_rest, cnt = STRAY_TAG_RE.subn('', rest)
            n_stray += cnt
            l = m_first.group(0) + cleaned_rest
        else:
            new_l, cnt = STRAY_TAG_RE.subn('', l)
            if cnt:
                n_stray += cnt
                l = new_l
        out.append(l)

    # ---------- проход 2: уникализация дублирующихся тегов в секции ----------
    cur_doc = None
    cur_sec = None
    seen = defaultdict(int)      # (doc, sec, tag) -> count
    n_renamed = 0
    for idx, l in enumerate(out):
        m = DOC_HEAD_RE.match(l)
        if m:
            cur_doc = m.group(1)
            cur_sec = None
            continue
        ms = SEC_HEAD_RE.match(l)
        if ms:
            cur_sec = ms.group(1)
            continue
        mt = TAG_RE.match(l)
        if not mt or cur_doc is None:
            continue
        tag = mt.group(1)
        key = (cur_doc, cur_sec, tag)
        seen[key] += 1
        if seen[key] > 1:
            base = tag.split('-')[0] if '-' in tag else tag
            num_part = tag[len(base) + 1:] if '-' in tag else ''
            canon = CANON_FAM_RE.search(tag)
            if canon:
                fam, num = canon.group(1), canon.group(2)
            else:
                fam, num = base, num_part
            newtag = f'{fam}-{int(num):02d}-{doc_suffix(cur_doc)}'
            out[idx] = '[{[' + newtag + ']}]' + l[mt.end():]
            seen[(cur_doc, cur_sec, newtag)] = max(seen[(cur_doc, cur_sec, newtag)], 1)
            n_renamed += 1

    # ---------- проход 3: сплошная перенумерация в секциях ----------
    cur_sec = None
    counters = {}   # sec -> last item number
    mapping = {}    # (doc, sec, oldnum) -> newnum
    cur_doc = None
    blocks_by_docsec = defaultdict(list)  # (doc,sec) -> [(idx_block_start, oldnum)]
    for idx, l in enumerate(out):
        m = DOC_HEAD_RE.match(l)
        if m:
            cur_doc = m.group(1)
            cur_sec = None
            counters = {}
            continue
        ms = SEC_HEAD_RE.match(l)
        if ms:
            cur_sec = ms.group(1)
            counters[cur_sec] = 0
            continue
        mn = NUM_RE.match(l)
        if mn and cur_sec is not None:
            oldnum = mn.group(2)
            top = oldnum.split('.')[0]
            if top != cur_sec:
                # номер не соответствует разделу — доверяем разделу
                pass
            counters[cur_sec] = counters.get(cur_sec, 0) + 1
            newnum = f'{cur_sec}.{counters[cur_sec]}'
            mapping[(cur_doc, cur_sec, oldnum)] = newnum
            blocks_by_docsec[(cur_doc, cur_sec)].append((idx, oldnum, newnum))

    # перезапись номеров в строках-заголовках блоков
    n_renum = 0
    for (d, s), lst in blocks_by_docsec.items():
        for idx, oldnum, newnum in lst:
            l = out[idx]
            if oldnum != newnum:
                l = NUM_RE.sub('[{[' + TAG_RE.match(l).group(1) + ']}] ' + newnum, l, count=1)
                out[idx] = l
                n_renum += 1

    # ---------- проход 4: перенумерация ссылок «пункт(а/ов) X.Y» ----------
    LINK_RE = re.compile(r'(?<![\d.])(\d)\.(\d+)(?!\.\d)(?![\d])')
    cur_doc = None
    cur_sec = None
    n_links = 0
    for idx, l in enumerate(out):
        m = DOC_HEAD_RE.match(l)
        if m:
            cur_doc = m.group(1)
            cur_sec = None
            continue
        ms = SEC_HEAD_RE.match(l)
        if ms:
            cur_sec = ms.group(1)
            continue
        if cur_doc is None or 'пункт' not in l:
            continue
        def repl(mm):
            nonlocal n_links
            sec, num = mm.group(1), mm.group(2)
            new = mapping.get((cur_doc, sec, f'{sec}.{num}'))
            if new and new != f'{sec}.{num}':
                n_links += 1
                return new
            return mm.group(0)
        out[idx] = LINK_RE.sub(repl, l)

    text = '\n'.join(out).rstrip() + '\n'

    print(f'удалено служебных строк/артефактов заголовков: {n_junk}')
    print(f'удалено тегов вне начала строк: {n_stray}')
    print(f'переименовано дублей тегов: {n_renamed}')
    print(f'перенумеровано пунктов: {n_renum}')
    print(f'исправлено ссылок на пункты: {n_links}')
    n_open = text.count("[[[")
    n_close = text.count("]]]")
    print(f"остаточных артефактов открывающих: {n_open}, закрывающих: {n_close}")
    print(f'строк на выходе: {len(out)}')

    if write:
        open(DST, 'w', encoding='utf-8').write(text)
        print(f'записано: {DST}')


if __name__ == '__main__':
    main(write='--write' in sys.argv)
