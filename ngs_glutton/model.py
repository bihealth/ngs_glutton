# -*- coding: utf-8 -*-
"""Representation of the meta data information."""

import typing
import datetime
import pathlib


class ReadDescription(typing.NamedTuple):
    """Representation of ``RunInfo/Run/Reads/Read`` from the XML file."""

    #: The read number.
    number: int
    #: The cycle number.
    num_cycles: int
    #: Whether or not read is indexed.
    is_indexed_read: bool


class RunInfo(typing.NamedTuple):
    """Information about the run"""

    #: The run ID
    id: str
    #: Flowcell ID
    flowcell: str
    #: Date
    date: datetime.date
    #: Instrument ID
    instrument: str
    #: Reads information
    read_descriptions: typing.List[ReadDescription]


class RunFolder(typing.NamedTuple):
    """Container for the information contained in a run folder."""

    #: The run folder path used when parsing.
    run_folder_path: pathlib.Path
    #: XML contents of "RunInfo.xml" file
    run_info_xml: str
    #: Information about the run
    run_info: RunInfo


class SampleIndexedReadsStats(typing.NamedTuple):
    """Results from sampling indexed reads."""

    #: Number of index reads that were read
    num_indexed_reads: int
    #: For each lane (as 'L001', ...), a dict mapping str to count
    per_lane: typing.Dict[str, typing.Dict[str, int]]

