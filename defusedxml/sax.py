# defusedxml
#
# Copyright (c) 2013 by Christian Heimes <christian@python.org>
# Licensed to PSF under a Contributor Agreement.
# See https://www.python.org/psf/license for licensing details.
"""Defused xml.sax
"""
from __future__ import print_function, absolute_import

from xml.sax import InputSource as _InputSource
from xml.sax import ErrorHandler as _ErrorHandler

from . import expatreader
from .common import (
    _check_expat_slots,
    _strict_policy_error,
    _verify_policy_flags,
)

__origin__ = "xml.sax"


def parse(
    source,
    handler,
    errorHandler=_ErrorHandler(),
    forbid_dtd=False,
    forbid_entities=True,
    forbid_external=True,
):
    parser = make_parser()
    parser.setContentHandler(handler)
    parser.setErrorHandler(errorHandler)
    parser.forbid_dtd = forbid_dtd
    parser.forbid_entities = forbid_entities
    parser.forbid_external = forbid_external
    parser.parse(source)


def parseString(
    string,
    handler,
    errorHandler=_ErrorHandler(),
    forbid_dtd=False,
    forbid_entities=True,
    forbid_external=True,
):
    from io import BytesIO

    if errorHandler is None:
        errorHandler = _ErrorHandler()
    parser = make_parser()
    parser.setContentHandler(handler)
    parser.setErrorHandler(errorHandler)
    parser.forbid_dtd = forbid_dtd
    parser.forbid_entities = forbid_entities
    parser.forbid_external = forbid_external

    inpsrc = _InputSource()
    inpsrc.setByteStream(BytesIO(string))
    parser.parse(inpsrc)


def make_parser(parser_list=[]):
    return expatreader.create_parser()


def verify_strict_parser(
    parser, forbid_dtd, forbid_entities, forbid_external
):
    """Prove that a caller-supplied SAX parser enforces the hardening policy.

    Only a :class:`~defusedxml.expatreader.DefusedExpatParser` (or subclass)
    can be verified. The boolean policy flags are checked and the live pyexpat
    handler slots are inspected as authoritative proof.

    A pristine SAX parser lazily creates its pyexpat object in ``reset()``. For
    such a parser -- and only when it is not already parsing -- ``reset()`` is
    called once so the slots can be proven. A parser that is already in use is
    never reset, preserving its in-progress parse state and its installed
    handlers.
    """
    if not isinstance(parser, expatreader.DefusedExpatParser):
        raise _strict_policy_error(
            "custom parser is not a DefusedExpatParser instance; defusedxml "
            "cannot prove that it enforces the requested hardening policy",
            parser,
            forbid_dtd,
            forbid_entities,
            forbid_external,
        )

    error = _verify_policy_flags(
        parser, forbid_dtd, forbid_entities, forbid_external
    )
    if error is not None:
        raise error

    if parser._parser is None:
        if parser._parsing:
            # Do not disturb a parser that is actively processing a document.
            raise _strict_policy_error(
                "parser has no pyexpat object yet but is already parsing; "
                "its hardening cannot be verified",
                parser,
                forbid_dtd,
                forbid_entities,
                forbid_external,
            )
        parser.reset()

    error = _check_expat_slots(
        parser._parser, parser, forbid_dtd, forbid_entities, forbid_external
    )
    if error is not None:
        raise error
