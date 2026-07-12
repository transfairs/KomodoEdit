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
# Activestate Tool Corp.
# Portions created by the Initial Developer are Copyright (C) 2000
# the Initial Developer. All Rights Reserved.
#
# Contributor(s):
#    Mark Hammond <MarkH@ActiveState.com>
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

import xpcom
import xpcom.nsError
import xpcom.client
import xpcom.server
import xpcom._xpcom
import xpcom.components
import string
from pyxpcom_test_tools import testmain

import unittest

import traceback, getopt, sys

verbose_level = 0

reportedSampleMissing = 0

def get_sample_component_cpp():
    global reportedSampleMissing
    contractid = "@mozilla.org/sample;1" # The C++ version.
    try:
        return xpcom.components.classes[contractid].createInstance()
    except xpcom.COMException:
        if not reportedSampleMissing:
            print "***"
            print "*** This test requires an XPCOM sample component,"
            print "*** which does not exist.  To build this test, you"
            print "*** should change to the 'mozilla/xpcom/sample' directory,"
            print "*** and run 'make', then run this test again."
            print "***"
            reportedSampleMissing = 1
        else:
            print "(skipping - no C++ sample...) ",
        return None

def get_sample_component_js():
    # This should *always* exist - no special make process.
    contractid = "@mozilla.org/jssample;1" # the JS version
    return xpcom.components.classes[contractid].createInstance()

def get_sample_component_any():
    return get_sample_component_cpp() or get_sample_component_js()
    
class TestDumpInterfaces(unittest.TestCase):
    def testAllInterfaces(self):
        "Dump every interface under the sun!"
        import xpcom, xpcom.xpt, xpcom._xpcom
        iim = xpcom._xpcom.XPTI_GetInterfaceInfoManager()
    
        if verbose_level:
            print "Dumping every interface I can find"
        for num, iid in enumerate(iim.GetScriptableInterfaces().values()):
            if verbose_level:
                iface = xpcom.xpt.Interface(iid)
                print iface.Describe()
        if num < 200:
            print "Only found", num, "interfaces - this seems unusually low!"
        elif verbose_level:
            print "Found", num, "interfaces"

class TestEnumContractIDs(unittest.TestCase):
    def testContractIDs(self):
        """Enumerate all the ContractIDs registered"""
        enum = xpcom.components.registrar.enumerateContractIDs()
        n = 0
        while enum.hasMoreElements():
            item = enum.getNext(xpcom.components.interfaces.nsISupportsCString)
            n = n + 1
            if verbose_level:
                print "ContractID:", item.data
        if n < 200:
            print "Only found", n, "ContractIDs - this seems unusually low!"

class TestSampleComponent(unittest.TestCase):
    def _doTestSampleComponent(self, test_flat = 0):
        """Test the standard Netscape 'sample' sample"""
        initial_value = "initial_value"
        c = get_sample_component_cpp()
        if c is None:
            # try the JS version instead, so that at least we test _something_
            c = get_sample_component_js()
            initial_value = "<default value>"
            test_flat = False # JS doesn't implement classinfo
        if not test_flat:
            c = c.queryInterface(xpcom.components.interfaces.nsISample)
        self.failUnlessEqual(c.value, initial_value)
        c.value = "new value"
        self.failUnlessEqual(c.value, "new value")
        c.poke("poked value")
        self.failUnlessEqual(c.value, "poked value")
        c.writeValue("Python just poked:")

    def testSampleComponentFlat(self):
        """Test the standard Netscape 'sample' sample using interface flattening"""
        self._doTestSampleComponent(1)

    def testSampleComponentOld(self):
        """Test the standard Netscape 'sample' sample using explicit QI"""
        self._doTestSampleComponent(0)
    
    def _doTestHash(self, c):
        "Test that hashing COM objects works"
        d = {}
        d[c] = None
        if not d.has_key(c):
            raise RuntimeError, "Can't get the exact same object back!"
        if not d.has_key(c.queryInterface(xpcom.components.interfaces.nsISupports)):
            raise RuntimeError, "Can't get back as nsISupports"

        # And the same in reverse - stick an nsISupports in, and make sure an explicit interface comes back.
        d = {}
#        contractid = "@mozilla.org/sample;1" # The C++ version.
#        c = xpcom.components.classes[contractid].createInstance() \
#            .queryInterface(xpcom.components.interfaces.nsISupports)
        d[c] = None
        if not d.has_key(c):
            raise RuntimeError, "Can't get the exact same object back!"
        if not d.has_key(c.queryInterface(xpcom.components.interfaces.nsISample)):
            raise RuntimeError, "Can't get back as nsISupports"

    def testHashJS(self):
        c = get_sample_component_js()
        self._doTestHash(c)

    def testHashCPP(self):
        c = get_sample_component_cpp()
        if c is not None:
            self._doTestHash(c)


class TestIIDs(unittest.TestCase):
    def TestIIDs(self):
        "Do some basic IID semantic tests."
        iid_str = "{7ee4bdc6-cb53-42c1-a9e4-616b8e012aba}"
        IID = xpcom._xpcom.IID
        self.failUnlessEqual(IID(iid_str), IID(iid_str))
        self.failUnlessEqual(hash(IID(iid_str)), hash(IID(iid_str)))
        self.failUnlessEqual(IID(iid_str), IID(iid_str.upper()))
        self.failUnlessEqual(hash(IID(iid_str)), hash(IID(iid_str.upper())))
        # If the above work, this shoud too, but WTF
        dict = {}
        dict[IID(iid_str)] = None
        self.failUnless(dict.has_key(IID(iid_str)), "hashes failed in dictionary")
        self.failUnless(dict.has_key(IID(iid_str.upper())), "uppercase hash failed in dictionary")

