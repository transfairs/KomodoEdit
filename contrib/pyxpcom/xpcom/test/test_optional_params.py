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
#   Todd Whiteman <twhitema@gmail.com>
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
# test_optional_params.py
# Check that [optional] arguments work
#

from xpcom import components, COMException
from xpcom.server import UnwrapObject
from pyxpcom_test_tools import testmain
import unittest

class TestOptionalParams(unittest.TestCase):
    def testPythonComponent(self):
        ob = components.classes["Python.TestComponent"].createInstance()

        ob.SetOptionalNumbers(8, 100)
        self.failUnless(ob.optional_number_1 == 8)
        self.failUnless(ob.optional_number_2 == 100)
        ob.SetOptionalNumbers(5)
        self.failUnless(ob.optional_number_1 == 5)
        self.failUnless(ob.optional_number_2 == 0)
        ob.SetOptionalNumbers()
        self.failUnless(ob.optional_number_1 == 0)
        self.failUnless(ob.optional_number_2 == 0)

        ob.SetOptionalStrings("blah", "TestOptionalParams")
        self.failUnless(ob.optional_string_1 == "blah")
        self.failUnless(ob.optional_string_2 == "TestOptionalParams")
        ob.SetOptionalStrings("try2")
        self.failUnless(ob.optional_string_1 == "try2")
        self.failUnless(ob.optional_string_2 == None)
        ob.SetOptionalStrings()
        self.failUnless(ob.optional_string_1 == None)
        self.failUnless(ob.optional_string_2 == None)

        ob.SetNumbersAndOptionalStrings(7, -3, "bleat", "bloat")
        self.failUnless(ob.optional_number_1 == 7)
        self.failUnless(ob.optional_number_2 == -3)
        self.failUnless(ob.optional_string_1 == "bleat")
        self.failUnless(ob.optional_string_2 == "bloat")
        ob.SetNumbersAndOptionalStrings(77, -33, "wheat")
        self.failUnless(ob.optional_number_1 == 77)
        self.failUnless(ob.optional_number_2 == -33)
        self.failUnless(ob.optional_string_1 == "wheat")
        self.failUnless(ob.optional_string_2 == None)
        ob.SetNumbersAndOptionalStrings(777, -333)
        self.failUnless(ob.optional_number_1 == 777)
        self.failUnless(ob.optional_number_2 == -333)
        self.failUnless(ob.optional_string_1 == None)
        self.failUnless(ob.optional_string_2 == None)
        try:
            ob.SetNumbersAndOptionalStrings(1)
            self.fail("Expected an exception for not enough arguments")
        except TypeError:
            pass

        ob.SetOptionalNumbersAndStrings(8, -5, "optionals", " some stuff")
        self.failUnless(ob.optional_number_1 == 8)
        self.failUnless(ob.optional_number_2 == -5)
        self.failUnless(ob.optional_string_1 == "optionals")
        self.failUnless(ob.optional_string_2 == " some stuff")
        ob.SetOptionalNumbersAndStrings(88, -55, "forarray")
        self.failUnless(ob.optional_number_1 == 88)
        self.failUnless(ob.optional_number_2 == -55)
        self.failUnless(ob.optional_string_1 == "forarray")
        self.failUnless(ob.optional_string_2 == None)
        ob.SetOptionalNumbersAndStrings(888, -555)
        self.failUnless(ob.optional_number_1 == 888)
        self.failUnless(ob.optional_number_2 == -555)
        self.failUnless(ob.optional_string_1 == None)
        self.failUnless(ob.optional_string_2 == None)
        ob.SetOptionalNumbersAndStrings(8888)
        self.failUnless(ob.optional_number_1 == 8888)
        self.failUnless(ob.optional_number_2 == 0)
        self.failUnless(ob.optional_string_1 == None)
        self.failUnless(ob.optional_string_2 == None)
        ob.SetOptionalNumbersAndStrings()
        self.failUnless(ob.optional_number_1 == 0)
        self.failUnless(ob.optional_number_2 == 0)
        self.failUnless(ob.optional_string_1 == None)
        self.failUnless(ob.optional_string_2 == None)

if __name__=='__main__':
    testmain()
