
#
# test_function_interface.py
# Check that [function] flags on interfaces work (i.e. that Python callables can
# be used as implementations)
#

from xpcom import components
from xpcom.server import UnwrapObject
from pyxpcom_test_tools import testmain
import unittest

class TestFunctionInterface(unittest.TestCase):
    def testFunction(self):
        class dummy(object):
            _com_interfaces_ = []

        args = []
        results = []
        def callee(subject, topic, data):
            results.extend([UnwrapObject(subject), topic, data])
        sip = components.classes["@mozilla.org/supports-interface-pointer;1"]\
                        .createInstance(components.interfaces.nsISupportsInterfacePointer)
        sip.dataIID = components.interfaces.nsIObserver
        sip.data = callee
        args = [dummy(), "hello", "world"]
        sip.data.queryInterface(components.interfaces.nsIObserver).observe(*args)
        self.assertEqual(args, results)

if __name__=='__main__':
    testmain()
