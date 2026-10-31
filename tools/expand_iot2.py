#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Раскрытие ссылок [[[вставить пункты с тегами ...]]] в файле iotraw (версия 2).

Логика источников:
  * ПЕРЕД-/ВОВРЕМЯ-/АВАР-/ОКОНЧ-*  — общерабочие формулировки из ИОТ-СПС-03;
  * ОБЩ-01..22 — общие требования раздела 1. Формулировки, привязанные к
    должности/виду работ (упоминание должности, «непосредственный руководитель
    работ», «на рабочем месте»), берутся из ИОТ-СПС-03; нейтральные — из
    ИОТ-СПС-01 (канонический источник по ссылке);
  * собственные заполненные блоки целевого документа (в т.ч. суффиксные теги
    вида ОБЩ-01-АГР) имеют приоритет;
  * ссылки на ИОТ-СПС-02 трактуются как руководящие формулировки (берутся
    оттуда напрямую);
  * сокращённые документы ИОТ-СПС-04/05 достраиваются до полной формы:
    каркас и общие блоки — из ИОТ-СПС-03, собственные (должностные) — из текста.

Удаляются служебные строки чата («Жду команду…», «**… сформированы полностью.**»,
«*(Пункты …)*», «*(Примечание …)*»), черновики реплик пользователя, разделители
«---» между документами; схлопываются идущие подряд пустые строки.

Запуск:  python3 tools/expand_iot2.py          — статистика
         python3 tools/expand_iot2.py --write  — запись iotraw_expanded
