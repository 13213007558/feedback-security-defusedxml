# defusedxml
#
# Copyright (c) 2013 by Christian Heimes <christian@python.org>
# Licensed to PSF under a Contributor Agreement.
# See https://www.python.org/psf/license for licensing details.
"""Defused xml.dom.minidom
"""
from __future__ import print_function, absolute_import

from xml.dom.minidom import _do_pulldom_parse
from . import expatbuilder as _expatbuilder
from . import pulldom as _pulldom

__origin__ = "xml.dom.minidom"


def parse(
    file,
    parser=None,
    bufsize=None,
    forbid_dtd=False,
    forbid_entities=True,
    forbid_external=True,
    strict=False,
):
    """Parse a file into a DOM by filename or file object.

    When a custom ``parser`` is supplied the SAX/pull-DOM path is used. With
    ``strict=True`` the parser is verified before any file or URL is opened;
    an unverifiable parser is rejected with
    :class:`~defusedxml.common.StrictParserPolicyError`. Without ``strict``
    the custom parser keeps the historical trust-as-is behavior.
    """
    if parser is None and not bufsize:
        return _expatbuilder.parse(
            file,
            forbid_dtd=forbid_dtd,
            forbid_entities=forbid_entities,
            forbid_external=forbid_external,
        )
    else:
        return _do_pulldom_parse(
            _pulldom.parse,
            (file,),
            {
                "parser": parser,
                "bufsize": bufsize,
                "forbid_dtd": forbid_dtd,
                "forbid_entities": forbid_entities,
                "forbid_external": forbid_external,
                "strict": strict,
            },
        )


def parseString(
    string,
    parser=None,
    forbid_dtd=False,
    forbid_entities=True,
    forbid_external=True,
    strict=False,
):
    """Parse a file into a DOM from a string.

    A custom ``parser`` is verified before reading the string when
    ``strict=True``; otherwise it is used as-is for backwards compatibility.
    """
    if parser is None:
        return _expatbuilder.parseString(
            string,
            forbid_dtd=forbid_dtd,
            forbid_entities=forbid_entities,
            forbid_external=forbid_external,
        )
    else:
        return _do_pulldom_parse(
            _pulldom.parseString,
            (string,),
            {
                "parser": parser,
                "forbid_dtd": forbid_dtd,
                "forbid_entities": forbid_entities,
                "forbid_external": forbid_external,
                "strict": strict,
            },
        )
