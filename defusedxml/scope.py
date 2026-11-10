# defusedxml
#
# Copyright (c) 2023 by Christian Heimes <christian@python.org>
# Licensed to PSF under a Contributor Agreement.
# See https://www.python.org/psf/license for licensing details.
"""Scoped, reversible monkey patching of the XML stdlib

The :class:`DefusingScope` context manager applies the same monkey patches as
:func:`defusedxml.defuse_stdlib` (including ``xmlrpc``) for the duration of a
``with`` block and restores the previous state on exit.

.. warning::

    Entering a scope modifies process-global module attributes. The change is
    visible to every thread in the process and is *not* a per-thread security
    policy. Nested ``with`` blocks are supported, but concurrent scopes in
    different threads are not.
"""
from __future__ import print_function, absolute_import

import sys
import threading
import warnings

from . import xmlrpc

# module-level stack of all currently entered scopes, outermost first
_active_scopes = []
# serializes enter/exit so the global state and the scope stack stay consistent
_state_lock = threading.RLock()

# how the scope reacts when a target attribute was changed behind its back
_ON_CONFLICT = ("raise", "warn")

# sentinel marking an attribute that did not exist when the scope was entered
_MISSING = object()


class ScopeConflictError(RuntimeError):
    """A target was modified by other code while a scope was active.

    The scope refuses to restore its own snapshot blindly, because doing so
    would overwrite the conflicting change. Inspect ``conflicts`` (or
    :attr:`DefusingScope.conflicts`) for the details.
    """

    def __init__(self, conflicts):
        self.conflicts = conflicts
        details = ", ".join(
            "{}.{}".format(conflict.module_name, conflict.attribute)
            for conflict in conflicts
        )
        super().__init__(
            "conflicting modification of patched stdlib target(s): {}".format(details)
        )


class ScopeConflictWarning(UserWarning):
    """A target was modified by other code while a scope was active."""


class ScopeConflict(object):
    """Record of a conflicting modification detected on scope exit.

    Attributes:
        module_name: dotted name of the stdlib module that owns the attribute.
        attribute: name of the attribute that was changed.
        original: object found at the attribute when the scope was entered.
        replacement: defused object the scope installed at the attribute.
        current: object found at the attribute when the conflict was detected.
    """

    __slots__ = ("module_name", "attribute", "original", "replacement", "current")

    def __init__(self, module_name, attribute, original, replacement, current):
        self.module_name = module_name
        self.attribute = attribute
        self.original = original
        self.replacement = replacement
        self.current = current

    def __repr__(self):
        return (
            "ScopeConflict(module_name={!r}, attribute={!r}, original={!r}, "
            "replacement={!r}, current={!r})".format(
                self.module_name,
                self.attribute,
                self.original,
                self.replacement,
                self.current,
            )
        )


