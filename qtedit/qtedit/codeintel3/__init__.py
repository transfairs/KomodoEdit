#!python
# ***** BEGIN LICENSE BLOCK *****
# Version: MPL 1.1/GPL 2.0/LGPL 2.1
# 
# The contents of this file are subject to the Mozilla Public License
# Version 1.1 (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://www.mozilla.org/MPL/
# 
# Software distributed under the License is distributed on an "AS IS"
# basis, WITHOUT WARRANTY OF ANY KIND, either express or implied. See the
# License for the specific language governing rights and limitations
# under the License.
# 
# The Original Code is Komodo code.
# 
# The Initial Developer of the Original Code is ActiveState Software Inc.
# Portions created by ActiveState Software Inc are Copyright (C) 2000-2007
# ActiveState Software Inc. All Rights Reserved.
# 
# Contributor(s):
#   ActiveState Software Inc
# 
# Alternatively, the contents of this file may be used under the terms of
# either the GNU General Public License Version 2 or later (the "GPL"), or
# the GNU Lesser General Public License Version 2.1 or later (the "LGPL"),
# in which case the provisions of the GPL or the LGPL are applicable instead
# of those above. If you wish to allow use of your version of this file only
# under the terms of either the GPL or the LGPL, and not to allow others to
# use your version of this file under the terms of the MPL, indicate your
# decision by deleting the provisions above and replace them with the notice
# and other provisions required by the GPL or the LGPL. If you do not delete
# the provisions above, a recipient may use your version of this file under
# the terms of any one of the MPL, the GPL or the LGPL.
# 
# ***** END LICENSE BLOCK *****

"""Get and manage Code Intelligence data about source code of many languages.

The Code Intelligence system is one for generating and managing code
structure information on given source code. See the spec for more details:
    http://specs.tl.activestate.com/kd/kd-0100.html

General Usage
-------------

    from codeintel3.manager import Manager
    mgr = Manager()
    # Alternatively use Database upgrade methods directly for finer control.
    mgr.upgrade()
    mgr.initialize()
    try:
        # Get a Buffer object from a scimoz/path/content.
        buf = mgr.buf_from_*(...)
        
        # Use the buffer's API to do codeintel-y stuff. For example:
        # - See if you are at a trigger point.
        trg = buf.trg_from_pos(...)

        # - Get completions at that trigger. See also
        #   Buffer.async_eval_at_trg(), Buffer.calltips_from_trg().
        cplns = buf.cplns_from_trg(trg, ...)

        # ...
    finally:
        mgr.finalize() # make sure this gets run on your could get hangs
"""

import sys


def _patch_elementtree():
    """Add the `.names`/`.cache` Element attributes that the rest of
    codeintel3 relies on everywhere (blob.names[...], elem.cache[...]).

    The original codeintel2 engine got these from Komodo's own patched
    "ciElementTree" C extension (see
    src/codeintel/src/patches/ciElementTree-2-names.patch and
    ciElementTree-4-cache.patch) -- a fork of cElementTree with two extra
    fields bolted onto the C struct. That extension has no Python 3 build
    (same situation as SilverCity), so this re-implements just those two
    attributes in pure Python instead of porting the C extension.

    `.names` is a read-only view: a dict of {child's "name" attrib: child
    element} for direct children that have a "name" attribute. The C
    original lazily cached this and invalidated the cache on structural
    mutation; every real call site in this codebase only *reads* it
    (`in`, `[key]`, `.get()`, `.items()`), so recomputing on each access
    is simpler and avoids any staleness risk.

    `.cache` is a plain, persistent per-element dict for ad hoc caching
    (e.g. database.py/catalog.py stash a "lpaths" entry in it) -- unlike
    `.names` this one *is* written to and must return the same dict
    object on every access.

    Requires the pure-Python Element implementation (mutable instance
    __dict__) rather than the C-accelerated `_elementtree.Element` type,
    which cannot have new attributes added to it. `sys.modules["_elementtree"]
    = None` blocks that accelerator the same way CPython's own test suite
    does, forcing xml.etree.ElementTree's own `except ImportError: pass`
    fallback to the pure-Python classes.
    """
    import xml.etree.ElementTree as ET

    if getattr(ET, "_patched_for_komodo_", False):
        return

    probe = ET.Element("x")
    if not hasattr(probe, "__dict__"):
        # The C accelerator is in use; force a fresh, pure-Python import.
        sys.modules["_elementtree"] = None
        sys.modules.pop("xml.etree.ElementTree", None)
        sys.modules.pop("xml.etree.cElementTree", None)
        import xml.etree.ElementTree as ET

    def _names(self):
        result = {}
        for child in self:
            name = child.attrib.get("name")
            if name is not None:
                result[name] = child
        return result

    def _cache(self):
        cache = self.__dict__.get("_ci_cache_store")
        if cache is None:
            cache = {}
            self.__dict__["_ci_cache_store"] = cache
        return cache

    ET.Element.names = property(_names)
    ET.Element.cache = property(_cache)
    ET._patched_for_komodo_ = True


_patch_elementtree()
del sys

