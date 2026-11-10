from __future__ import print_function

import io
import os
import sys
import unittest
import warnings
from unittest import mock

from xml.etree import ElementTree as orig_elementtree
from xml.etree.ElementTree import Element as ElementBeforeImport
from xml.sax.saxutils import XMLGenerator
from xml.sax import SAXParseException
from pyexpat import ExpatError

from defusedxml import ElementTree, minidom, pulldom, sax, xmlrpc, expatreader
from defusedxml import defuse_stdlib
from defusedxml import (
    DTDForbidden,
    EntitiesForbidden,
    ExternalReferenceForbidden,
    NotSupportedError,
)
from defusedxml.scope import (
    DefusingScope,
    ScopeConflictError,
    ScopeConflictWarning,
    _iter_targets,
    _active_scopes,
    _MISSING,
)
import xml.etree.ElementTree as stdlib_etree
import xml.dom.minidom as stdlib_minidom
import xmlrpc.client as stdlib_xmlrpc_client

from xml.etree.ElementTree import Element as ElementAfterImport

if sys.version_info < (3, 7):
    warnings.filterwarnings("once", category=DeprecationWarning)


with warnings.catch_warnings(record=True) as cetree_warnings:
    from defusedxml import cElementTree


try:
    import gzip
except ImportError:
    gzip = None


try:
    with warnings.catch_warnings(record=True) as lxml_warnings:
        from defusedxml import lxml
    from lxml import etree as lxml_etree

    LXML3 = lxml.LXML3
except ImportError:
    lxml = None
    lxml_etree = None
    LXML3 = False
    lxml_warnings = None


warnings.filterwarnings("always", category=DeprecationWarning, module=r"defusedxml\..*")


HERE = os.path.dirname(os.path.abspath(__file__))

# prevent web access
# based on Debian's rules, Port 9 is discard
os.environ["http_proxy"] = "http://127.0.9.1:9"
os.environ["https_proxy"] = os.environ["http_proxy"]
os.environ["ftp_proxy"] = os.environ["http_proxy"]


class DefusedTestCase(unittest.TestCase):
    content_binary = False

    xml_dtd = os.path.join(HERE, "xmltestdata", "dtd.xml")
    xml_external = os.path.join(HERE, "xmltestdata", "external.xml")
    xml_external_file = os.path.join(HERE, "xmltestdata", "external_file.xml")
    xml_quadratic = os.path.join(HERE, "xmltestdata", "quadratic.xml")
    xml_simple = os.path.join(HERE, "xmltestdata", "simple.xml")
    xml_simple_ns = os.path.join(HERE, "xmltestdata", "simple-ns.xml")
    xml_bomb = os.path.join(HERE, "xmltestdata", "xmlbomb.xml")
    xml_bomb2 = os.path.join(HERE, "xmltestdata", "xmlbomb2.xml")
    xml_cyclic = os.path.join(HERE, "xmltestdata", "cyclic.xml")
    xml_dtd_element = os.path.join(HERE, "xmltestdata", "dtd_element.xml")
    xml_schema_include = os.path.join(HERE, "xmltestdata", "schema-include.xsd")

    def get_content(self, xmlfile):
        mode = "rb" if self.content_binary else "r"
        with io.open(xmlfile, mode) as f:
            data = f.read()
        return data


