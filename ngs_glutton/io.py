# -*- coding: utf-8 -*-
"""Representation of the meta data information."""

import gzip
import datetime
import logging
from pathlib import Path
import struct
import typing
import xml.etree.ElementTree as ET

import numpy as np
import numpy.ma as ma

from . import model, exceptions

#: Folder layout for MiSeq or HiSeq 2000
FOLDER_LAYOUT_MISEQ_HISEQ2K = 'MiSeq_or_HiSeq_2000_2500'

#: Folder layout for MiniSeq or NextSeq.
FOLDER_LAYOUT_MINISEQ_NEXTSEQ = 'MiniSeq_or_NextSeq'

#: Folder layout for HiSeq X
FOLDER_LAYOUT_HISEQX = 'HiSeqX'

#: Known folder layouts.
FOLDER_LAYOUTS = (
    FOLDER_LAYOUT_MISEQ_HISEQ2K,
    FOLDER_LAYOUT_MINISEQ_NEXTSEQ,
    FOLDER_LAYOUT_HISEQX,
)


def guess_folder_layout(path: Path) -> str:
    """Guess folder layout from path"""
    miseq_marker = (
        path / 'Data' / 'Intensities' / 'BaseCalls' / 'L001' / 'C1.1')
    hiseqx_marker = path / 'Data' / 'Intensities' / 's.locs'
    miniseq_marker = path / 'Data' / 'Intensities' / 'BaseCalls' / 'L001'
    if miseq_marker.exists():
        return FOLDER_LAYOUT_MISEQ_HISEQ2K
    elif hiseqx_marker.exists():
        return FOLDER_LAYOUT_HISEQX
    elif miniseq_marker.exists():
        return FOLDER_LAYOUT_MINISEQ_NEXTSEQ
    else:
        raise exceptions.UnknownFlowcellLayoutException(
            'Unknown flowcell layout')


def parse_run_info(xmls: str) -> model.RunInfo:
    """Parse out run information from ``RunInfo.xml``."""
    root = ET.fromstring(xmls)
    tag_run = root.find('Run')
    run_id = tag_run.attrib['Id']
    run_flowcell = tag_run.find('Flowcell').text
    run_instrument = tag_run.find('Instrument').text
    run_date = datetime.datetime.strptime(
        tag_run.find('Date').text, '%y%m%d').date()
    run_reads = [
        model.ReadDescription(
            read.attrib['Number'],
            int(read.attrib['NumCycles']),
            {'Y': True, 'N': False}[read.attrib['IsIndexedRead']],
        )
        for read in tag_run.find('Reads').findall('Read')
    ]
    return model.RunInfo(
        run_id, run_flowcell, run_date, run_instrument, run_reads)


def parse_run_folder(path: Path) -> model.RunFolder:
    """Read ``RunInfo.xml`` file from the given ``path``."""
    logging.info('Reading %s/RunInfo.xml', path)
    with open(path / 'RunInfo.xml', 'rt') as xmlf:
        xmls = xmlf.read()
    return model.RunFolder(path, xmls, parse_run_info(xmls))


class _BaseIndexedReadSampler(object):
    """Base class for index sampling"""

    def __init__(
            self,
            run_folder: model.RunFolder,
            num_reads: int,
            lower_thresh: float):
        #: The RunFolder
        self.run_folder = run_folder
        #: The number of reads to sample per lane
        self.num_reads = num_reads
        #: The lower threshold of reads
        self.lower_thresh = lower_thresh

    def run(self) -> [model.SampleIndexedReadsStats]:
        # Iterate over index reads
        result = []
        cycle = 1
        for read_desc in self.run_folder.run_info.read_descriptions:
            if read_desc.is_indexed_read:
                result.append(self._do_sample(read_desc, cycle))
            cycle += read_desc.num_cycles
        return result

    def _do_sample(self, read_desc: model.ReadDescription, start_cycle: int):
        raise NotImplementedError('Override me!')

    def _sample_for_lane(
            self,
            read_desc: model.ReadDescription,
            start_cycle: int,
            cycle_to_path) -> typing.Dict[str, int]:
        """Sample for the lane."""
        cycle_bases = []
        cycles = range(start_cycle, start_cycle + read_desc.num_cycles)
        logging.info('Considering cycles %s', list(cycles))
        for cycle in cycles:
            bcl_bgzf = cycle_to_path(cycle)
            logging.debug('Extracting adapters from file %s', bcl_bgzf)
            with gzip.GzipFile(bcl_bgzf, 'rb') as bclf:
                # Read number of bytes in file.
                bytes_num = bclf.read(4)
                num = min(self.num_reads, struct.unpack('I', bytes_num)[0])
                # Read array with bases and quality values, mask "0" as we have
                # to differentiate 'N' from 'A'.
                bytes_bases = bclf.read(num)
                arr_base_qual = np.frombuffer(bytes_bases, dtype=np.uint8)
                masked_base_qual = ma.masked_where(
                    arr_base_qual == 0, arr_base_qual)
                # Remove quality values and replace mask by 5
                masked_base = np.bitwise_and(masked_base_qual, 3)
                masked_base_n = ma.filled(masked_base, 4)
                # Convert to char
                masked_base_n = np.vectorize(
                    lambda x: 'ACGTN'[x])(masked_base_n)
                cycle_bases.append(masked_base_n)
        histogram = {}
        for row in np.vstack(cycle_bases).T:
            seq = ''.join(row)
            histogram.setdefault(seq, 0)
            histogram[seq] += 1
        thresh = int(self.lower_thresh * num)
        return {
            seq: count
            for seq, count in sorted(
                histogram.items(), key=lambda x: x[1], reverse=True)
            if count > thresh}


