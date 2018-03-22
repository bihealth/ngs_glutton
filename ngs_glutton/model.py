# -*- coding: utf-8 -*-
"""Representation of the meta data information."""

import typing
import datetime
import pathlib


#: Status values
STATUSES = (
    'initial', 'in_progress', 'complete', 'failed', 'closed', 'canceled',
    'skipped')

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

    #: The run vendor ID
    id: str
    #: Flowcell barcode
    flowcell: str
    #: Date
    date: datetime.date
    #: Instrument ID
    instrument: str
    #: Reads information
    read_descriptions: typing.List[ReadDescription]
    #: Number of lanes
    lane_count: int


class RunParameters(typing.NamedTuple):
    """Information extracted from ``RunParameters.xml`` file."""

    #: Information about the planned reads
    planned_read_descriptions: typing.List[ReadDescription]
    #: Version of the RTA
    rta_version: str
    #: Run number on this instrument
    run_number: int
    #: Flow cell position/slot
    flowcell_slot: str
    #: Experiment name
    experiment_name: str


class RunFolder(typing.NamedTuple):
    """Container for the information contained in a run folder."""

    #: The run folder path used when parsing.
    run_folder_path: pathlib.Path
    #: The layout
    layout: str
    #: XML contents of "RunInfo.xml" file
    run_info_xml: str
    #: Information about the run
    run_info: RunInfo
    #: XML contents of "RunParameters.xml" file
    run_parameters_xml: str
    #: Parameterization of the run
    run_parameters: RunParameters


class SampleIndexedReadsStats(typing.NamedTuple):
    """Results from sampling indexed reads."""

    #: Number of index reads that were read
    num_indexed_reads: int
    #: Lower limit on count
    min_read_threshold: float
    #: For each lane (as 'L001', ...), a dict mapping str to count
    per_lane: typing.Dict[str, typing.Dict[str, int]]