class BaseTests(DefusedTestCase):
    module = None
    dtd_external_ref = False

    external_ref_exception = ExternalReferenceForbidden
    cyclic_error = None
    iterparse = None

    def test_simple_parse(self):
        self.parse(self.xml_simple)
        self.parseString(self.get_content(self.xml_simple))
        if self.iterparse:
            self.iterparse(self.xml_simple)

    def test_simple_parse_ns(self):
        self.parse(self.xml_simple_ns)
        self.parseString(self.get_content(self.xml_simple_ns))
        if self.iterparse:
            self.iterparse(self.xml_simple_ns)

    def test_entities_forbidden(self):
        self.assertRaises(EntitiesForbidden, self.parse, self.xml_bomb)
        self.assertRaises(EntitiesForbidden, self.parse, self.xml_quadratic)
        self.assertRaises(EntitiesForbidden, self.parse, self.xml_external)

        self.assertRaises(EntitiesForbidden, self.parseString, self.get_content(self.xml_bomb))
        self.assertRaises(
            EntitiesForbidden, self.parseString, self.get_content(self.xml_quadratic)
        )
        self.assertRaises(
            EntitiesForbidden, self.parseString, self.get_content(self.xml_external)
        )

        if self.iterparse:
            self.assertRaises(EntitiesForbidden, self.iterparse, self.xml_bomb)
            self.assertRaises(EntitiesForbidden, self.iterparse, self.xml_quadratic)
            self.assertRaises(EntitiesForbidden, self.iterparse, self.xml_external)

    def test_entity_cycle(self):
        self.assertRaises(self.cyclic_error, self.parse, self.xml_cyclic, forbid_entities=False)

    def test_dtd_forbidden(self):
        self.assertRaises(DTDForbidden, self.parse, self.xml_bomb, forbid_dtd=True)
        self.assertRaises(DTDForbidden, self.parse, self.xml_quadratic, forbid_dtd=True)
        self.assertRaises(DTDForbidden, self.parse, self.xml_external, forbid_dtd=True)
        self.assertRaises(DTDForbidden, self.parse, self.xml_dtd, forbid_dtd=True)

        self.assertRaises(
            DTDForbidden, self.parseString, self.get_content(self.xml_bomb), forbid_dtd=True
        )
        self.assertRaises(
            DTDForbidden, self.parseString, self.get_content(self.xml_quadratic), forbid_dtd=True
        )
        self.assertRaises(
            DTDForbidden, self.parseString, self.get_content(self.xml_external), forbid_dtd=True
        )
        self.assertRaises(
            DTDForbidden, self.parseString, self.get_content(self.xml_dtd), forbid_dtd=True
        )

        if self.iterparse:
            self.assertRaises(DTDForbidden, self.iterparse, self.xml_bomb, forbid_dtd=True)
            self.assertRaises(DTDForbidden, self.iterparse, self.xml_quadratic, forbid_dtd=True)
            self.assertRaises(DTDForbidden, self.iterparse, self.xml_external, forbid_dtd=True)
            self.assertRaises(DTDForbidden, self.iterparse, self.xml_dtd, forbid_dtd=True)

    def test_dtd_with_external_ref(self):
        if self.dtd_external_ref:
            self.assertRaises(self.external_ref_exception, self.parse, self.xml_dtd)
        else:
            self.parse(self.xml_dtd)

    def test_external_ref(self):
        self.assertRaises(
            self.external_ref_exception, self.parse, self.xml_external, forbid_entities=False
        )

    def test_external_file_ref(self):
        content = self.get_content(self.xml_external_file)
        if isinstance(content, bytes):
            here = HERE.encode(sys.getfilesystemencoding())
            content = content.replace(b"/PATH/TO", here)
        else:
            content = content.replace("/PATH/TO", HERE)
        self.assertRaises(
            self.external_ref_exception, self.parseString, content, forbid_entities=False
        )

    def test_allow_expansion(self):
        self.parse(self.xml_bomb2, forbid_entities=False)
        self.parseString(self.get_content(self.xml_bomb2), forbid_entities=False)

    def test_dtd_element(self):
        self.parse(self.xml_dtd_element)


