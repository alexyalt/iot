# -*- coding: utf-8 -*-
"""Проверка структуры и совпадения общих блоков с эталоном."""
import re, sys, importlib.util

sp = importlib.util.spec_from_file_location('g', '/tmp/iot/gen/gen2.py')
g = importlib.util.module_from_spec(sp); sp.loader.exec_module(g)

EXPECT = ['1.1', '1.2', '1.3', '1.4', '1.5', '1.6', '2.1', '2.2', '2.3', '2.4',
          '3.1', '3.2', '3.3', '3.4', '3.5', '4.1', '4.2', '4.3', '4.4',
          '5.1', '5.2', '5.3', '5.4', '5.5', '6.1', '6.2']
VERBATIM = ['1.2', '1.5', '2.3', '2.4', '4.1', '4.2', '4.3', '4.4', '6.1', '6.2']


def blocks(txt):
    out, cur, buf = {}, None, []
    for line in txt.split('\n'):
        m = re.match(r'^### (\d+\.\d+) ', line)
        if m:
            if cur: out[cur] = '\n'.join(buf).strip()
            cur, buf = m.group(1), []
        elif re.match(r'^## |^### |^# |^---', line):
            if cur: out[cur] = '\n'.join(buf).strip()
            cur, buf = None, []
        elif cur:
            buf.append(line)
    if cur: out[cur] = '\n'.join(buf).strip()
    return out


def check(path):
    txt = open(path, encoding='utf-8').read()
    errs = []
    secs = re.findall(r'^## (\d)\. ', txt, flags=re.M)
    if secs != ['1', '2', '3', '4', '5', '6']:
        errs.append(f'разделы: {secs}')
    b = blocks(txt)
    for k in EXPECT:
        if k not in b:
            errs.append(f'нет подраздела {k}')
    for k in VERBATIM:
        if k in b and b[k] != g.REF[k][1].strip():
            errs.append(f'{k} не совпадает с эталоном')
    if 'ПРИЛОЖЕНИЕ №1' not in txt:
        errs.append('нет Приложения №1')
    if 'Садовник' in txt.replace('«Садовник»', ''):
        # допустимо только в самом эталоне
        pass
    heads = re.findall(r'^### (\d+\.\d+) ', txt, flags=re.M)
    if heads != sorted(set(heads), key=heads.index):
        errs.append('дубли заголовков')
    return errs, len(txt)


if __name__ == '__main__':
    bad = 0
    for p in sys.argv[1:]:
        e, n = check(p)
        print(('OK  ' if not e else 'FAIL'), n, p.split('/')[-1], '; '.join(e))
        bad += bool(e)
    sys.exit(bad)