class _MiSeqHiSeq2kReadSampler(_BaseIndexedReadSampler):
    """Sampling from MiSeq and HiSeq 2000/2500 output"""

    def _do_sample(self, read_desc: model.ReadDescription, start_cycle: int):
        """Sample the read, starting at the given cycle"""
        # Iterate over base call directory
        base_calls_dir = (
            self.run_folder.run_folder_path / 'Data' / 'Intensities' /
            'BaseCalls')
        result = {}
        for lane in sorted(base_calls_dir.glob('L???')):
            logging.info('Considering lane %s', lane.name)
            tile = list(sorted((lane / 'C1.1').glob('*.bcl.gz')))[10]

            def cycle_to_path(cycle):
                return lane / 'C{}.1'.format(cycle) / tile.name

            result[lane.name] = self._sample_for_lane(
                read_desc, start_cycle, cycle_to_path)
        return model.SampleIndexedReadsStats(
            self.num_reads, self.lower_thresh, result)


class _MiniSeqNextSeqIndexedReadSampler(_BaseIndexedReadSampler):
    """Sampling from MiniSeq/NextSeq output."""

    def _do_sample(self, read_desc: model.ReadDescription, start_cycle: int):
        """Sample the read, starting at the given cycle"""
        # Iterate over base call directory
        base_calls_dir = (
            self.run_folder.run_folder_path / 'Data' / 'Intensities' /
            'BaseCalls')
        result = {}
        for lane in sorted(base_calls_dir.glob('L???')):
            logging.info('Considering lane %s', lane.name)

            def cycle_to_lane(cycle):
                return lane / '{:04d}.bcl.bgzf'.format(cycle)

            result[lane.name] = self._sample_for_lane(
                read_desc, start_cycle, cycle_to_lane)
        return model.SampleIndexedReadsStats(
            self.num_reads, self.lower_thresh, result)


class _IndexedReadSamplingDriver(object):
    """Dispatch index read sampling"""

    def __init__(
            self,
            run_folder: model.RunFolder,
            num_reads: int,
            lower_thresh: float):
        #: The RunFolder
        self.run_folder = run_folder
        #: The number of reads to sample per lane
        self.num_reads = num_reads
        #: The lower threshold of reads
        self.lower_thresh = lower_thresh

    def run(self) -> [model.SampleIndexedReadsStats]:
        # Guess layout and check
        logging.info('Sampling adapter sequences from raw output folder %s',
                     self.run_folder)
        layout = guess_folder_layout(self.run_folder.run_folder_path)
        if layout == FOLDER_LAYOUT_MINISEQ_NEXTSEQ:
            result = _MiniSeqNextSeqIndexedReadSampler(
                self.run_folder, self.num_reads, self.lower_thresh).run()
        elif layout == FOLDER_LAYOUT_MISEQ_HISEQ2K:
            result = _MiSeqHiSeq2kReadSampler(
                self.run_folder, self.num_reads, self.lower_thresh).run()
        else:
            raise exceptions.NgsGluttonException(
                'Can only handle MiniSeq, NextSeq, MiSeq, HiSeq 2000/2500 '
                'for now!')
        logging.debug('Result is %s', result)
        return result


def sample_indexed_reads(
        run_folder: model.RunFolder,
        num_reads: int = 10_000,
        lower_thresh: float = 0.01) -> [model.SampleIndexedReadsStats]:
    """Sample indexed reads.

    Will sample ``num_reads`` reads from each lane, ignoring everything that
    is below ``lower_thres * num_reads``.
    """
    return _IndexedReadSamplingDriver(
        run_folder, num_reads, lower_thresh).run()


def read_quality_scores(
        run_folder: model.RunFolder):
    return None
