# defusedxml
#
# Copyright (c) 2013-2020 by Christian Heimes <christian@python.org>
# Licensed to PSF under a Contributor Agreement.
# See https://www.python.org/psf/license for licensing details.
"""Common constants, exceptions and helper functions
"""
import sys
import xml.parsers.expat

PY3 = True

# Fail early when pyexpat is not installed correctly
if not hasattr(xml.parsers.expat, "ParserCreate"):
    raise ImportError("pyexpat")  # pragma: no cover


class DefusedXmlException(ValueError):
    """Base exception"""

    def __repr__(self):
        return str(self)


class DTDForbidden(DefusedXmlException):
    """Document type definition is forbidden"""

    def __init__(self, name, sysid, pubid):
        super().__init__()
        self.name = name
        self.sysid = sysid
        self.pubid = pubid

    def __str__(self):
        tpl = "DTDForbidden(name='{}', system_id={!r}, public_id={!r})"
        return tpl.format(self.name, self.sysid, self.pubid)


class EntitiesForbidden(DefusedXmlException):
    """Entity definition is forbidden"""

    def __init__(self, name, value, base, sysid, pubid, notation_name):
        super().__init__()
        self.name = name
        self.value = value
        self.base = base
        self.sysid = sysid
        self.pubid = pubid
        self.notation_name = notation_name

    def __str__(self):
        tpl = "EntitiesForbidden(name='{}', system_id={!r}, public_id={!r})"
        return tpl.format(self.name, self.sysid, self.pubid)


class ExternalReferenceForbidden(DefusedXmlException):
    """Resolving an external reference is forbidden"""

    def __init__(self, context, base, sysid, pubid):
        super().__init__()
        self.context = context
        self.base = base
        self.sysid = sysid
        self.pubid = pubid

    def __str__(self):
        tpl = "ExternalReferenceForbidden(system_id='{}', public_id={})"
        return tpl.format(self.sysid, self.pubid)


class NotSupportedError(DefusedXmlException):
    """The operation is not supported"""


class StrictParserPolicyError(DefusedXmlException):
    """A custom parser cannot be proven to honor the requested hardening policy.

    Raised in strict mode (``strict=True``) when a caller-supplied parser is
    not one of defusedxml's own hardened parsers, does not carry the requested
    policy flags, or does not have the required pyexpat handler slots
    installed. The check runs before any input is read, so an untrusted parser
    can never be used to silently downgrade the defenses.
    """

    def __init__(self, reason, parser, forbid_dtd, forbid_entities, forbid_external):
        super().__init__(reason)
        self.reason = reason
        self.parser = parser
        self.forbid_dtd = forbid_dtd
        self.forbid_entities = forbid_entities
        self.forbid_external = forbid_external

    def __str__(self):
        return (
            "StrictParserPolicyError({!r}, parser={!r}, "
            "forbid_dtd={}, forbid_entities={}, forbid_external={})".format(
                self.reason,
                type(self.parser).__name__,
                self.forbid_dtd,
                self.forbid_entities,
                self.forbid_external,
            )
        )


def _strict_policy_error(
    reason, parser, forbid_dtd, forbid_entities, forbid_external
):
    return StrictParserPolicyError(
        reason, parser, forbid_dtd, forbid_entities, forbid_external
    )


def _verify_policy_flags(parser, forbid_dtd, forbid_entities, forbid_external):
    """Check that a hardened parser's boolean flags match the requested policy.

    The flags alone are never trusted: callers must additionally prove that
    the matching pyexpat handler slots are installed.
    """
    requested = {
        "forbid_dtd": forbid_dtd,
        "forbid_entities": forbid_entities,
        "forbid_external": forbid_external,
    }
    for flag, expected in requested.items():
        # Reject missing attributes as well as mismatched ones. An object that
        # merely happens to carry same-named booleans must not be trusted.
        if getattr(parser, flag, None) is not expected:
            return _strict_policy_error(
                "parser flag {!r} is not {} as required by the strict "
                "policy".format(flag, expected),
                parser,
                forbid_dtd,
                forbid_entities,
                forbid_external,
            )
    return None


def _check_expat_slots(
    expat_parser, parser, forbid_dtd, forbid_entities, forbid_external
):
    """Verify that the hardened handlers are installed on the pyexpat parser.

    Bound methods of pyexpat compare by equality, so ``==`` is used instead of
    ``is``. This is the authoritative proof that the policy is actually in
    effect; a look-alike object with the right boolean attributes but no
    installed handlers fails here.
    """
    if forbid_dtd and (
        expat_parser.StartDoctypeDeclHandler != parser.defused_start_doctype_decl
    ):
        return _strict_policy_error(
            "parser has no StartDoctypeDeclHandler enforcing forbid_dtd",
            parser,
            forbid_dtd,
            forbid_entities,
            forbid_external,
        )
    if forbid_entities and (
        expat_parser.EntityDeclHandler != parser.defused_entity_decl
        or expat_parser.UnparsedEntityDeclHandler
        != parser.defused_unparsed_entity_decl
    ):
        return _strict_policy_error(
            "parser has no entity declaration handlers enforcing "
            "forbid_entities",
            parser,
            forbid_dtd,
            forbid_entities,
            forbid_external,
        )
    if forbid_external and (
        expat_parser.ExternalEntityRefHandler
        != parser.defused_external_entity_ref_handler
    ):
        return _strict_policy_error(
            "parser has no ExternalEntityRefHandler enforcing "
            "forbid_external",
            parser,
            forbid_dtd,
            forbid_entities,
            forbid_external,
        )
    return None


def _apply_defusing(defused_mod):
    assert defused_mod is sys.modules[defused_mod.__name__]
    stdlib_name = defused_mod.__origin__
    __import__(stdlib_name, {}, {}, ["*"])
    stdlib_mod = sys.modules[stdlib_name]
    stdlib_names = set(dir(stdlib_mod))
    for name, obj in vars(defused_mod).items():
        if name.startswith("_") or name not in stdlib_names:
            continue
        setattr(stdlib_mod, name, obj)
    return stdlib_mod