class TestDefusedElementTree(BaseTests):
    module = ElementTree

    # etree doesn't do external ref lookup
    # external_ref_exception = ElementTree.ParseError

    cyclic_error = ElementTree.ParseError

    def parse(self, xmlfile, **kwargs):
        tree = self.module.parse(xmlfile, **kwargs)
        return self.module.tostring(tree.getroot())

    def parseString(self, xmlstring, **kwargs):
        tree = self.module.fromstring(xmlstring, **kwargs)
        return self.module.tostring(tree)

    def parseStringList(self, sequence, **kwargs):
        tree = self.module.fromstringlist(sequence, **kwargs)
        return self.module.tostring(tree)

    def iterparse(self, source, **kwargs):
        return list(self.module.iterparse(source, **kwargs))

    def test_html_arg(self):
        with warnings.catch_warnings(record=True) as w:
            self.module.XMLParse(html=0)
        self.assertEqual(len(w), 1)
        self.assertIs(w[0].category, DeprecationWarning)
        with self.assertRaises(TypeError):
            self.module.XMLParse(html=1)

    def test_aliases(self):
        parser = self.module.DefusedXMLParser
        assert self.module.XMLTreeBuilder is parser
        assert self.module.XMLParser is parser
        assert self.module.XMLParse is parser

    def test_fromstringlist(self):
        seq = ["<root>", '<tag id="one" />', '<tag id="two" />', "</root>"]
        tree = self.module.fromstringlist(seq)
        result = self.module.tostring(tree)
        self.assertEqual(result, "".join(seq).encode("utf-8"))

    def test_import_order(self):
        from xml.etree import ElementTree as second_elementtree

        self.assertIs(orig_elementtree, second_elementtree)

    def test_orig_parseerror(self):
        # https://github.com/tiran/defusedxml/issues/63
        self.assertIs(self.module.ParseError, orig_elementtree.ParseError)
        try:
            self.parseString("invalid")
        except Exception as e:
            self.assertIsInstance(e, orig_elementtree.ParseError)
            self.assertIsInstance(e, self.module.ParseError)

    def test_etree_element(self):
        tree = tree = self.module.parse(self.xml_simple)
        root = tree.getroot()
        root.append(orig_elementtree.Element("module-import"))
        root.append(ElementBeforeImport("before-import"))
        root.append(ElementAfterImport("after-import"))
        s = orig_elementtree.tostring(root)
        self.assertEqual(s.count(b"import"), 3, s)


class TestDefusedcElementTree(TestDefusedElementTree):
    module = cElementTree

    def test_celementtree_warnings(self):
        self.assertTrue(cetree_warnings)
        self.assertEqual(cetree_warnings[0].category, DeprecationWarning)
        self.assertIn("tests.py", cetree_warnings[0].filename)


class TestDefusedMinidom(BaseTests):
    module = minidom

    cyclic_error = ExpatError

    iterparse = None

    def parse(self, xmlfile, **kwargs):
        doc = self.module.parse(xmlfile, **kwargs)
        return doc.toxml()

    def parseString(self, xmlstring, **kwargs):
        doc = self.module.parseString(xmlstring, **kwargs)
        return doc.toxml()


class TestDefusedMinidomWithParser(TestDefusedMinidom):
    cyclic_error = SAXParseException
    dtd_external_ref = True

    def parse(self, xmlfile, **kwargs):
        doc = self.module.parse(xmlfile, parser=expatreader.create_parser(**kwargs), **kwargs)
        return doc.toxml()

    def parseString(self, xmlstring, **kwargs):
        doc = self.module.parseString(
            xmlstring, parser=expatreader.create_parser(**kwargs), **kwargs
        )
        return doc.toxml()


class TestDefusedPulldom(BaseTests):
    module = pulldom

    cyclic_error = SAXParseException

    dtd_external_ref = True

    def parse(self, xmlfile, **kwargs):
        events = self.module.parse(xmlfile, **kwargs)
        return list(events)

    def parseString(self, xmlstring, **kwargs):
        events = self.module.parseString(xmlstring, **kwargs)
        return list(events)