class TestRepr(unittest.TestCase):
    def _doTestRepr(self, progid, interfaces):
        if isinstance(progid, str):
            ob = xpcom.components.classes[progid].createInstance()
        else:
            ob = progid
        self.failUnless(repr(ob).find(str(progid)) >= 0, repr(ob))
        for interface_name in interfaces.split():
            self.failUnless(repr(ob).find(interface_name) >= 0, repr(ob))

    def testReprPython(self):
        "Test repr() of Python objects"
        self._doTestRepr("Python.TestComponent", "nsIPythonTestInterfaceDOMStrings nsIPythonTestInterfaceExtra nsIPythonTestInterface")

    # JS does not provide class-info :(
    #def testReprJS(self):
    #    self._doTestRepr("@mozilla.org/jssample;1", "nsISample")

    def testReprSample(self):
        "Test repr() of non-Python objects"
        ob = get_sample_component_cpp()
        if ob is None:
            ob = get_sample_component_js()
            # the JS version doesn't implement nsIClassInfo
            ob.QueryInterface(xpcom.components.interfaces.nsISample)
        self._doTestRepr(ob, "nsISample")

class TestUnwrap(unittest.TestCase):
    "Test the unwrap facilities"
    def testUnwrap(self):
        # First test that a Python object can be unwrapped.
        ob = xpcom.components.classes["Python.TestComponent"].createInstance()
        pyob = xpcom.server.UnwrapObject(ob)
        # This depends on our __repr__ implementation, but that's OK - it
        # can be updated should our __repr__ change :)
        self.failUnless(str(pyob).startswith("<component:py_test_component.PythonTestComponent"))
        # Test that a non-Python implemented object can NOT be unwrapped.
        ob = get_sample_component_any()
        if ob is None:
            return
        self.failUnlessRaises(ValueError, xpcom.server.UnwrapObject, ob)

class TestNonScriptable(unittest.TestCase):
    def testQI(self):
        # Test we can QI for a non-scriptable interface.  We can't *do* much
        # with it (other than pass it on), but we should still work and get
        # a basic wrapper.
        ob = xpcom.components.classes["Python.TestComponent"].createInstance()
        ob = ob.queryInterface(xpcom._xpcom.IID_nsIInternalPython)

class TestNoInterfaceCaching(unittest.TestCase):
    """QueryInterface failure should not cause attributes to be mapped to the
    failing interface"""

    # A bug caused a QI failure to still map attributes to that interface (which
    # the component is then known to not implement); this caused trying to use
    # any attributes with the same name to then fail in the future

    # both nsIChannel and nsILoadGruop have a .notificationCallbacks
    class DummyComponent(object):
        _com_interfaces_ = [xpcom.components.interfaces.nsIChannel]
        notificationCallbacks = None

    def testNoInterfaceCachingExplicitQI(self):
        sip = xpcom.components.classes["@mozilla.org/supports-interface-pointer;1"]\
                   .createInstance(xpcom.components.interfaces.nsISupportsInterfacePointer)
        sip.data = TestNoInterfaceCaching.DummyComponent()
        comp = sip.data
        # Check that it's on nsIChannel... (It's already there via classinfo)
        comp.QueryInterface(xpcom.components.interfaces.nsIChannel)
        self.assertIsNone(comp.notificationCallbacks)
        # QI to nsILoadGroup and fail
        with self.assertRaises(xpcom.Exception) as cm:
            comp.QueryInterface(xpcom.components.interfaces.nsILoadGroup)
        self.assertEquals(cm.exception.errno, xpcom.nsError.NS_ERROR_NO_INTERFACE)
        # Check that it's still on nsIChannel
        # (the bug caused it to look on nsILoadGroup)
        self.assertIsNone(comp.notificationCallbacks)

    def testNoInterfaceCachingViaClassInfo(self):
        sip = xpcom.components.classes["@mozilla.org/supports-interface-pointer;1"]\
                   .createInstance(xpcom.components.interfaces.nsISupportsInterfacePointer)
        sip.data = TestNoInterfaceCaching.DummyComponent()
        comp = sip.data
        # QI to nsILoadGroup and fail
        with self.assertRaises(xpcom.Exception) as cm:
            comp.QueryInterface(xpcom.components.interfaces.nsILoadGroup)
        self.assertEquals(cm.exception.errno, xpcom.nsError.NS_ERROR_NO_INTERFACE)
        # Check that it's still on nsIChannel
        # (the bug caused it to look on nsILoadGroup)
        self.assertIsNone(comp.notificationCallbacks)

class TestDirInterfaces(unittest.TestCase):
    def testDirInterface(self):
        self.assertIn("TYPE_INTERFACE_POINTER",
                      dir(xpcom.components.interfaces.nsISupportsInterfacePointer))

    def testDirComponent(self):
        sip = xpcom.components.classes["@mozilla.org/supports-interface-pointer;1"]\
                   .createInstance(xpcom.components.interfaces.nsISupportsInterfacePointer)
        self.assertIn("dataIID", dir(sip))

if __name__=='__main__':
    testmain()
