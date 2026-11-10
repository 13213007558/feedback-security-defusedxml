# defusedxml
#
# Copyright (c) 2013 by Christian Heimes <christian@python.org>
# Licensed to PSF under a Contributor Agreement.
# See https://www.python.org/psf/license for licensing details.
"""Defused xmlrpclib

Also defuses gzip bomb
"""
from __future__ import print_function, absolute_import

import io

from .common import DTDForbidden, EntitiesForbidden, ExternalReferenceForbidden

__origin__ = "xmlrpc.client"
from xmlrpc.client import ExpatParser
from xmlrpc import client as xmlrpc_client
from xmlrpc import server as xmlrpc_server
from xmlrpc.client import gzip_decode as _orig_gzip_decode
from xmlrpc.client import GzipDecodedResponse as _OrigGzipDecodedResponse

try:
    import gzip
except ImportError:  # pragma: no cover
    gzip = None


# Limit maximum request size to prevent resource exhaustion DoS
# Also used to limit maximum amount of gzip decoded data in order to prevent
# decompression bombs
# A value of -1 or smaller disables the limit
MAX_DATA = 30 * 1024 * 1024  # 30 MB


def defused_gzip_decode(data, limit=None):
    """gzip encoded data -> unencoded data

    Decode data using the gzip content encoding as described in RFC 1952
    """
    if not gzip:  # pragma: no cover
        raise NotImplementedError
    if limit is None:
        limit = MAX_DATA
    f = io.BytesIO(data)
    gzf = gzip.GzipFile(mode="rb", fileobj=f)
    try:
        if limit < 0:  # no limit
            decoded = gzf.read()
        else:
            decoded = gzf.read(limit + 1)
    except IOError:  # pragma: no cover
        raise ValueError("invalid data")
    f.close()
    gzf.close()
    if limit >= 0 and len(decoded) > limit:
        raise ValueError("max gzipped payload length exceeded")
    return decoded


class DefusedGzipDecodedResponse(gzip.GzipFile if gzip else object):
    """a file-like object to decode a response encoded with the gzip
    method, as described in RFC 1952.

    The response is decompressed as a bounded stream instead of being
    buffered in memory first.  At most ``max_input`` compressed bytes
    are read from the underlying response and at most ``max_output``
    decompressed bytes are handed to the caller.  Both budgets are
    cumulative over the whole stream, including concatenated gzip
    members, and are never reset by chunked reads.  The legacy
    ``limit`` argument sets both budgets at once; a negative value
    disables a budget.

    This layer takes ownership of ``response``: it is closed when the
    decoder is closed, when decoding fails, or when a budget is
    exceeded.  Decompression errors (truncated members, CRC or length
    mismatches, trailing non-gzip data) and exceeded budgets raise
    instead of returning partial data.
    """

    def __init__(self, response, limit=None, max_input=None, max_output=None):
        if not gzip:  # pragma: no cover
            raise NotImplementedError
        if limit is None:
            limit = MAX_DATA
        self.limit = limit
        if max_input is None:
            max_input = limit
        if max_output is None:
            max_output = limit
        self.max_input = max_input
        self.max_output = max_output
        self._readlength = 0
        self._response = response
        self._stream = _LimitedStream(response, max_input)
        super().__init__(mode="rb", fileobj=self._stream)

    def read(self, size=-1):
        try:
            return self._read(size)
        except Exception:
            self.close()
            raise

    def read1(self, size=-1):
        return self.read(size)

    def _read(self, size):
        if self.max_output < 0:  # no limit
            return super().read(-1 if size is None else size)
        if size is None or size < 0:
            chunks = []
            while True:
                chunk = self._read(io.DEFAULT_BUFFER_SIZE)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks)
        if size == 0:
            return b""
        size = min(size, self.max_output - self._readlength + 1)
        data = super().read(size)
        self._readlength += len(data)
        if self._readlength > self.max_output:
            raise ValueError("max payload length exceeded")
        return data

    def close(self):
        response = getattr(self, "_response", None)
        self._response = None
        try:
            super().close()
        except AttributeError:
            pass
        finally:
            if response is not None:
                response.close()


class _LimitedStream:
    """Bounded reader over a byte stream.

    Raises ValueError once more than ``limit`` bytes have been
    consumed in total; a negative limit disables the check.  Reads are
    always bounded: the wrapped stream is never asked for more than
    the remaining budget plus one byte to detect an overflow.
    """

    def __init__(self, raw, limit):
        self._raw = raw
        self._limit = limit
        self._consumed = 0

    def read(self, size=-1):
        if size is None or size < 0:
            if self._limit < 0:  # no limit
                return self._raw.read()
            chunks = []
            while True:
                chunk = self.read(io.DEFAULT_BUFFER_SIZE)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks)
        if size == 0:
            return b""
        if self._limit >= 0:
            size = min(size, self._limit - self._consumed + 1)
        data = self._raw.read(size)
        self._consumed += len(data)
        if self._limit >= 0 and self._consumed > self._limit:
            raise ValueError("max gzipped payload length exceeded")
        return data

    def close(self):
        pass


class DefusedExpatParser(ExpatParser):
    def __init__(self, target, forbid_dtd=False, forbid_entities=True, forbid_external=True):
        super().__init__(target)
        self.forbid_dtd = forbid_dtd
        self.forbid_entities = forbid_entities
        self.forbid_external = forbid_external
        parser = self._parser
        if self.forbid_dtd:
            parser.StartDoctypeDeclHandler = self.defused_start_doctype_decl
        if self.forbid_entities:
            parser.EntityDeclHandler = self.defused_entity_decl
            parser.UnparsedEntityDeclHandler = self.defused_unparsed_entity_decl
        if self.forbid_external:
            parser.ExternalEntityRefHandler = self.defused_external_entity_ref_handler

    def defused_start_doctype_decl(self, name, sysid, pubid, has_internal_subset):
        raise DTDForbidden(name, sysid, pubid)

    def defused_entity_decl(
        self, name, is_parameter_entity, value, base, sysid, pubid, notation_name
    ):
        raise EntitiesForbidden(name, value, base, sysid, pubid, notation_name)

    def defused_unparsed_entity_decl(self, name, base, sysid, pubid, notation_name):
        # expat 1.2
        raise EntitiesForbidden(name, None, base, sysid, pubid, notation_name)  # pragma: no cover

    def defused_external_entity_ref_handler(self, context, base, sysid, pubid):
        raise ExternalReferenceForbidden(context, base, sysid, pubid)


def monkey_patch():
    xmlrpc_client.FastParser = DefusedExpatParser
    xmlrpc_client.GzipDecodedResponse = DefusedGzipDecodedResponse
    xmlrpc_client.gzip_decode = defused_gzip_decode
    if xmlrpc_server:
        xmlrpc_server.gzip_decode = defused_gzip_decode


def unmonkey_patch():
    xmlrpc_client.FastParser = None
    xmlrpc_client.GzipDecodedResponse = _OrigGzipDecodedResponse
    xmlrpc_client.gzip_decode = _orig_gzip_decode
    if xmlrpc_server:
        xmlrpc_server.gzip_decode = _orig_gzip_decode
