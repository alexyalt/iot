#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сборка финальных DOCX для печати из iotraw_expanded.

Правила тегирования:
  * Теги вида [{[ПЕРЕД-01]}] в НАЧАЛЕ пунктов остаются как есть.
  * Все прочие артефакты разметки (##, **, *, ` и т.п.) преобразуются в
    нормальное оформление документа Word.

Выход: docx_final/ИОТ-*.docx + сводный файл docx_final/Все_инструкции.docx
"""
import os
import re
import sys

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, Cm

SRC = 'iotraw_expanded'
OUT = 'docx_final'

TAG_RE = re.compile(r'^\[\{\[([^\]]+)\]\}\]')
STRAY_TAG_RE = re.compile(r'\[\{\[[^\]]*\]\}\]')
MD_H_RE = re.compile(r'^(#{1,6})\s+(.*)$')
BOLD_RE = re.compile(r'\*\*(.+?)\*\*')
ITAL_RE = re.compile(r'(?<!\*)\*(?!\*)([^*]+)\*(?!\*)')
CODE_RE = re.compile(r'`([^`]+)`')

FONT = 'Times New Roman'


def clean_line(line):
    """Удалить служебные артефакты генерации, оставив текст."""
    s = line.rstrip()
    # курсивные примечания вида *(...)* уже удалены expand-скриптом; на всякий:
    return s


def add_runs(p, text):
    """Добавить текст с простым markdown-форматированием (**жирный**, *курсив*, `код`)."""
    # сначала защищаем жирный, разбивая текст
    pos = 0
    parts = []
    for m in BOLD_RE.finditer(text):
        if m.start() > pos:
            parts.append((text[pos:m.start()], False))
        parts.append((m.group(1), True))
        pos = m.end()
    if pos < len(text):
        parts.append((text[pos:], False))
    for chunk, bold in parts:
        # курсив внутри оставшихся частей
        cpos = 0
        subs = []
        for m in ITAL_RE.finditer(chunk):
            if m.start() > cpos:
                subs.append((chunk[cpos:m.start()], False))
            subs.append((m.group(1), True))
            cpos = m.end()
        if cpos < len(chunk):
            subs.append((chunk[cpos:], False))
        for schunk, italic in subs:
            schunk = CODE_RE.sub(r'\1', schunk)
            if not schunk:
                continue
            r = p.add_run(schunk)
            r.bold = bold
            r.italic = italic


def make_doc(title, body_lines, path):
    doc = Document()
    # базовый стиль
    st = doc.styles['Normal']
    st.font.name = FONT
    st.font.size = Pt(12)
    st.element.rPr.rFonts.set(
        '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia', FONT)
    pf = st.paragraph_format
    pf.space_after = Pt(4)
    pf.line_spacing = 1.15
    for section in doc.sections:
        section.left_margin = Cm(2.0)
        section.right_margin = Cm(1.0)
        section.top_margin = Cm(1.5)
        section.bottom_margin = Cm(1.5)

    first_h1 = True
    for raw in body_lines:
        line = clean_line(raw)
        if not line.strip():
            continue
        hm = MD_H_RE.match(line)
        if hm:
            level = len(hm.group(1))
            htext = hm.group(2).strip()
            htext = STRAY_TAG_RE.sub('', htext).strip()
            htext = BOLD_RE.sub(r'\1', htext)
            if level == 1:
                if not first_h1:
                    doc.add_page_break()
                first_h1 = False
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                r = p.add_run(htext)
                r.bold = True
                r.font.size = Pt(14)
                r.font.name = FONT
            elif level == 2:
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(10)
                r = p.add_run(htext)
                r.bold = True
                r.font.size = Pt(13)
                r.font.name = FONT
            else:
                p = doc.add_paragraph()
                r = p.add_run(htext)
                r.bold = True
                r.font.name = FONT
            continue
        if re.fullmatch(r'-{3,}', line.strip()):
            continue
        p = doc.add_paragraph()
        tm = TAG_RE.match(line)
        if tm:
            # оставляем тег в начале пункта как есть
            rest = line[tm.end():].lstrip()
            p.add_run('[{}] '.format(tm.group(1)))
            add_runs(p, rest)
        else:
            # теоретически тег мог встретиться не в начале — удаляем артефакт
            line = STRAY_TAG_RE.sub('', line)
            add_runs(p, line)
    doc.save(path)


def main():
    txt = open(SRC, encoding='utf-8').read().splitlines()
    docs, order, cur = {}, [], None
    buf = []
    for l in txt:
        if l.startswith('# ') and '—' in l:
            if cur is not None:
                docs[cur] = buf
            code = l[2:].split('—')[0].strip()
            order.append(code)
            cur = code
            buf = [l]
        elif cur is not None:
            buf.append(l)
    if cur is not None:
        docs[cur] = buf

    os.makedirs(OUT, exist_ok=True)
    print(f'Документов: {len(order)}')

    # отдельный docx на каждую инструкцию
    all_doc = None
    for code in order:
        lines = docs[code]
        title = lines[0][2:].strip()
        path = os.path.join(OUT, f'{code}.docx')
        make_doc(title, lines, path)
        print('OK', path)

    # сводный документ
    merged = []
    for code in order:
        merged.extend(docs[code])
    make_doc('Комплект инструкций по охране труда', merged,
             os.path.join(OUT, 'Все_инструкции.docx'))
    print('OK', os.path.join(OUT, 'Все_инструкции.docx'))


if __name__ == '__main__':
    main()
