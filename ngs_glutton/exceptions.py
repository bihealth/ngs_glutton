# -*- coding: utf-8 -*-
"""Exceptions"""


class NgsGluttonException(Exception):
    """Base exception class"""


class UnknownFlowcellLayoutException(NgsGluttonException):
    """Raised on unknown flowcell layout."""


class InvalidCommandLineArguments(NgsGluttonException):
    """Raised on problems with command line arguments."""


class UnknownFlowcellException(NgsGluttonException):
    """Raised when the flowcell is not known."""
