# defusedxml
#
# Copyright (c) 2013 by Christian Heimes <christian@python.org>
# Licensed to PSF under a Contributor Agreement.
# See https://www.python.org/psf/license for licensing details.
"""Defused xml.dom.pulldom
"""
from __future__ import print_function, absolute_import

from xml.dom.pulldom import parse as _parse
from xml.dom.pulldom import parseString as _parseString
from .sax import make_parser, verify_strict_parser

__origin__ = "xml.dom.pulldom"


def parse(
    stream_or_string,
    parser=None,
    bufsize=None,
    forbid_dtd=False,
    forbid_entities=True,
    forbid_external=True,
    strict=False,
):
    """Parse a stream, filename or URL into a pull DOM event stream.

    A custom ``parser`` is trusted as-is unless ``strict=True``. In strict
    mode the parser is verified before the stream or URL is opened; an
    unverifiable parser raises
    :class:`~defusedxml.common.StrictParserPolicyError` without reading any
    input.
    """
    if parser is None:
        parser = make_parser()
        parser.forbid_dtd = forbid_dtd
        parser.forbid_entities = forbid_entities
        parser.forbid_external = forbid_external
    elif strict:
        verify_strict_parser(
            parser, forbid_dtd, forbid_entities, forbid_external
        )
    return _parse(stream_or_string, parser, bufsize)


def parseString(
    string,
    parser=None,
    forbid_dtd=False,
    forbid_entities=True,
    forbid_external=True,
    strict=False,
):
    """Parse a string into a pull DOM event stream.

    The same trust boundary and ``strict`` verification as :func:`parse`
    apply to a custom ``parser``.
    """
    if parser is None:
        parser = make_parser()
        parser.forbid_dtd = forbid_dtd
        parser.forbid_entities = forbid_entities
        parser.forbid_external = forbid_external
    elif strict:
        verify_strict_parser(
            parser, forbid_dtd, forbid_entities, forbid_external
        )
    return _parseString(string, parser)