class TestDefusedSax(BaseTests):
    module = sax

    cyclic_error = SAXParseException

    content_binary = True
    dtd_external_ref = True

    def parse(self, xmlfile, **kwargs):
        with io.StringIO() as result:
            handler = XMLGenerator(result)
            self.module.parse(xmlfile, handler, **kwargs)
            return result.getvalue()

    def parseString(self, xmlstring, **kwargs):
        with io.StringIO() as result:
            handler = XMLGenerator(result)
            self.module.parseString(xmlstring, handler, **kwargs)
            return result.getvalue()

    def test_exceptions(self):
        with self.assertRaises(EntitiesForbidden) as ctx:
            self.parse(self.xml_bomb)
        msg = "EntitiesForbidden(name='a', system_id=None, public_id=None)"
        self.assertEqual(str(ctx.exception), msg)
        self.assertEqual(repr(ctx.exception), msg)

        with self.assertRaises(ExternalReferenceForbidden) as ctx:
            self.parse(self.xml_external, forbid_entities=False)
        msg = (
            "ExternalReferenceForbidden"
            "(system_id='http://www.w3schools.com/xml/note.xml', public_id=None)"
        )
        self.assertEqual(str(ctx.exception), msg)
        self.assertEqual(repr(ctx.exception), msg)

        with self.assertRaises(DTDForbidden) as ctx:
            self.parse(self.xml_bomb, forbid_dtd=True)
        msg = "DTDForbidden(name='xmlbomb', system_id=None, public_id=None)"
        self.assertEqual(str(ctx.exception), msg)
        self.assertEqual(repr(ctx.exception), msg)


@unittest.skipUnless(lxml is not None, "test requires lxml")
class TestDefusedLxml(BaseTests):
    module = lxml

    cyclic_error = getattr(lxml_etree, "XMLSyntaxError", None)

    content_binary = True

    def parse(self, xmlfile, **kwargs):
        try:
            tree = self.module.parse(xmlfile, **kwargs)
        except lxml_etree.XMLSyntaxError:
            self.skipTest("lxml detects entity reference loop")
        return self.module.tostring(tree)

    def parseString(self, xmlstring, **kwargs):
        try:
            tree = self.module.fromstring(xmlstring, **kwargs)
        except lxml_etree.XMLSyntaxError:
            self.skipTest("lxml detects entity reference loop")
        return self.module.tostring(tree)

    if not LXML3:

        def test_entities_forbidden(self):
            self.assertRaises(NotSupportedError, self.parse, self.xml_bomb)

        def test_dtd_with_external_ref(self):
            self.assertRaises(NotSupportedError, self.parse, self.xml_dtd)

    def test_external_ref(self):
        pass

    def test_external_file_ref(self):
        pass

    def test_restricted_element1(self):
        try:
            tree = self.module.parse(self.xml_bomb, forbid_dtd=False, forbid_entities=False)
        except lxml_etree.XMLSyntaxError:
            self.skipTest("lxml detects entityt reference loop")
        root = tree.getroot()
        self.assertEqual(root.text, None)

        self.assertEqual(list(root), [])
        self.assertEqual(root.getchildren(), [])
        self.assertEqual(list(root.iter()), [root])
        self.assertEqual(list(root.iterchildren()), [])
        self.assertEqual(list(root.iterdescendants()), [])
        self.assertEqual(list(root.itersiblings()), [])
        self.assertEqual(list(root.getiterator()), [root])
        self.assertEqual(root.getnext(), None)

    def test_restricted_element2(self):
        try:
            tree = self.module.parse(self.xml_bomb2, forbid_dtd=False, forbid_entities=False)
        except lxml_etree.XMLSyntaxError:
            self.skipTest("lxml detects entityt reference loop")
        root = tree.getroot()
        bomb, tag = root
        self.assertEqual(root.text, "text")

        self.assertEqual(list(root), [bomb, tag])
        self.assertEqual(root.getchildren(), [bomb, tag])
        self.assertEqual(list(root.iter()), [root, bomb, tag])
        self.assertEqual(list(root.iterchildren()), [bomb, tag])
        self.assertEqual(list(root.iterdescendants()), [bomb, tag])
        self.assertEqual(list(root.itersiblings()), [])
        self.assertEqual(list(root.getiterator()), [root, bomb, tag])
        self.assertEqual(root.getnext(), None)
        self.assertEqual(root.getprevious(), None)

        self.assertEqual(list(bomb.itersiblings()), [tag])
        self.assertEqual(bomb.getnext(), tag)
        self.assertEqual(bomb.getprevious(), None)
        self.assertEqual(tag.getnext(), None)
        self.assertEqual(tag.getprevious(), bomb)

    def test_xpath_injection(self):
        # show XPath injection vulnerability
        xml = """<root><tag id="one" /><tag id="two"/></root>"""
        expr = "one' or @id='two"
        root = lxml.fromstring(xml)

        # insecure way
        xp = "tag[@id='%s']" % expr
        elements = root.xpath(xp)
        self.assertEqual(len(elements), 2)
        self.assertEqual(elements, list(root))

        # proper and safe way
        xp = "tag[@id=$idname]"
        elements = root.xpath(xp, idname=expr)
        self.assertEqual(len(elements), 0)
        self.assertEqual(elements, [])

        elements = root.xpath(xp, idname="one")
        self.assertEqual(len(elements), 1)
        self.assertEqual(elements, list(root)[:1])

    def test_lxml_warnings(self):
        self.assertTrue(lxml_warnings)
        self.assertEqual(lxml_warnings[0].category, DeprecationWarning)
        self.assertIn("tests.py", lxml_warnings[0].filename)

    def test_lxml_schema_include(self):
        # attempt to trigger network ops and error
        with mock.patch.dict(os.environ):
            os.environ.pop("no_proxy", None)
            os.environ["http_proxy"] = "http://proxy.invalid:3128"
            os.environ["https_proxy"] = "http://proxy.invalid:3128"

            doc = self.module.fromstring("<root>true</root>")

            schema = lxml_etree.XMLSchema(file=self.xml_schema_include)
            schema.validate(doc)

            schema_etree = self.module.parse(self.xml_schema_include)
            lxml_etree.XMLSchema(etree=schema_etree)
            schema.validate(doc)