"""
import re
import sys

SRC = 'iotraw'
DST = 'iotraw_expanded'

TAG_RE = re.compile(r'^\[\{\[([^\]]+)\]\}\]')
NUM_RE = re.compile(r'\]\}]\s+(\d+\.\d+)')
MARKER_RE = re.compile(
    r'^\[\[\[вставить\s+пункты\s+с\s+те[га]ами\s+\[\{\[(.+?)\]\}\]\s*[-–—]\s*\[\{\[(.+?)\]\}\]'
    r'(?:\s+из\s+(ИОТ-[А-ЯЁ0-9-]+))?\s*\]\]\]\s*$'
)
CANON_FAM = ('ОБЩ', 'ПЕРЕД', 'ВОВРЕМЯ', 'АВАР', 'ОКОНЧ')

# маркеры привязки к исполнителю/рабочему месту в тексте пункта
ROLE_MARKERS = ('руководител', 'рабочем месте', 'рабочего места')


def split_docs(lines):
    docs, order, cur = {}, [], None
    for l in lines:
        if l.startswith('# ') and '—' in l:
            code = l[2:].split('—')[0].strip()
            docs.setdefault(code, [])
            order.append(code)
            cur = code
        elif cur is not None:
            docs[cur].append(l)
    return docs, order


def collect_blocks(doc_lines):
    """tag -> список строк блока (первое вхождение)."""
    blocks, cur_tag, buf = {}, None, []
    for l in doc_lines:
        m = TAG_RE.match(l)
        if m:
            if cur_tag is not None:
                blocks.setdefault(cur_tag, buf)
            cur_tag, buf = m.group(1), [l]
        elif cur_tag is not None:
            if l.strip() == '':
                blocks.setdefault(cur_tag, buf)
                cur_tag, buf = None, []
            else:
                buf.append(l)
    if cur_tag is not None:
        blocks.setdefault(cur_tag, buf)
    return blocks


def item_num(block):
    m = NUM_RE.search(block[0])
    return m.group(1) if m else None


def tag_range(a, b):
    fam = a.split('-')[0]
    assert b.startswith(fam + '-'), (a, b)
    try:
        ia, ib = int(a[len(fam) + 1:]), int(b[len(fam) + 1:])
    except ValueError:
        return [a]
    return [f'{fam}-{i:02d}' for i in range(ia, ib + 1)]


def strip_trailing_blanks(blk):
    b = list(blk)
    while b and b[-1].strip() == '':
        b.pop()
    return b


def is_role_specific(block):
    text = '\n'.join(block)
    return any(s in text for s in ROLE_MARKERS)


def main(write=False):
    raw = open(SRC, encoding='utf-8').read().split('\n')
    # ---- исправление опечатки «тешами» в маркерах (файл остаётся источником) ----
    fixed_tesh = 0
    fixed = []
    for l in raw:
        if l.strip().startswith('[[[вставить пункты с тешами'):
            l = l.replace('с тешами', 'с тегами')
            fixed_tesh += 1
        fixed.append(l)
    raw = fixed
    docs, order = split_docs(raw)

    blocks = {d: collect_blocks(ls) for d, ls in docs.items()}

    sps01, sps02, sps03 = blocks['ИОТ-СПС-01'], blocks['ИОТ-СПС-02'], blocks['ИОТ-СПС-03']

    # карта: номер пункта СПС-01 (ОБЩ-23..49) -> канонический тег СПС-03
    obsh_to_linear = {}
    linear_by_num = {}
    for t, b in sps03.items():
        if t.split('-')[0] in ('ПЕРЕД', 'ВОВРЕМЯ', 'АВАР', 'ОКОНЧ'):
            n = item_num(b)
            if n:
                linear_by_num[n] = t
    for t, b in sps01.items():
        if t.startswith('ОБЩ-') and 23 <= int(t.split('-')[1]) <= 49:
            n = item_num(b)
            if n and n in linear_by_num:
                obsh_to_linear[t] = linear_by_num[n]

    # карта «документ -> {номер пункта: блок}» для поиска специфичных редакций
    num_map = {}
    for d, bl in blocks.items():
        nm = {}
        for t, b in bl.items():
            n = item_num(b)
            if n:
                nm.setdefault(n, []).append(t)
        num_map[d] = nm

    def specific_block(d, tag):
        """собственная редакция блока в документе d (тот же номер пункта,
        но НЕ каноническое имя тега и не тег чужой группы)"""
        canon = sps01.get(tag) or sps03.get(tag) or sps02.get(tag)
        if canon is None or d not in num_map:
            return None
        n = item_num(canon)
        fam = tag.split('-')[0]
        cands = []
        for t in num_map[d].get(n, []):
            tfam = re.match(r'(?:.*?[-_])?(ОБЩ|ПЕРЕД|ВОВРЕМЯ|АВАР|ОКОНЧ)-\d+$', t)
            tfam = tfam.group(1) if tfam else t.split('-')[0]
            if tfam != fam:
                continue
            # исключаем канонические имена ОБЩ-NN/ПЕРЕД-NN/... — они и так есть в источниках
            if re.match(r'^(ОБЩ|ПЕРЕД|ВОВРЕМЯ|АВАР|ОКОНЧ)-\d+$', t):
                continue
            cands.append(t)
        if cands:
            return blocks[d][cands[0]]
        return None

    def exact_block(d, tag):
        bl = blocks.get(d, {})
        if tag in bl:
            return bl[tag]
        alt = [t for t in bl if t.endswith(f'-{tag}') or t.startswith(tag + '-')]
        return bl[alt[0]] if alt else None

    def resolve(tag, ref, cur_doc):
        fam = tag.split('-')[0]
        # 1) собственная редакция текущего документа (точное имя или та же нумерация)
        blk = exact_block(cur_doc, tag) or specific_block(cur_doc, tag)
        if blk is not None:
            return blk
        # 2) собственная редакция документа из ссылки (кроме СПС-01 как канона)
        if ref and ref != cur_doc:
            blk = exact_block(ref, tag) or specific_block(ref, tag)
            if blk is not None:
                return blk
        # 3) ОБЩ-01..22: при привязке к исполнителю — рабочая редакция из СПС-03
        if fam == 'ОБЩ' and tag in sps01 and int(tag[len('ОБЩ-'):]) <= 22:
            b01, b03 = sps01[tag], sps03.get(tag)
            if b03 is not None and is_role_specific(b03):
                return b03
            return b01
        # 4) линейные семейства — общерабочая редакция из СПС-03
        if tag in sps03:
            return sps03[tag]
        # 5) ОБЩ-23..49 из СПС-01 -> эквивалент из СПС-03 по номеру пункта
        if tag in obsh_to_linear:
            return sps03[obsh_to_linear[tag]]
        return None

    # ---- достройка сокращённых документов (СПС-04/05) ----
    expanded_docs = {}
    for code in ('ИОТ-СПС-04', 'ИОТ-СПС-05'):
        rebuilt = []
        for l in docs[code]:
            m = TAG_RE.match(l)
            if m:
                rebuilt.extend(strip_trailing_blanks(blocks[code][m.group(1)]))
            else:
                rebuilt.append(l)
        # заменяем содержательные строки: перенос строки после заголовков не нужен
        expanded_docs[code] = rebuilt

    out = []
    stats = {'markers': 0, 'missing': [], 'dropped': 0, 'tesh': fixed_tesh}
    cur_doc = None
    i, n = 0, len(raw)
    while i < n:
        l = raw[i]
        if l.startswith('# ') and '—' in l:
            cur_doc = l[2:].split('—')[0].strip()
        s = l.strip()
        # служебные строки чата и примечания
        if (s.startswith('Жду команду') or s.startswith('Продолжаю генерацию')
                or s.startswith('**') and 'сформирован' in s
                or s.startswith('*(')
                or s == 'продолжай, полностью одинаковые пункты с тегами можно не дублировать и давать на них ссылку'
                or s == 'Например'
                or s.startswith('Если вам потребуется скомпилировать')):
            stats['dropped'] += 1
            i += 1
            continue
        m = MARKER_RE.match(s) if s.startswith('[[[') else None
        if m:
            start_tag, end_tag, ref = m.group(1), m.group(2), m.group(3) or 'ИОТ-СПС-01'
            stats['markers'] += 1
            first = True
            for t in tag_range(start_tag, end_tag):
                blk = resolve(t, ref, cur_doc)
                if blk is None:
                    stats['missing'].append((cur_doc, t, ref))
                    continue
                if not first:
                    out.append('')
                out.extend(strip_trailing_blanks(blk))
                first = False
            i += 1
            continue
        out.append(l)
        i += 1

    # нормализация: удалить «---», схлопнуть пустые строки, подчистить хвост
    final, prev_blank = [], True
    for l in out:
        if l.strip() == '---':
            continue
        if l == '':
            if prev_blank:
                continue
            prev_blank = True
        else:
            prev_blank = False
        final.append(l)
    text = '\n'.join(final).rstrip() + '\n'

    print(f"маркеров раскрыто: {stats['markers']}")
    print(f"исправлено опечаток «тешами»: {stats['tesh']}")
    print(f"служебных строк удалено: {stats['dropped']}")
    print(f"ненайденных тегов: {len(stats['missing'])}")
    for x in stats['missing'][:30]:
        print('  MISSING:', x)
    print(f"остаточных маркеров: {text.count('[[[')}")
    print(f"строк на выходе: {text.count(chr(10))}")
    if write:
        open(DST, 'w', encoding='utf-8').write(text)
        print(f"записано: {DST}")


if __name__ == '__main__':
    main(write='--write' in sys.argv)
