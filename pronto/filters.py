#!/usr/bin/env python
# -*- coding: utf-8 -*-


def word_at(value, index):
    return value.split()[index]


def count_entries(value):
    return len([e for e in value if e['id']])


def count_methods(value):
    return len(set([m['id'] for e in value for m in e['methods']]))