class XmlRpcTarget(object):
    def __init__(self):
        self._data = []

    def __str__(self):
        return "".join(self._data)

    def xml(self, encoding, standalone):
        pass

    def start(self, tag, attrs):
        self._data.append("<%s>" % tag)

    def data(self, text):
        self._data.append(text)

    def end(self, tag):
        self._data.append("</%s>" % tag)


class TestXmlRpc(DefusedTestCase):
    module = xmlrpc

    def parse(self, xmlfile, **kwargs):
        target = XmlRpcTarget()
        parser = self.module.DefusedExpatParser(target, **kwargs)
        data = self.get_content(xmlfile)
        parser.feed(data)
        parser.close()
        return target

    def parse_unpatched(self, xmlfile):
        target = XmlRpcTarget()
        parser = self.module.ExpatParser(target)
        data = self.get_content(xmlfile)
        parser.feed(data)
        parser.close()
        return target

    def test_xmlrpc(self):
        self.assertRaises(EntitiesForbidden, self.parse, self.xml_bomb)
        self.assertRaises(EntitiesForbidden, self.parse, self.xml_quadratic)
        self.parse(self.xml_dtd)
        self.assertRaises(DTDForbidden, self.parse, self.xml_dtd, forbid_dtd=True)

    # def test_xmlrpc_unpatched(self):
    #    for fname in (self.xml_external,  self.xml_dtd):
    #        print(self.parse_unpatched(fname))

    def test_monkeypatch(self):
        try:
            xmlrpc.monkey_patch()
        finally:
            xmlrpc.unmonkey_patch()


