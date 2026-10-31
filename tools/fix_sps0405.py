#!/usr/bin/env python3
"""Восстановление разделов 2-5 в ИОТ-СПС-04/05 из эталона ИОТ-СПС-03 + специфика."""
import re

lines = open('iotraw_final', encoding='utf-8').read().split('\n')


def doc_bounds(code, ls):
    s = None
    for i, l in enumerate(ls):
        if l.startswith('# ' + code + ' —'):
            s = i
            break
    e = len(ls)
    for j in range(s + 1, len(ls)):
        if re.match(r'^#\s+ИОТ-', ls[j]):
            e = j
            break
    return s, e


TAGL = re.compile(r'^\[\{\[([^\]]+)\]\}\]')
NUMRE = re.compile(r'^(\[\{\[[^\]]+\]\}\]\s*)(\d+\.\d+)(\.?)(.*)')
SEC = re.compile(r'^##\s+(\d+)\.\s*(.*)')


def split_sections(blk):
    heads = []
    for i, l in enumerate(blk):
        m = SEC.match(l)
        if m:
            heads.append((i, m.group(1), m.group(2)))
    segs = []
    for k, (i, num, title) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(blk)
        segs.append((num, title, i, end))
    pre = heads[0][0] if heads else len(blk)
    return segs, blk[:pre]


def normalize_items(seg_lines, sec_num, renames):
    out = []
    cnt = 0
    last_item = None
    for l in seg_lines:
        if l.startswith('## '):
            continue
        mn = NUMRE.match(l)
        if mn:
            tag = mn.group(1)
            body = mn.group(4)
            cnt += 1
            new = f'{sec_num}.{cnt}'
            last_item = new
            body = re.sub(r'^\s*\d+\.\d+\.\s*', '', body)
            for a, b in renames:
                body = body.replace(a, b)
            out.append(f'{tag}{new}. {body.lstrip()}')
        elif re.match(r'^\d+\.\d+\.\d+', l):
            m2 = re.match(r'^(\d+\.\d+)\.(\d+\.?.*)', l)
            parent = m2.group(1)
            newparent = last_item or parent
            ll = l
            for a, b in renames:
                ll = ll.replace(a, b)
            out.append(newparent + '.' + m2.group(2) if parent != newparent else ll)
        else:
            ll = l
            for a, b in renames:
                ll = ll.replace(a, b)
            out.append(ll)
    return out


s3, e3 = doc_bounds('ИОТ-СПС-03', lines)
ref = lines[s3:e3]
ref_segs, _ = split_sections(ref)

for code, pos in [('ИОТ-СПС-04', 'садовник'), ('ИОТ-СПС-05', 'младший садовник')]:
    s, e = doc_bounds(code, lines)
    blk = lines[s:e]
    segs, pre = split_sections(blk)
    tgt_by = {}
    for num, title, st, en in segs:
        tgt_by[num] = (st, en)
    newblk = list(pre)
    for num, title, rstart, rend in ref_segs:
        newblk.append(f'## {num}. {title}')
        newblk.append('')
        base_body = ref[rstart + 1:rend]
        renames = [] if num == '1' else [
            ('ведущего садовника', pos),
            ('Ведущий садовник', pos.capitalize()),
            ('ведущий садовник', pos),
        ]
        items = normalize_items(base_body, num, renames)
        newblk.extend(items)
        if num in tgt_by:
            ts, te = tgt_by[num]
            tbody = blk[ts + 1:te]
            spec_idx = [i for i, x in enumerate(tbody)
                        if re.match(r'^\[\{\[СПС\d+-', x)]
            for si in spec_idx:
                sp = tbody[si]
                m = NUMRE.match(sp)
                if not m:
                    continue
                cnt = len([x for x in items if x.startswith('[{[')])
                newsp = (m.group(1) + f'{num}.{cnt+1}. ' +
                         re.sub(r'^\s*\d+\.\d+\.\s*', '', m.group(4)))
                newblk.append('')
                newblk.append(newsp)
                items.append(newsp)
                for x in tbody[si + 1:]:
                    if TAGL.match(x):
                        break
                    if re.match(r'^\d+\.\d+\.\d+', x):
                        newblk.append(re.sub(r'^\d+\.\d+\.', f'{num}.{cnt+1}.', x))
                    elif x.strip():
                        newblk.append(x)
        newblk.append('')
    lines[s:e] = newblk
    print(code, 'собран заново:', len(newblk), 'строк')

open('iotraw_final', 'w', encoding='utf-8').write('\n'.join(lines).rstrip() + '\n')
print('OK')
