# -*- coding: utf-8 -*-
"""Exceptions"""


class NgsGluttonException(Exception):
    """Base exception class"""


class UnknownFlowcellLayoutException(NgsGluttonException):
    """Raised on unknown flowcell layout."""