@unittest.skipUnless(gzip is not None, "test requires gzip")
class TestDefusedGzip(DefusedTestCase):
    def get_gzipped(self, length):
        f = io.BytesIO()
        self.addCleanup(f.close)
        gzf = gzip.GzipFile(mode="wb", fileobj=f)
        gzf.write(b"d" * length)
        gzf.close()
        f.seek(0)
        return f

    def decode_response(self, response, limit=None, readlength=1024):
        dec = xmlrpc.DefusedGzipDecodedResponse(response, limit)
        acc = []
        while True:
            data = dec.read(readlength)
            if not data:
                break
            acc.append(data)
        return b"".join(acc)

    def test_defused_gzip_decode(self):
        data = self.get_gzipped(4096).getvalue()
        result = xmlrpc.defused_gzip_decode(data)
        self.assertEqual(result, b"d" * 4096)
        result = xmlrpc.defused_gzip_decode(data, -1)
        self.assertEqual(result, b"d" * 4096)
        result = xmlrpc.defused_gzip_decode(data, 4096)
        self.assertEqual(result, b"d" * 4096)
        with self.assertRaises(ValueError):
            result = xmlrpc.defused_gzip_decode(data, 4095)
        with self.assertRaises(ValueError):
            result = xmlrpc.defused_gzip_decode(data, 0)

    def test_defused_gzip_response(self):
        clen = len(self.get_gzipped(4096).getvalue())

        response = self.get_gzipped(4096)
        data = self.decode_response(response)
        self.assertEqual(data, b"d" * 4096)

        with self.assertRaises(ValueError):
            response = self.get_gzipped(4096)
            xmlrpc.DefusedGzipDecodedResponse(response, clen - 1)

        with self.assertRaises(ValueError):
            response = self.get_gzipped(4096)
            self.decode_response(response, 4095)

        with self.assertRaises(ValueError):
            response = self.get_gzipped(4096)
            self.decode_response(response, 4095, 8192)


