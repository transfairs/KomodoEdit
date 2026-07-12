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
# Portions created by the Initial Developer are Copyright (C) 2011
# the Initial Developer. All Rights Reserved.
#
# Contributor(s):
#   Mook <marky+mozhg@activestate.com>
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

#
# test_rewrapping.py
# Check to make sure we always end up using the same XPCOM wrapper.
#

from xpcom import components, COMException
from xpcom.server import UnwrapObject
from pyxpcom_test_tools import testmain
import unittest

class RewrappingVictim:
    """
    This class has two interfaces; we use it to make sure when we try to use
    it as a XPCOM interface, we get the same pointer each time
    """

    _com_interfaces_ = [components.interfaces.nsIObserver,
                        components.interfaces.nsIDOMEventListener]

    def __init__(self, testcase):
        self.testcase = testcase

    def observe(self, subject, topic, data):
        somesupports = UnwrapObject(subject)

        try:
            obsvc = components.classes["@mozilla.org/observer-service;1"]\
                              .getService(components.interfaces.nsIObserverService)
            obsvc.removeObserver(self, topic)
        except COMException, e:
            somesupports.fail("Falied to remove observer: 0x%08x" %
                              (e.errno & 0xFFFFFFFF,))
            raise

        # Wrap again as a nsIDOMEventListener.
        sip = components.classes["@mozilla.org/supports-interface-pointer;1"]\
                        .createInstance(components.interfaces.nsISupportsInterfacePointer)
        sip.dataIID = components.interfaces.nsIDOMEventListener
        sip.data = self

        # Check that the hashes match.
        self.testcase.assertEqual(somesupports.last_hash, hash(sip.data))
        somesupports.notified = True
    
    def handleEvent(self, event):
        # Not actually handling an event.
        obsvc = components.classes["@mozilla.org/observer-service;1"]\
                          .getService(components.interfaces.nsIObserverService)
        obsvc.addObserver(self, "test_rewrapping", False)

class SomeSupports:
    notified = False
    last_hash = None
    _com_interfaces_ = []

class TestRewrapping(unittest.TestCase):
    def testRewrapping(self):
        # Wrap a RewrappingVictim instance in XPCOM-goop; note that we can't
        # use xpcom.server.WrapObject here because that appears to create a new
        # wrapper every time.  Note here that we're wrapping it in an interface
        # that isn't nsIObserver - it's only the secondary ones that fail.
        sip = components.classes["@mozilla.org/supports-interface-pointer;1"]\
                        .createInstance(components.interfaces.nsISupportsInterfacePointer)
        sip.dataIID = components.interfaces.nsIDOMEventListener
        sip.data = RewrappingVictim(self)
        sip.data.handleEvent(None) # actually registers an observer

        # Remember what the current wrapper looks like.
        somesupports = SomeSupports()
        somesupports.last_hash = hash(sip.data)

        # Fire the observer to do the re-wrapping checks.
        obsvc = components.classes["@mozilla.org/observer-service;1"]\
                          .getService(components.interfaces.nsIObserverService)
        obsvc.notifyObservers(somesupports, "test_rewrapping", None)

        # Make sure we actually finished the checks.
        self.assertEqual(somesupports.notified, True)

if __name__=='__main__':
    testmain()