def _iter_targets():
    """Yield ``(stdlib_module, attribute_name, replacement)`` patch targets.

    Covers every stdlib module that :func:`defusedxml.defuse_stdlib` patches
    plus the four ``xmlrpc`` attributes handled by
    :func:`defusedxml.xmlrpc.monkey_patch`.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, module="defusedxml")
        from . import cElementTree
    from . import ElementTree
    from . import expatbuilder
    from . import expatreader
    from . import minidom
    from . import pulldom
    from . import sax

    defused_mods = [
        cElementTree,
        ElementTree,
        minidom,
        pulldom,
        sax,
        expatbuilder,
        expatreader,
    ]

    for defused_mod in defused_mods:
        stdlib_name = defused_mod.__origin__
        __import__(stdlib_name, {}, {}, ["*"])
        stdlib_mod = sys.modules[stdlib_name]
        stdlib_names = set(dir(stdlib_mod))
        for name, replacement in vars(defused_mod).items():
            if name.startswith("_") or name not in stdlib_names:
                continue
            yield stdlib_mod, name, replacement

    xmlrpc_modules = [xmlrpc.xmlrpc_client]
    if xmlrpc.xmlrpc_server is not None:
        xmlrpc_modules.append(xmlrpc.xmlrpc_server)
    xmlrpc_targets = {
        "FastParser": xmlrpc.DefusedExpatParser,
        "GzipDecodedResponse": xmlrpc.DefusedGzipDecodedResponse,
        "gzip_decode": xmlrpc.defused_gzip_decode,
    }
    for stdlib_mod in xmlrpc_modules:
        for name, replacement in xmlrpc_targets.items():
            # xmlrpc.server only carries gzip_decode
            if not hasattr(stdlib_mod, name):
                continue
            yield stdlib_mod, name, replacement


class DefusingScope(object):
    """Process-global, reversible monkey patch for the XML stdlib.

    Entering the scope replaces the parsing-related attributes of the XML
    stdlib modules (including ``xmlrpc.client`` and ``xmlrpc.server``) with
    their defused counterparts. Exiting the scope restores the exact objects
    that were present on entry. Both normal and exception-driven exits run the
    restoration.

    The patch is a *process-global* modification: patched module attributes are
    shared by every thread in the process. This class does not provide
    thread-local or per-thread protection and must not be used as such.

    Nested scopes are supported. An inner scope records the state it inherits
    (which may already be defused by an outer scope) and restores exactly that
    state, so leaving the inner scope never removes protection that an outer
    scope still relies on.

    If other code modifies one of the patched attributes while the scope is
    active, the scope detects the conflict through object identity instead of
    blindly writing its old snapshot back. The conflict is recorded with the
    original, replacement and current objects for later investigation:

    * ``on_conflict="raise"`` (the default) raises :class:`ScopeConflictError`
      after restoring every uncontested attribute.
    * ``on_conflict="warn"`` leaves the conflicting attribute untouched and
      issues a :class:`ScopeConflictWarning` instead.

    Typical usage::

        from defusedxml.scope import DefusingScope

        with DefusingScope():
            # stdlib XML parsers are defused in here, process-wide
            ...
        # previous state is restored here

    The object can also be driven explicitly with :meth:`enter` and
    :meth:`exit` when a ``with`` statement is not practical.
    """

    def __init__(self, on_conflict="raise"):
        if on_conflict not in _ON_CONFLICT:
            raise ValueError(
                "on_conflict must be one of {}, got {!r}".format(
                    _ON_CONFLICT, on_conflict
                )
            )
        self.on_conflict = on_conflict
        # list of (stdlib_module, attribute, original_object, replacement)
        self._snapshots = []
        # ScopeConflict records gathered on exit
        self.conflicts = []
        self._active = False

    @property
    def active(self):
        """Whether the scope is currently entered."""
        return self._active

    def enter(self):
        """Enter the scope and install the defused objects.

        Saves the identity of every target attribute before replacing it and
        pushes the scope onto the global nesting stack.
        """
        with _state_lock:
            if self._active:
                raise RuntimeError("DefusingScope is already active")
            snapshots = []
            for stdlib_mod, name, replacement in _iter_targets():
                original = getattr(stdlib_mod, name, _MISSING)
                snapshots.append((stdlib_mod, name, original, replacement))
                setattr(stdlib_mod, name, replacement)
            self._snapshots = snapshots
            self._active = True
            _active_scopes.append(self)
        return self

    def exit(self):
        """Leave the scope and restore this scope's own changes.

        Restores each target to the object it held when the scope was entered,
        provided the attribute still holds the scope's replacement. Targets
        changed by other code are left in place and reported as conflicts.
        """
        with _state_lock:
            if not self._active:
                raise RuntimeError("DefusingScope is not active")
            conflicts = []
            for stdlib_mod, name, original, replacement in self._snapshots:
                current = getattr(stdlib_mod, name, _MISSING)
                if current is replacement:
                    if original is _MISSING:
                        delattr(stdlib_mod, name)
                    else:
                        setattr(stdlib_mod, name, original)
                else:
                    conflicts.append(
                        ScopeConflict(
                            stdlib_mod.__name__, name, original, replacement, current
                        )
                    )
            self.conflicts = conflicts
            self._snapshots = []
            self._active = False
            try:
                _active_scopes.remove(self)
            except ValueError:  # pragma: no cover - stack bookkeeping
                raise RuntimeError("DefusingScope was not found in the active stack")

        if conflicts:
            if self.on_conflict == "raise":
                raise ScopeConflictError(conflicts)
            warnings.warn(
                "{} stdlib target(s) were modified while the scope was "
                "active; the conflicting values were kept. See "
                "DefusingScope.conflicts for details.".format(len(conflicts)),
                ScopeConflictWarning,
                stacklevel=2,
            )
        return conflicts

    def __enter__(self):
        return self.enter()

    def __exit__(self, exc_type, exc_value, traceback):
        # Restoration must run even when the body raised. A conflict is
        # reported but never masks an exception from the body.
        try:
            self.exit()
        except ScopeConflictError:
            if exc_type is not None:
                # retain the original exception; conflict info is still
                # available on self.conflicts
                return False
            raise
        return False


def defusing_scope(on_conflict="raise"):
    """Create a :class:`DefusingScope` instance.

    Convenience factory mirroring the naming of ``defuse_stdlib()``::

        from defusedxml.scope import defusing_scope

        with defusing_scope():
            ...
    """
    return DefusingScope(on_conflict=on_conflict)


__all__ = [
    "DefusingScope",
    "ScopeConflict",
    "ScopeConflictError",
    "ScopeConflictWarning",
    "defusing_scope",
]