class TestDefusingScope(DefusedTestCase):
    """Scoped, reversible process-global monkey patching."""

    def setUp(self):
        # make sure no scope leaks between tests
        self.assertEqual(_active_scopes, [])
        self._snapshot = self._snapshot_targets()

    def tearDown(self):
        # every test must leave the stdlib exactly as it found it
        self._assert_restored(self._snapshot)
        self.assertEqual(_active_scopes, [])

    def _snapshot_targets(self):
        snapshot = {}
        for stdlib_mod, name, replacement in _iter_targets():
            snapshot[(stdlib_mod.__name__, name)] = getattr(
                stdlib_mod, name, _MISSING
            )
        return snapshot

    def _assert_restored(self, snapshot):
        for (module_name, name), original in snapshot.items():
            stdlib_mod = sys.modules[module_name]
            current = getattr(stdlib_mod, name, _MISSING)
            self.assertIs(
                current,
                original,
                "{}.{} was not restored to its original object".format(
                    module_name, name
                ),
            )

    def _assert_all_patched(self, scope):
        for stdlib_mod, name, replacement in _iter_targets():
            self.assertIs(
                getattr(stdlib_mod, name),
                replacement,
                "{}.{} was not replaced with its defused object".format(
                    stdlib_mod.__name__, name
                ),
            )
        self.assertEqual(len(scope._snapshots), len(list(_iter_targets())))

    def test_scope_patches_and_restores_by_identity(self):
        scope = DefusingScope()
        self.assertFalse(scope.active)
        with scope:
            self.assertTrue(scope.active)
            self.assertIs(_active_scopes[-1], scope)
            self._assert_all_patched(scope)

            # the entity declaration sample is rejected while defused
            with open(self.xml_bomb, "rb") as f:
                bomb_bytes = f.read()
            self.assertRaises(
                EntitiesForbidden, stdlib_etree.fromstring, bomb_bytes
            )
            self.assertRaises(
                EntitiesForbidden, stdlib_minidom.parseString, bomb_bytes
            )

        self.assertFalse(scope.active)
        # normal parsing works again after restoration
        root = stdlib_etree.fromstring(bomb_bytes)
        self.assertEqual(len(root.text), 640)
        doc = stdlib_minidom.parseString(bomb_bytes)
        self.assertEqual(doc.documentElement.tagName, "bomb")

    def test_nested_scopes_keep_outer_protection(self):
        outer = DefusingScope()
        inner = DefusingScope()
        with outer:
            outer_etree_parse = stdlib_etree.parse
            with open(self.xml_bomb, "rb") as f:
                bomb_bytes = f.read()
            self.assertRaises(
                EntitiesForbidden, stdlib_etree.fromstring, bomb_bytes
            )
            with inner:
                self.assertEqual(_active_scopes, [outer, inner])
                self.assertRaises(
                    EntitiesForbidden, stdlib_etree.fromstring, bomb_bytes
                )
            # inner exit must not strip the outer scope's protection
            self.assertTrue(outer.active)
            self.assertIs(stdlib_etree.parse, outer_etree_parse)
            self.assertIs(stdlib_etree.parse, ElementTree.parse)
            self.assertRaises(
                EntitiesForbidden, stdlib_etree.fromstring, bomb_bytes
            )
            self.assertEqual(_active_scopes, [outer])
        # outer exit restores the original objects
        self.assertIsNot(stdlib_etree.parse, ElementTree.parse)

    def test_exception_in_body_still_restores(self):
        scope = DefusingScope()
        original_parse = stdlib_etree.parse
        with self.assertRaises(RuntimeError):
            with scope:
                patched_parse = stdlib_etree.parse
                self.assertIs(patched_parse, ElementTree.parse)
                raise RuntimeError("boom")
        self.assertFalse(scope.active)
        self.assertIs(stdlib_etree.parse, original_parse)
        self.assertEqual(scope.conflicts, [])

    def test_conflict_raises_and_keeps_third_party_object(self):
        scope = DefusingScope()
        third_party = lambda *args, **kwargs: "third-party parser"
        with self.assertRaises(ScopeConflictError) as ctx:
            with scope:
                stdlib_etree.parse = third_party
        conflict = scope.conflicts
        self.assertEqual(len(conflict), 1)
        record = conflict[0]
        self.assertEqual(record.module_name, "xml.etree.ElementTree")
        self.assertEqual(record.attribute, "parse")
        self.assertIs(record.replacement, ElementTree.parse)
        self.assertIs(record.current, third_party)
        # the conflicting object must not be overwritten with the snapshot
        self.assertIs(stdlib_etree.parse, third_party)
        self.assertIs(ctx.exception.conflicts, conflict)
        # clean up the third party change, then restoration must be complete
        stdlib_etree.parse = record.original
        self._assert_restored(self._snapshot)

    def test_conflict_warn_mode_preserves_other_restorations(self):
        scope = DefusingScope(on_conflict="warn")
        third_party = lambda *args, **kwargs: "third-party gzip"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with scope:
                stdlib_xmlrpc_client.gzip_decode = third_party
        scope_warnings = [w for w in caught if issubclass(w.category, ScopeConflictWarning)]
        self.assertEqual(len(scope_warnings), 1)
        self.assertEqual(len(scope.conflicts), 1)
        record = scope.conflicts[0]
        self.assertEqual(
            (record.module_name, record.attribute),
            ("xmlrpc.client", "gzip_decode"),
        )
        self.assertIs(record.current, third_party)
        # conflicting target left alone ...
        self.assertIs(stdlib_xmlrpc_client.gzip_decode, third_party)
        # ... while every uncontested target is fully restored
        stdlib_xmlrpc_client.gzip_decode = record.original
        self._assert_restored(self._snapshot)

    def test_raise_on_conflict_does_not_mask_body_exception(self):
        scope = DefusingScope()
        third_party = lambda *args, **kwargs: "third-party parser"
        with self.assertRaises(RuntimeError):
            with scope:
                stdlib_etree.parse = third_party
                raise RuntimeError("body error wins")
        # conflict information stays available even though no error was raised
        self.assertEqual(len(scope.conflicts), 1)
        self.assertIs(stdlib_etree.parse, third_party)
        stdlib_etree.parse = scope.conflicts[0].original

    def test_invalid_on_conflict(self):
        self.assertRaises(ValueError, DefusingScope, on_conflict="explode")

    def test_enter_and_exit_explicitly(self):
        scope = DefusingScope()
        self.assertRaises(RuntimeError, scope.exit)
        scope.enter()
        try:
            self.assertTrue(scope.active)
            self.assertIs(stdlib_xmlrpc_client.FastParser, xmlrpc.DefusedExpatParser)
        finally:
            scope.exit()
        self.assertFalse(scope.active)
        self.assertRaises(RuntimeError, scope.exit)

    def test_xmlrpc_targets_are_scoped(self):
        original_fast = stdlib_xmlrpc_client.FastParser
        original_gzip = stdlib_xmlrpc_client.gzip_decode
        original_response = stdlib_xmlrpc_client.GzipDecodedResponse
        with DefusingScope():
            self.assertIs(
                stdlib_xmlrpc_client.FastParser, xmlrpc.DefusedExpatParser
            )
            self.assertIs(
                stdlib_xmlrpc_client.gzip_decode, xmlrpc.defused_gzip_decode
            )
            self.assertIs(
                stdlib_xmlrpc_client.GzipDecodedResponse,
                xmlrpc.DefusedGzipDecodedResponse,
            )
            import xmlrpc.server as stdlib_xmlrpc_server

            self.assertIs(
                stdlib_xmlrpc_server.gzip_decode, xmlrpc.defused_gzip_decode
            )
        self.assertIs(stdlib_xmlrpc_client.FastParser, original_fast)
        self.assertIs(stdlib_xmlrpc_client.gzip_decode, original_gzip)
        self.assertIs(
            stdlib_xmlrpc_client.GzipDecodedResponse, original_response
        )

    def test_scope_factory_returns_scope(self):
        from defusedxml import defusing_scope as factory

        scope = factory()
        self.assertIsInstance(scope, DefusingScope)
        with scope:
            self.assertIs(stdlib_etree.XMLParser, ElementTree.DefusedXMLParser)


