#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Раскрытие ссылок [[[вставить пункты с тегами ...]]] в файле iotraw.

Источники канонических блоков (полные тексты помеченных пунктов):
  * ОБЩ-01..22            — ИОТ-СПС-01, раздел 1 (уникальные формулировки по должности)
  * ОБЩ-23..49            — ИОТ-СПС-01, разделы 2–5 (пункты 2.1–2.4, 2.6–2.7,
                            3.1–3.7, 3.9–3.10, 4.1–4.7, 5.2–5.6)
  * ПЕРЕД-/ВОВРЕМЯ-/АВАР-/ОКОНЧ- — ИОТ-СПС-03 (общерабочие формулировки для
                            линейных должностей и работ по видам; текст совпадает
                            с ИОТ-СПС-06/07)

Правила подстановки:
  * нумерация пунктов сохраняется как в источнике (каноническая);
  * при указании конкретной инструкции («из ИОТ-СПС-XX», кроме ИОТ-СПС-01),
    если в ней есть собственное заполнение того же тега — берётся оно
    (напр. ОБЩ-01..04 с суффиксом должности у агронома);
  * в ссылках на ИОТ-СПС-01 теги ОБЩ-23..49 трактуются какравновеликие
    ПЕРЕД-*/ВОВРЕМЯ-*/АВАР-*/ОКОНЧ-* (подставляются из ИОТ-СПС-03).

Удалению подлежат также служебные строки чата ассистента («Жду команду…»,
«Продолжаю генерацию…», «**… сформирован(ы) полностью.**»), черновики реплик
пользователя и курсивные примечания вида «*(Пункты … используют теги …)*».

Запуск:  python3 tools/expand_iot.py          — проверка (статистика)
         python3 tools/expand_iot.py --write  — запись iotraw_expanded
