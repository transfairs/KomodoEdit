# ***** BEGIN LICENSE BLOCK *****
# Version: MPL 1.1/GPL 2.0/LGPL 2.1
#
# The contents of this file are subject to the Mozilla Public License Version
# 1.1 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
# http://www.mozilla.org/MPL/
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License
# for the specific language governing rights and limitations under the
# License.
#
# The Original Code is the Python XPCOM language bindings.
#
# The Initial Developer of the Original Code is
# ActiveState Tool Corp.
# Portions created by the Initial Developer are Copyright (C) 2000, 2001
# the Initial Developer. All Rights Reserved.
#
# Contributor(s):
#   Mark Hammond <markh@activestate.com> (original author)
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

# test_defaultgateway.py - Test that creating the default gateway is
# re-entrant.
#
# Note: This requires a PyXPCOM DEBUG build to test properly.

from xpcom import components, _xpcom
import xpcom.server, xpcom.client
from pyxpcom_test_tools import suite_from_functions, testmain
import gc, unittest

class DummyObject(object):
    # class with a __repr__ that creates a wrapper for itself
    _com_interfaces_ = []
    def __init__(self):
        self._wrapped = False
    def __repr__(self):
        # repr() is used in debug builds for refcnt logging
        if not self._wrapped:
            self._wrapped = True # prevent infinite recursion
            sip = components.classes["@mozilla.org/supports-interface-pointer;1"]\
                            .createInstance(components.interfaces.nsISupportsInterfacePointer)
            sip.dataIID = components.interfaces.nsIRequestObserver
            sip.data = self # recursion
            # sip is dropped here, along with sip.data, to prevent reference cycle
        return "<DummyRequestObserver %08x>" % (hash(self))

class TestDefaultGateway(unittest.TestCase):
    def runTest(self):
        return self.test_defaultgateway()
    def test_defaultgateway(self):
        obj = DummyObject()
        # create the first wrapper
        sip = components.classes["@mozilla.org/supports-interface-pointer;1"]\
                        .createInstance(components.interfaces.nsISupportsInterfacePointer)
        sip.data = obj
        weak = xpcom.client.WeakReference(sip.data)
        sip.data = None
        while weak() is not None:
            # wait until the xpcom->python wrapper is destroyed
            gc.collect()
        # at this point the wrapper is dead; make a new one
        sip.data = obj

# Make this test run under our std test suite
def suite():
    return unittest.TestSuite([TestDefaultGateway()])

if __name__=='__main__':
    testmain()

# vim: set et ts=4 :