class TestPermanentDefuseStdlib(DefusedTestCase):
    """The legacy permanent monkey patch must keep working and be restorable."""

    def test_defuse_stdlib_is_permanent_and_restorable_via_scope_identity(self):
        snapshot = {}
        for stdlib_mod, name, replacement in _iter_targets():
            snapshot[(stdlib_mod, name)] = getattr(stdlib_mod, name, _MISSING)
        try:
            result = defuse_stdlib()
            self.assertIn(xmlrpc, result)
            for stdlib_mod, name, replacement in _iter_targets():
                self.assertIs(getattr(stdlib_mod, name), replacement)
            with open(self.xml_bomb, "rb") as f:
                bomb_bytes = f.read()
            self.assertRaises(
                EntitiesForbidden, stdlib_etree.fromstring, bomb_bytes
            )
        finally:
            for (stdlib_mod, name), original in snapshot.items():
                if original is _MISSING:
                    delattr(stdlib_mod, name)
                else:
                    setattr(stdlib_mod, name, original)
        # ordinary parsing works again after manual restoration
        root = stdlib_etree.fromstring(bomb_bytes)
        self.assertEqual(len(root.text), 640)


def test_main():
    suite = unittest.TestSuite()
    cls = [
        TestDefusedElementTree,
        TestDefusedcElementTree,
        TestDefusedMinidom,
        TestDefusedMinidomWithParser,
        TestDefusedPulldom,
        TestDefusedSax,
        TestDefusedLxml,
        TestXmlRpc,
        TestDefusedGzip,
        TestDefusingScope,
        TestPermanentDefuseStdlib,
    ]
    for c in cls:
        suite.addTest(unittest.defaultTestLoader.loadTestsFromTestCase(c))
    return suite


if __name__ == "__main__":
    suite = test_main()
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    # TODO: test that it actually works
    defuse_stdlib()
    sys.exit(not result.wasSuccessful())