"""
import re
import sys

SRC = 'iotraw'
DST = 'iotraw_expanded'

TAG_RE = re.compile(r'^\[\{\[([^\]]+)\]\}\]')
MARKER_RE = re.compile(
    r'^\[\[\[вставить\s+пункты\s+с\s+те[га]ами\s+\[\{\[(.+?)\]\}\]\s*[-–—]\s*\[\{\[(.+?)\]\}\](?:\s+из\s+(ИОТ-[А-ЯЁ0-9-]+))?\s*\]\]\]\s*$'
)
NUM_RE = re.compile(r'^(\d+\.\d+)\.')

SECTION_OF_PREFIX = {'ОБЩ': None, 'ПЕРЕД': '2', 'ВОВРЕМЯ': '3', 'АВАР': '4', 'ОКОНЧ': '5'}


def split_blocks(lines):
    """Разбить файл на документы {code: lines} и собрать блоки тегов."""
    docs = {}
    order = []
    cur = None
    for l in lines:
        if l.startswith('# ') and '—' in l:
            code = l[2:].split('—')[0].strip()
            cur = code
            docs.setdefault(code, [])
            order.append(code)
        elif cur is not None:
            docs[cur].append(l)
    return docs, order


def collect_tag_blocks(doc_lines):
    """tag -> список строк блока (начиная с линии тега, до пустой строки или нового тега)."""
    blocks = {}
    cur_tag = None
    buf = []
    for l in doc_lines:
        m = TAG_RE.match(l)
        if m:
            if cur_tag:
                blocks.setdefault(cur_tag, []).append(buf)
            cur_tag = m.group(1)
            buf = [l]
        elif cur_tag and l.strip() == '':
            blocks.setdefault(cur_tag, []).append(buf)
            cur_tag = None
            buf = []
        elif cur_tag:
            buf.append(l)
        elif buf and cur_tag is None:
            pass
    if cur_tag:
        blocks.setdefault(cur_tag, []).append(buf)
    # взять первый (канонический) блок каждого тега
    return {t: b[0] for t, b in blocks.items()}


def normalize_doc(doc_lines):
    """Развернуть ссылки внутри одного документа (для ИОТ-СПС-04/05), чтобы
    получить его полное каноническое содержимое."""
    out = []
    i = 0
    n = len(doc_lines)
    while i < n:
        l = doc_lines[i]
        m = MARKER_RE.match(l.strip()) if l.strip().startswith('[[[') else None
        if m and not m.group(3):
            # ссылка без «из ...» — источник неизвестен, оставляем как есть
            out.append(l); i += 1; continue
        if m:
            seq = tag_range(m.group(1), m.group(2))
            for t in seq:
                blk = find_block_in_doc(doc_lines, t)
                if blk:
                    out.extend(strip_trailing_blanks(blk))
                    out.append('')
            i += 1
            continue
        out.append(l)
        i += 1
    return out


def find_block_in_doc(doc_lines, tag):
    blocks = collect_tag_blocks(doc_lines)
    if tag in blocks:
        return blocks[tag]
    alt = [t for t in blocks if t.startswith(tag + '-')]
    return blocks[alt[0]] if alt else None


def main(write=False):
    lines = open(SRC, encoding='utf-8').read().split('\n')
    docs, order = split_blocks(lines)

    # достраивание сокращённых документов (ИОТ-СПС-04/05) до полной формы:
    # общие блоки берутся из ИОТ-СПС-03, собственные (должностные) — из документа
    LINEAR_DOCS = ('ИОТ-СПС-04', 'ИОТ-СПС-05')
    sps03_src = docs.get('ИОТ-СПС-03', [])
    for code in LINEAR_DOCS:
        if code not in docs:
            continue
        own = collect_tag_blocks(docs[code])
        rebuilt = []
        for l in sps03_src:
            m = TAG_RE.match(l)
            if m and m.group(1) in own:
                rebuilt.extend(strip_trailing_blanks(own[m.group(1)]))
            else:
                rebuilt.append(l)
        # вставляем собственные блоки с тегами ОБЩ-10/ОБЩ-11 (упомянуты в тексте
        # самого документа) на место канонических; остальные общие — из СПС-03
        docs[code] = rebuilt

    # предварительная нормализация документов с внутренними ссылками
    for code in list(docs):
        if any(l.strip().startswith('[[[') for l in docs[code]):
            docs[code] = normalize_doc(docs[code])

    sps01 = collect_tag_blocks(docs['ИОТ-СПС-01'])
    sps03 = collect_tag_blocks(docs['ИОТ-СПС-03'])
    sps02 = collect_tag_blocks(docs['ИОТ-СПС-02'])  # ОБЩ-23..49 (руководящий состав)

    # карта соответствия ОБЩ-23..49 -> ПЕРЕД/ВОВРЕМЯ/АВАР/ОКОНЧ (по номеру пункта)
    num_to_alias = {}
    for t, b in sps03.items():
        m = NUM_RE.match(b[0][len('[{[%s]}]' % t):].strip())
        if m:
            num_to_alias[m.group(1)] = t

    def get_block(tag, ref_doc=None):
        """Вернуть строки блока для тега; ref_doc — инструкция из ссылки (или None)."""
        # 1) собственное заполнение в целевой инструкции
        if ref_doc and ref_doc != 'ИОТ-СПС-01' and ref_doc in docs:
            own = collect_tag_blocks(docs[ref_doc])
            # точное совпадение тега
            if tag in own:
                return own[tag], True
            # суффиксные варианты: ОБЩ-01-АГР вместо ОБЩ-01 (только для ОБЩ-01..04/10/11)
            alt = [t for t in own if t.startswith(tag + '-')]
            if alt:
                return own[alt[0]], True
        # 2) канонические источники
        if tag in sps01:
            return sps01[tag], False
        if tag in sps03:
            return sps03[tag], False
        # 3) алиасы ОБЩ-23..49 <-> ПЕРЕД/ВОВРЕМЯ/АВАР/ОКОНЧ
        m = NUM_RE.match(sps01.get(tag, ['x'])[0][len('[{[%s]}]' % tag):].strip()) if tag in sps01 else None
        return None, False

    def resolve(tag, ref_doc):
        # прямой поиск
        cand_docs = ([ref_doc] if ref_doc else []) 
        for d in cand_docs:
            if d and d != 'ИОТ-СПС-01' and d in docs:
                own = collect_tag_blocks(docs[d])
                if tag in own:
                    return own[tag]
                alt = [t for t in own if t.startswith(tag + '-')]
                if alt:
                    return own[alt[0]]
        if tag in sps01:
            return sps01[tag]
        if tag in sps03:
            return sps03[tag]
        # ОБЩ-23..49 из СПС-01 == ПЕРЕД/ВОВРЕМЯ/АВАР/ОКОНЧ из СПС-03 (по номеру пункта)
        if tag in sps01:
            pass
        return None

    # построим алиас-таблицу: номер пункта -> тег в СПС-03
    sps01_num = {}
    for t, b in sps01.items():
        mm = NUM_RE.match(b[0].split(']}]', 1)[1].strip())
        if mm:
            sps01_num[t] = mm.group(1)

    def build_default_source(doc_code):
        """Документы-источники по умолчанию: для руководящего состава —
        ИОТ-СПС-02 (полный документ с ОБЩ-01..49), для остальных —
        ИОТ-СПС-03 (общерабочие ПЕРЕД/ВОВРЕМЯ/АВАР/ОКОНЧ) + ИОТ-СПС-01."""
        mgr = doc_code in ('ИОТ-СПС-01', 'ИОТ-СПС-02', 'ИОТ-СПС-04', 'ИОТ-СПС-05')
        return [sps02] if mgr else [sps03, sps01]

    def resolve2(tag, ref_doc, cur_doc=None):
        default_sources = build_default_source(cur_doc or '')
        # 1) собственное заполнение в целевой инструкции
        for d in ([ref_doc] if ref_doc else []):
            if d and d not in ('ИОТ-СПС-01', 'ИОТ-СПС-02') and d in docs:
                own = collect_tag_blocks(docs[d])
                if tag in own:
                    return own[tag]
                alt = [t for t in own if t.startswith(tag + '-')]
                if alt:
                    return own[alt[0]]
        # 2) суффиксные варианты в текущем документе (ОБЩ-01-АГР и т.п.)
        if cur_doc and cur_doc in docs:
            own = collect_tag_blocks(docs[cur_doc])
            alt = [t for t in own if t.startswith(tag + '-')]
            if alt:
                return own[alt[0]]
        # 3) источники по умолчанию (порядок важен!)
        for src in default_sources:
            if tag in src:
                return src[tag]
        # 4) алиас ОБЩ-23..49 <-> ПЕРЕД/ВОВРЕМЯ/АВАР/ОКОНЧ (для не-руководящих)
        if tag in sps01:
            num = sps01_num.get(tag)
            alias = num_to_alias.get(num) if num else None
            if alias and alias in sps03:
                return sps03[alias]
            return sps01[tag]
        if tag in sps03:
            return sps03[tag]
        return None

    out = []
    stats = {'markers': 0, 'missing': [], 'dropped': 0}
    cur_doc = None
    skip_meta_until_sep = False
    i = 0
    n = len(lines)
    while i < n:
        l = lines[i]
        if l.startswith('# ') and '—' in l:
            cur_doc = l[2:].split('—')[0].strip()
            skip_meta_until_sep = False
        # служебные строки
        if (l.startswith('Жду команду') or l.startswith('Продолжаю генерацию')
                or l.startswith('**') and ('сформирован' in l)
                or l.startswith('*(') or l.startswith('*(Пункты') or l.startswith('*(Примечание')
                or l.strip() == 'продолжай, полностью одинаковые пункты с тегами можно не дублировать и давать на них ссылку'
                or l.strip() == 'Например'):
            stats['dropped'] += 1
            i += 1
            continue
        if l.startswith('[[[вставить пункты с тешами'):  # опечатка-черновик из реплики пользователя
            stats['dropped'] += 1
            i += 1
            continue
        m = MARKER_RE.match(l.strip())
        if m:
            start_tag, end_tag, ref = m.group(1), m.group(2), m.group(3) or 'ИОТ-СПС-01'
            stats['markers'] += 1
            seq = tag_range(start_tag, end_tag)
            inserted_any = False
            for t in seq:
                blk = resolve2(t, ref)
                if blk is None:
                    stats['missing'].append((cur_doc, t))
                    continue
                if inserted_any:
                    out.append('')
                out.extend(strip_trailing_blanks(blk))
                inserted_any = True
            i += 1
            continue
        out.append(l)
        i += 1

    # нормализация: убрать строки «---» между документами и склеить лишние пустые строки
    final = []
    prev_blank = False
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
    print(f"markers раскрыто: {stats['markers']}")
    print(f"служебных строк удалено: {stats['dropped']}")
    print(f"ненайденных тегов: {len(stats['missing'])}")
    for x in stats['missing'][:20]:
        print('  MISSING:', x)
    left = re.findall(r'\[\[\[', text)
    print(f"остаточных маркеров: {len(left)}")
    if write:
        with open(DST, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f"записано: {DST} ({text.count(chr(10))} строк)")


def strip_trailing_blanks(blk):
    b = list(blk)
    while b and b[-1].strip() == '':
        b.pop()
    return b


def tag_range(a, b):
    """Перечислить теги от a до b включительно в пределах одного семейства."""
    fam = a.split('-')[0]
    assert b.startswith(fam), (a, b)
    rest_a = a[len(fam) + 1:]
    rest_b = b[len(fam) + 1:]
    try:
        ia, ib = int(rest_a), int(rest_b)
    except ValueError:
        return [a]
    return [f'{fam}-{i:02d}' for i in range(ia, ib + 1)]


if __name__ == '__main__':
    main(write='--write' in sys.argv)
