# -*- coding: utf-8 -*-
"""Полная сборка инструкции: все 6 разделов + Приложение №1."""
import importlib.util, os, re

_s = importlib.util.spec_from_file_location('mk', '/tmp/iot/gen/mk.py')
mk = importlib.util.module_from_spec(_s); _s.loader.exec_module(mk)


def full(spec, filename=None):
    """spec: title, sub, code, positions, purpose, funcs, role_term(name,def),
    hazards(blocks), extra_ppe(list), sec3(body), sec5(dict of 5 overrides or None)"""
    P = spec['positions']
    sec1 = '\n\n'.join([
        mk.s11(P, spec['purpose'], spec['funcs']),
        mk.verbatim('1.2'),
        mk.s13(spec['role_term'][0], spec['role_term'][1], spec.get('extra_terms', [])),
        mk.s14(P, '', spec['hazards'], spec.get('haz_tail')),
        mk.verbatim('1.5'),
        mk.s16(P, spec['extra_ppe']),
    ])
    sec2 = '\n\n'.join([mk.verbatim('2.1'), mk.verbatim('2.2'), mk.verbatim('2.3'),
                        mk.verbatim('2.4'), mk.verbatim('2.5')])
    if spec.get('sec2_extra'):
        sec2 += '\n\n' + spec['sec2_extra']
    sec5 = spec.get('sec5') or None
    if sec5:
        sec5 = '\n\n'.join([
            mk.retitle('5.1', '5.1 Выполнение отключения оборудования', sec5.get('close')),
            mk.retitle('5.2', '5.2 Приём и сдача рабочего места', sec5.get('hand')),
            mk.retitle('5.3', '5.3 Снятие СИЗ и спецодежды', sec5.get('ppe')),
            mk.retitle('5.4', '5.4 Уборка рабочего места', sec5.get('clean')),
            mk.retitle('5.5', '5.5 Гигиенические процедуры', sec5.get('hyg')),
        ])
    else:
        sec5 = mk.s5()
    s = dict(spec)
    s.update({'sec1': sec1, 'sec2': sec2, 'sec3': spec['sec3'],
              'sec4': mk.s4(), 'sec5': sec5, 'sec6': mk.s6()})
    fn = filename or spec['filename']
    return mk.build(s, fn)
