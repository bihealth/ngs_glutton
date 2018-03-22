#!/usr/bin/env python

import csv
import sys

import pandas as pd


def process_corrected_int(section):
    section['data'] = [list(map(int, arr)) for arr in section['data']]
    cols_int = ['Cycle', 'CalledIntensity_A', 'CalledIntensity_C',
                'CalledIntensity_G', 'CalledIntensity_T']
    df = pd.DataFrame(section['data'], columns=section['header'])
    mean_ints = df[[*cols_int]].groupby('Cycle').mean()
    mean_ints.column = [
            'Cycle', 'Mean_calledintensity_a', 'Mean_calledintensity_c',
            'Mean_CalledIntensity_G', 'Mean_CalledIntensity_T']
    print(mean_ints, file=sys.stderr)
    cols_called = [
        'Cycle', 'CalledCount_A', 'CalledCount_C',
        'CalledCount_G', 'CalledCount_T']
    num_bases = df[[*cols_called]].groupby('Cycle').sum()
    num_bases.column = [
            'Cycle', 'Sum_CalledCount_A', 'Sum_CalledCount_C',
            'Sum_CalledCount_G', 'Sum_CalledCount_T']
    print(num_bases, file=sys.stderr)


def process_q_by_lane(section):
    section['data'] = [list(map(int, arr)) for arr in section['data']]
    df = pd.DataFrame(section['data'], columns=section['header'])
    sum_qs = df.groupby('Cycle').mean()
    sum_qs.column = [
        'Cycle', 'Sum_Bin_1', 'Sum_Bin_2', 'Sum_Bin_3', 'Sum_Bin_4',
        'Sum_Bin_5', 'Sum_Bin_6', 'Sum_Bin_7']
    print(sum_qs)


def dispatch(section):
    """Perform dispatching based on section type."""
    if section['name'] == 'CorrectedInt':
        process_corrected_int(section)
    elif section['name'] == 'QByLane':
        process_q_by_lane(section)

def process_file(inputf):
    """Process input file.
    
    Read file section by section and use ``dispatch()`` for doing the actual
    work.
    """
    print('Processing...', file=sys.stderr)
    state = 'begin'
    version_line = None
    sections = []
    section = {'name': None}

    for line in csv.reader(inputf, delimiter=','):
        if not line:
            continue
        elif not version_line:
            version_line = line
            assert version_line[0].startswith('# Version')
            assert state == 'begin'
        elif line[0].startswith('#') and len(line) > 1:  # new section
            if section['name']:
                print('Dispatching...', file=sys.stderr)
                dispatch(section)
            section = {
                'name': line[0][2:],
                'version': line[1],
                'header': None,
                'bin_count': None,
                'bins': None,
                'data': [],
            }
            state = 'section'
        elif line[0].startswith('#') and line[0].startswith('# Bin Count'):
            section['bin_count'] = int(line[0].split(':')[1])
            section['bins'] = []
            state = 'bins'
        elif line[0].startswith('#'):
            state = 'header'
        else:
            if state == 'header':
                section['header'] = line
                state ='data'
            elif state == 'bins':
                section['bins'].append(line)
            else:
                section['data'].append(line)
    if section['data']:
        print('Dispatching...', file=sys.stderr)
        dispatch(section)

if __name__ == '__main__':
    with open(sys.argv[1], 'rt') as inputf:
        process_file(inputf)
