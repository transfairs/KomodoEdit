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
#        Mark Hammond <MarkH@ActiveState.com> (original author)
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

import sys, os, time, traceback
import xpcom.components
import xpcom._xpcom
import xpcom.nsError

MakeVariant = xpcom._xpcom.MakeVariant

try:
    import gc
except ImportError:
    gc = None

num_errors = 0

component_iid = xpcom.components.ID("{7EE4BDC6-CB53-42c1-A9E4-616B8E012ABA}")
new_iid = xpcom.components.ID("{2AF747D3-ECBC-457b-9AF9-5C5D80EDC360}")

contractid = "Python.TestComponent"

really_big_string = "This is really repetitive!" * 10000
really_big_wstring = u"This is really repetitive!" * 10000
extended_unicode_string = u"The Euro Symbol is '\u20ac'"

Cc = xpcom.components.classes
Ci = xpcom.components.interfaces

# Exception raised when a -ve integer is converted to an unsigned C integer
# (via an extension module).  This changed in Python 2.2, and back in 2.7
if 0x02010000 < sys.hexversion < 0x02070000 :
    UnsignedMismatchException = TypeError
else:
    UnsignedMismatchException = OverflowError

def print_error(error):
    print error
    global num_errors
    num_errors = num_errors + 1

def _test_value(what, got, expecting, expected_type = None):
    ok = got == expecting
    if type(got)==type(expecting)==type(0.0):
        ok = abs(got-expecting) < 0.001
    if not ok:
        print_error("*** Error %s - got '%r', but expecting '%r'" % (what, got, expecting))
    if expected_type is not None:
        if not isinstance(got, expected_type):
            print_error("*** Error %s - got type '%s', but expecting '%s'" % (what, type(got), expected_type))

def test_attribute(ob, attr_name, expected_init, new_value, new_value_really = None, expected_type = None):
    if xpcom.verbose:
        print "Testing attribute %s" % (attr_name,)
    if new_value_really is None:
        new_value_really = new_value # Handy for eg bools - set a BOOL to 2, you still get back 1!
        
    _test_value( "getting initial attribute value (%s)" % (attr_name,), getattr(ob, attr_name), expected_init, expected_type=expected_type)
    setattr(ob, attr_name, new_value)
    _test_value( "getting new attribute value (%s)" % (attr_name,), getattr(ob, attr_name), new_value_really, expected_type=expected_type)
    # And set it back to the expected init.
    setattr(ob, attr_name, expected_init)
    _test_value( "getting back initial attribute value after change (%s)" % (attr_name,), getattr(ob, attr_name), expected_init, expected_type=expected_type)

def test_string_attribute(ob, attr_name, expected_init, is_dumb_sz = False, ascii_only = False, expected_type = None):
    test_attribute(ob, attr_name, expected_init, "normal value", expected_type=expected_type)
    val = "a null >\0<"
    if is_dumb_sz:
        expected = "a null >" # dumb strings are \0 terminated.
    else:
        expected = val
    test_attribute(ob, attr_name, expected_init, val, expected, expected_type=expected_type)
    test_attribute(ob, attr_name, expected_init, "", expected_type=expected_type)
    test_attribute(ob, attr_name, expected_init, really_big_string, expected_type=expected_type)
    test_attribute(ob, attr_name, expected_init, u"normal unicode value", expected_type=expected_type)
    val = u"a null >\0<"
    if is_dumb_sz:
        expected = "a null >" # dumb strings are \0 terminated.
    else:
        expected = val
    test_attribute(ob, attr_name, expected_init, val, expected, expected_type=expected_type)
    test_attribute(ob, attr_name, expected_init, u"", expected_type=expected_type)
    test_attribute(ob, attr_name, expected_init, really_big_wstring, expected_type=expected_type)
    if not ascii_only:
        test_attribute(ob, attr_name, expected_init, extended_unicode_string, expected_type=expected_type)

def test_attribute_failure(ob, attr_name, new_value, expected_exception):
    try:
        setattr(ob, attr_name, new_value)
        try:
            result = "(it seems to result in '%r')" % (getattr(ob, attr_name),)
        except:
            result = "(there was an error reading it back)"
        print_error("*** Setting attribute '%s' to '%r' didn't yield an exception! %s" % (
            attr_name, new_value, result))
    except:
        exc_typ = sys.exc_info()[0]
        exc_val = sys.exc_info()[1]
        ok = issubclass(exc_typ, expected_exception)
        if not ok:
            print_error("*** Wrong exception setting '%s' to '%r'- got '%s: %s', expected '%s'" % (attr_name, new_value, exc_typ, exc_val, expected_exception))


def test_method(method, args, expected_results, expected_type = None):
    if xpcom.verbose:
        print "Testing %s%s" % (method.__name__, `args`)
    try:
        ret = method(*args)
    except Exception, ex:
        print_error("calling method %s with %r - exception:" %
                    (method.__name__, args))
        traceback.print_exc(None, sys.stdout)
    else:
        if ret != expected_results:
            print_error("calling method %s with %r - expected %r, but got %r" %
                        (method.__name__, args, expected_results, ret))
        if expected_type is not None:
            if type(ret) is not expected_type:
                print_error("calling method %s with %r - expected type %r, but got %r" %
                            (method.__name__, args, expected_type, type(ret)))
    sys.stdout.flush()

def test_int_method(meth):
    test_method(meth, (0,0), (0,0,0))
    test_method(meth, (1,1), (2,0,1))
    test_method(meth, (5,2), (7,3,10))
#    test_method(meth, (2,5), (7,-3,10))

def test_constant(ob, cname, val):
    v = getattr(ob, cname)
    if v != val:
        print_error("Bad value for constant '%s' - expected '%r' got '%r'" % (cname, val, v))
    try:
        setattr(ob, cname, 0)
        print_error("The object allowed us to set the constant '%s'" % (cname,))
    except AttributeError:
        pass

def test_base_interface(c, isJS=False):
    test_attribute(c, "boolean_value", 1, 0, expected_type=bool)
    test_attribute(c, "boolean_value", 1, -1, 1, expected_type=bool) # Set a bool to anything, you should always get back 0 or 1
    test_attribute(c, "boolean_value", 1, 4, 1, expected_type=bool) # Set a bool to anything, you should always get back 0 or 1
    test_attribute(c, "boolean_value", 1, "1", 1, expected_type=bool) # This works by virtual of PyNumber_Int - not sure I agree, but...
    test_attribute_failure(c, "boolean_value", "boo", ValueError)
    test_attribute_failure(c, "boolean_value", test_base_interface, TypeError)

    test_attribute(c, "octet_value", 2, 5, expected_type=int)
    test_attribute(c, "octet_value", 2, 0, expected_type=int)
    test_attribute(c, "octet_value", 2, 128, expected_type=int) # octet is unsigned 8 bit
    test_attribute(c, "octet_value", 2, 255, expected_type=int) # octet is unsigned 8 bit
    test_attribute_failure(c, "octet_value", 256, OverflowError) # can't fit into unsigned
    test_attribute_failure(c, "octet_value", -1, OverflowError) # can't fit into unsigned
    test_attribute_failure(c, "octet_value", "boo", ValueError)

    test_attribute(c, "short_value", 3, 10, expected_type=int)
    test_attribute(c, "short_value", 3, -1, expected_type=int) # 16 bit signed
    test_attribute(c, "short_value", 3, 0L, expected_type=int)
    test_attribute(c, "short_value", 3, 1L, expected_type=int)
    test_attribute(c, "short_value", 3, -1L, expected_type=int)
    test_attribute_failure(c, "short_value", 0xFFFF, OverflowError) # 16 bit signed
    test_attribute_failure(c, "short_value", "boo", ValueError)

    test_attribute(c, "ushort_value",  4, 5, expected_type=int)
    test_attribute(c, "ushort_value",  4, 0, expected_type=int)
    test_attribute(c, "ushort_value",  4, 0xFFFF, expected_type=int) # 16 bit signed
    test_attribute(c, "ushort_value",  4, 0L, expected_type=int)
    test_attribute(c, "ushort_value",  4, 1L, expected_type=int)
    test_attribute_failure(c, "ushort_value",  -1, OverflowError) # 16 bit signed
    test_attribute_failure(c, "ushort_value", "boo", ValueError)

    test_attribute(c, "long_value",  5, 7, expected_type=int)
    test_attribute(c, "long_value",  5, 0, expected_type=int)
    test_attribute(c, "long_value",  5, -1, -1, expected_type=int) # 32 bit signed.
    test_attribute(c, "long_value",  5, -1, expected_type=int) # 32 bit signed.
    test_attribute(c, "long_value",  5, 0L, expected_type=int)
    test_attribute(c, "long_value",  5, 1L, expected_type=int)
    test_attribute(c, "long_value",  5, -1L, expected_type=int)
    test_attribute_failure(c, "long_value", 0xFFFFL * 0xFFFF, OverflowError) # long int too long to convert
    test_attribute_failure(c, "long_value", "boo", ValueError)

    test_attribute(c, "ulong_value", 6, 7, expected_type=int)
    test_attribute(c, "ulong_value", 6, 0, expected_type=int)
    test_attribute(c, "ulong_value", 6, 0x80004004L) # should fit 32 bits on 32 bit machines
    test_attribute_failure(c, "ulong_value", -1, OverflowError) # 32 bit signed.
    test_attribute_failure(c, "ulong_value", 0x100010002L, OverflowError) # Needs 33 bits
    test_attribute_failure(c, "ulong_value", "boo", ValueError)
    
    # don't check type on long long; they are int on 64-bit systems, and long on 32-bit
    test_attribute(c, "long_long_value", 7, 8)
    test_attribute(c, "long_long_value", 7, 0)
    test_attribute(c, "long_long_value", 7, -1)
    test_attribute(c, "long_long_value", 7, 0xFFFF)
    test_attribute(c, "long_long_value", 7, 0xFFFFL * 2)
    test_attribute_failure(c, "long_long_value", 0xFFFFL * 0xFFFF * 0xFFFF * 0xFFFF, OverflowError) # long int too long to convert
    test_attribute_failure(c, "long_long_value", "boo", ValueError)
    
    test_attribute(c, "ulong_long_value", 8, 9)
    test_attribute(c, "ulong_long_value", 8, 0)
    if not isJS:
        test_attribute(c, "ulong_long_value", 8, 0x8000700060005000L) # 64-bit unsigned int should fit 64 bits
    test_attribute_failure(c, "ulong_long_value", "boo", ValueError)
    test_attribute_failure(c, "ulong_long_value", -1, UnsignedMismatchException) # can't convert negative value to unsigned long)
    test_attribute_failure(c, "ulong_long_value", 0x10001000200030004L, OverflowError) # Needs 65 bits
    
    test_attribute(c, "float_value", 9.0, 10.2, expected_type=float)
    test_attribute(c, "float_value", 9.0, 0, expected_type=float)
    test_attribute(c, "float_value", 9.0, -1, expected_type=float)
    test_attribute(c, "float_value", 9.0, 1L, expected_type=float)
    test_attribute_failure(c, "float_value", "boo", ValueError)

    test_attribute(c, "double_value", 10.0, 9.0, expected_type=float)
    test_attribute(c, "double_value", 10.0, 0, expected_type=float)
    test_attribute(c, "double_value", 10.0, -1, expected_type=float)
    test_attribute(c, "double_value", 10.0, 1L, expected_type=float)
    test_attribute_failure(c, "double_value", "boo", ValueError)
    
    test_attribute(c, "char_value", "a", "b", expected_type=str)
    test_attribute(c, "char_value", "a", "\0", expected_type=str)
    test_attribute_failure(c, "char_value", "xy", ValueError)
    test_attribute(c, "char_value", "a", u"c", expected_type=str)
    test_attribute(c, "char_value", "a", u"\0", expected_type=str)
    test_attribute_failure(c, "char_value", u"xy", ValueError)
    
    test_attribute(c, "wchar_value", "b", "a", expected_type=unicode)
    test_attribute(c, "wchar_value", "b", "\0", expected_type=unicode)
    test_attribute_failure(c, "wchar_value", "hi", ValueError)
    test_attribute(c, "wchar_value", "b", u"a", expected_type=unicode)
    test_attribute(c, "wchar_value", "b", u"\0", expected_type=unicode)
    test_attribute_failure(c, "wchar_value", u"hi", ValueError)
    
    test_string_attribute(c, "string_value", "cee", is_dumb_sz = True, ascii_only = True, expected_type=str)
    test_string_attribute(c, "wstring_value", "dee", is_dumb_sz = True, expected_type=unicode)
    test_string_attribute(c, "astring_value", "astring", expected_type=unicode)
    test_string_attribute(c, "acstring_value", "acstring", ascii_only = True, expected_type=str)

    # Test NULL astring values are supported.
    # https://bugzilla.mozilla.org/show_bug.cgi?id=450784
    c.astring_value = None
    test_string_attribute(c, "astring_value", None, expected_type=(type(None), unicode))
    c.astring_value = "astring"
    test_string_attribute(c, "astring_value", "astring", expected_type=unicode)

    test_string_attribute(c, "utf8string_value", "utf8string", expected_type=unicode)
    # Test a string already encoded gets through correctly.
    test_attribute(c, "utf8string_value", "utf8string", extended_unicode_string.encode("utf8"), extended_unicode_string, expected_type=unicode)

    # This will fail internal string representation :(  Test we don't crash
    try:
        c.wstring_value = "a big char >" + chr(129) + "<"
        print_error("strings with chars > 128 appear to have stopped failing?")
    except UnicodeError:
        pass

    test_attribute(c, "iid_value", component_iid, new_iid)
    test_attribute(c, "iid_value", component_iid, str(new_iid), new_iid)
    test_attribute(c, "iid_value", component_iid, xpcom._xpcom.IID(new_iid))

    test_attribute_failure(c, "no_attribute", "boo", AttributeError)

    test_attribute(c, "interface_value", None, c)
    test_attribute_failure(c, "interface_value", 2, ValueError)

    test_attribute(c, "isupports_value", None, c)

    # The methods
    test_method(c.do_boolean, (False, True), (True, False, True))
    test_method(c.do_boolean, (True, False), (True, False, True))
    test_method(c.do_boolean, (True, True), (False, True, False))

    test_int_method(c.do_octet)
    test_int_method(c.do_short)

    test_int_method(c.do_unsigned_short)
    test_int_method(c.do_long)
    test_int_method(c.do_unsigned_long)
    test_int_method(c.do_long_long)
    test_int_method(c.do_unsigned_long)
    test_int_method(c.do_float)
    test_int_method(c.do_double)

    test_method(c.do_char, ("A", " "), (chr(ord("A")+ord(" ")), " ","A") )
    test_method(c.do_char, ("A", "\0"), ("A", "\0","A") )
    test_method(c.do_wchar, ("A", " "), (chr(ord("A")+ord(" ")), " ","A") )
    test_method(c.do_wchar, ("A", "\0"), ("A", "\0","A") )

    test_method(c.do_string, ("Hello from ", "Python"), ("Hello from Python", "Hello from ", "Python") )
    test_method(c.do_string, (u"Hello from ", u"Python"), ("Hello from Python", "Hello from ", "Python") )
    test_method(c.do_string, (None, u"Python"), ("Python", None, "Python") )
    test_method(c.do_string, (None, really_big_string), (really_big_string, None, really_big_string) )
    test_method(c.do_string, (None, really_big_wstring), (really_big_string, None, really_big_string) )
    test_method(c.do_wstring, ("Hello from ", "Python"), ("Hello from Python", "Hello from ", "Python") )
    test_method(c.do_wstring, (u"Hello from ", u"Python"), ("Hello from Python", "Hello from ", "Python") )
    test_method(c.do_string, (None, really_big_wstring), (really_big_wstring, None, really_big_wstring) )
    test_method(c.do_string, (None, really_big_string), (really_big_wstring, None, really_big_wstring) )
    test_method(c.do_nsIIDRef, (component_iid, new_iid), (component_iid, component_iid, new_iid))
    test_method(c.do_nsIIDRef, (new_iid, component_iid), (new_iid, component_iid, component_iid))
    test_method(c.do_nsIPythonTestInterface, (None, None), (None, None, c))
    test_method(c.do_nsIPythonTestInterface, (c, c), (c, c, c))
    test_method(c.do_nsISupports, (None, None), (c, None, None))
    test_method(c.do_nsISupports, (c,c), (c, c, c))
    test_method(c.do_nsISupportsIs, (xpcom._xpcom.IID_nsISupports,), c)
    test_method(c.do_nsISupportsIs, (xpcom.components.interfaces.nsIPythonTestInterface,), c)
##    test_method(c.do_nsISupportsIs2, (xpcom.components.interfaces.nsIPythonTestInterface,c), (xpcom.components.interfaces.nsIPythonTestInterface,c))
##    test_method(c.do_nsISupportsIs3, (c,), (xpcom.components.interfaces.nsIPythonTestInterface,c))
##    test_method(c.do_nsISupportsIs4, (), (xpcom.components.interfaces.nsIPythonTestInterface,c))
    # Test the constants.
    test_constant(c, "One", 1)
    test_constant(c, "Two", 2)
    test_constant(c, "MinusOne", -1)
    test_constant(c, "BigLong", 0x7FFFFFFF)
    test_constant(c, "BiggerLong", -1)
    test_constant(c, "BigULong", 0xFFFFFFFF)
    # Test the components.Interfaces semantics
    i = xpcom.components.interfaces.nsIPythonTestInterface
    test_constant(i, "One", 1)
    test_constant(i, "Two", 2)
    test_constant(i, "MinusOne", -1)
    test_constant(i, "BigLong", 0x7FFFFFFF)
    test_constant(i, "BigULong", 0xFFFFFFFF)

def test_derived_interface(c, test_flat = 0, isJS = False):
    val = "Hello\0there"
    expected = val * 2

    if not isJS:
        # Don't test from JS, it can't deal with nulls in |string|s
        # (it _can_ deal with nulls in AStrings/ACStrings)
        test_method(c.DoubleString, (val,), expected, expected_type=str)
        test_method(c.DoubleString2, (val,), expected, expected_type=str)
        test_method(c.DoubleString3, (val,), expected, expected_type=str)
        test_method(c.DoubleString4, (val,), expected, expected_type=str)
    test_method(c.UpString, (val,), val.upper(), expected_type=str)
    test_method(c.UpString2, (val,), val.upper(), expected_type=str)
    test_method(c.GetFixedString, (20,), "A"*20, expected_type=str)
    val = u"Hello\0there"
    expected = val * 2
    if not isJS:
        # Don't test from JS, it can't deal with nulls in |string|s
        # (it _can_ deal with nulls in AStrings/ACStrings)
        test_method(c.DoubleWideString, (val,), expected, expected_type=unicode)
        test_method(c.DoubleWideString2, (val,), expected, expected_type=unicode)
        test_method(c.DoubleWideString3, (val,), expected, expected_type=unicode)
        test_method(c.DoubleWideString4, (val,), expected, expected_type=unicode)
    test_method(c.UpWideString, (val,), val.upper(), expected_type=unicode)
    test_method(c.UpWideString2, (val,), val.upper(), expected_type=unicode)
    test_method(c.GetFixedWideString, (20,), u"A"*20, expected_type=unicode)
    val = extended_unicode_string
    test_method(c.CopyUTF8String, ("foo",), u"foo", expected_type=unicode)
    test_method(c.CopyUTF8String, (u"foo",), u"foo", expected_type=unicode)
    test_method(c.CopyUTF8String, (val,), val, expected_type=unicode)
    test_method(c.CopyUTF8String, (val.encode("utf8"),), val, expected_type=unicode)
    test_method(c.CopyUTF8String2, ("foo",), u"foo", expected_type=unicode)
    test_method(c.CopyUTF8String2, (u"foo",), u"foo", expected_type=unicode)
    test_method(c.CopyUTF8String2, (val,), val, expected_type=unicode)
    test_method(c.CopyUTF8String2, (val.encode("utf8"),), val, expected_type=unicode)
    items = [1,2,3,4,5]
    test_method(c.MultiplyEachItemInIntegerArray, (3, items,), map(lambda i:i*3, items))

    test_method(c.MultiplyEachItemInIntegerArrayAndAppend, (3, items), items + map(lambda i:i*3, items))
    items = "Hello from Python".split()
    expected = map( lambda x: x*2, items)
    test_method(c.DoubleStringArray, (items,), expected)

    test_method(c.CompareStringArrays, (items, items), cmp(items, items))
    # Can we pass lists and tuples correctly?
    test_method(c.CompareStringArrays, (items, tuple(items)), cmp(items, items))
    items2 = ["Not", "the", "same"]
    test_method(c.CompareStringArrays, (items, items2), cmp(items, items2))

    expected = items[:]
    expected.reverse()
    test_method(c.ReverseStringArray, (items,), expected)

    expected = "Hello from the Python test component".split()
    test_method(c.GetStrings, (), expected)

    val = "Hello\0there"
    test_method(c.UpOctetArray, (val,), val.upper(), expected_type=bytes)
    test_method(c.UpOctetArray, (unicode(val),), val.upper(), expected_type=bytes)
    # Passing Unicode objects here used to cause us grief.
    test_method(c.UpOctetArray2, (val,), val.upper(), expected_type=bytes)

    test_method(c.CheckInterfaceArray, ((c, c),), 1)
    test_method(c.CheckInterfaceArray, ((c, None),), 0)
    test_method(c.CheckInterfaceArray, ((),), 1)
    test_method(c.CopyInterfaceArray, ((c, c),), [c,c])

    test_method(c.GetInterfaceArray, (), [c,c,c, None])
    test_method(c.ExtendInterfaceArray, ((c,c,c, None),), [c,c,c,None,c,c,c,None] )

    expected = [xpcom.components.interfaces.nsIPythonTestInterfaceDOMStrings, xpcom.components.classes[contractid].clsid]
    test_method(c.GetIIDArray, (), expected)

    val = [xpcom.components.interfaces.nsIPythonTestInterfaceExtra, xpcom.components.classes[contractid].clsid]
    expected = val * 2
    test_method(c.ExtendIIDArray, (val,), expected)

    test_method(c.GetArrays, (), ( [1,2,3], [4,5,6] ) )
    test_method(c.CopyArray, ([1,2,3],), [1,2,3] )
    test_method(c.CopyAndDoubleArray, ([1,2,3],), [1,2,3,1,2,3] )
    # for the next call, the second arg (None) is automatically converted to an array [0,0,0]
    # because we can't pass null to inout args
    test_method(c.AppendArray, ([1,2,3],), [1,2,3,0,0,0])
    test_method(c.AppendArray, ([1,2,3],[4,5,6]), [1,2,3,4,5,6])

    test_method(c.CopyVariant, ([],), [])
    test_method(c.CopyVariant, (None,), None)
    test_method(c.CopyVariant, (1,), 1)
    test_method(c.CopyVariant, (1.0,), 1.0)
    test_method(c.CopyVariant, (-1,), -1)
    test_method(c.CopyVariant, ((1 << 31) - 1,), (1 << 31) - 1)
    test_method(c.CopyVariant, ("foo",), "foo")
    test_method(c.CopyVariant, (u"foo",), u"foo")
    test_method(c.CopyVariant, (c,), c)
    test_method(c.CopyVariant, (component_iid,), component_iid)
    test_method(c.CopyVariant, ((1,2),), [1,2])
    test_method(c.CopyVariant, ((1.2,2.1),), [1.2,2.1])
    test_method(c.CopyVariant, (("foo","bar"),), ["foo", "bar"])
    test_method(c.CopyVariant, ((component_iid,component_iid),), [component_iid,component_iid])
    test_method(c.CopyVariant, ((c,c),), [c,c])
    sup = c.queryInterface(xpcom.components.interfaces.nsISupports)._comobj_
    test_method(c.CopyVariant, ((sup, sup),), [sup,sup])
    test_method(c.CopyVariant, ([1,"test"],), [1,"test"])
    test_method(c.AppendVariant, (1,2), 3)
    test_method(c.AppendVariant, ((1,2),(3,4)), 10)
    test_method(c.AppendVariant, ("bar", "foo"), "foobar")
    test_method(c.AppendVariant, (None, None), None)

    test_method(c.SumVariants, ([],), None)
    test_method(c.SumVariants, ([1,2,3],), 6)
    test_method(c.SumVariants, (['foo', 'bar'],), 'foobar')
    # We previously had trouble working out the IID of interface arrays, so
    # had to pass an explicitly wrapped variant - let's check that still works.
    test_method(c.SumVariants, ([MakeVariant(1),MakeVariant(2),MakeVariant(3)],), 6)
    test_method(c.SumVariants, ([MakeVariant('foo'), MakeVariant('bar')],), 'foobar')

    test_method(c.ReturnArray, (), [1,2,3])

    if not test_flat:
        c = c.queryInterface(xpcom.components.interfaces.nsIPythonTestInterfaceDOMStrings)
# NULL DOM strings don't work yet.
#    test_method(c.GetDOMStringResult, (-1,), None)
    test_method(c.GetDOMStringResult, (3,), "PPP", expected_type=unicode)
#    test_method(c.GetDOMStringOut, (-1,), None)
    test_method(c.GetDOMStringOut, (4,), "yyyy", expected_type=unicode)
    val = "Hello there"
    test_method(c.GetDOMStringLength, (val,), len(val), expected_type=int)
    test_method(c.GetDOMStringRefLength, (val,), len(val), expected_type=int)
    test_method(c.GetDOMStringPtrLength, (val,), len(val), expected_type=int)
    test_method(c.ConcatDOMStrings, (val,val), val+val, expected_type=unicode)
    test_attribute(c, "domstring_value", "dom", "new dom", expected_type=unicode)
    if c.domstring_value_ro != "dom":
        print_error("Read-only DOMString not correct - got %s" % (c.domstring_ro,))
    try:
        c.dom_string_ro = "new dom"
        print_error("Managed to set a readonly attribute - eek!")
    except AttributeError:
        pass
    except:
        print_error("Unexpected exception when setting readonly attribute: %s: %s" % (sys.exc_info()[0], sys.exc_info()[1]))
    if c.domstring_value_ro != "dom":
        print_error("Read-only DOMString not correct after failed set attempt - got %s" % (c.domstring_ro,))

def do_test_failures():
    c = xpcom.client.Component(contractid, xpcom.components.interfaces.nsIPythonTestInterfaceExtra)
    try:
        ret = c.do_nsISupportsIs( xpcom._xpcom.IID_nsIInterfaceInfoManager )
        print "*** got", ret, "***"
        raise RuntimeError, "We worked when using an IID we don't support!?!"
    except xpcom.Exception, details:
        if details.errno != xpcom.nsError.NS_ERROR_NO_INTERFACE:
            raise RuntimeError, "Wrong COM exception type: %r" % (details,)

def test_failures():
    # This extra stack-frame ensures Python cleans up sys.last_traceback etc
    do_test_failures()

def test_component(contractid=contractid, isJS=False):

    c = xpcom.client.Component(contractid, Ci.nsIPythonTestInterface)
    test_base_interface(c, isJS=isJS)
    # Now create an instance using the derived IID, and test that.
    c = xpcom.client.Component(contractid, Ci.nsIPythonTestInterfaceExtra)
    test_base_interface(c, isJS=isJS)
    test_derived_interface(c, isJS=isJS)
    # Now create an instance and test interface flattening.
    if not isJS:
        c = Cc[contractid].createInstance()
        test_base_interface(c)
        test_derived_interface(c, test_flat=1)

    # We had a bug where a "set" of an attribute before a "get" failed.
    # Don't let it happen again :)
    c = Cc[contractid].createInstance(Ci.nsIPythonTestInterface)
    c.boolean_value = 0
    
    # This name is used in exceptions etc - make sure we got it from nsIClassInfo OK.
    assert c._object_name_ == contractid

def test_all():
    print "Testing Python -> Python"
    try:
        test_component(contractid)
    finally:
        print "End testing Python -> Python"
    test_failures()
    test_from_js()
    test_from_python_to_js()

try:
    from sys import gettotalrefcount
except ImportError:
    # Not a Debug build - assume no references (can't be leaks then :-)
    def gettotalrefcount():
        return 0

from pyxpcom_test_tools import getmemusage

def test_from_js():
    print "Testing JS -> Python:"
    try:
        c = Cc["JavaScript.TestComponent"].createInstance(Ci.nsIRunnable)
        c.run() # throws on failure
    finally:
        print "End testing JS -> Python"

def test_from_python_to_js():
    print "Testing Python -> JS:"
    try:
        test_component("JavaScript.TestComponent", isJS=True)
    finally:
        print "End testing Python -> JS"

def doit(num_loops = -1):
    # Do the test lots of times - can help shake-out ref-count bugs.
    if num_loops == -1: num_loops = 5
    for i in xrange(num_loops):
        test_all()

        if i==0:
            # First loop is likely to "leak" as we cache things.
            # Leaking after that is a problem.
            if gc is not None:
                gc.collect()
            num_refs = gettotalrefcount()
            try:
                mem_usage = getmemusage()
            except:
                mem_usage = 0 # Failed to get memory usage

        if num_errors:
            break

    if gc is not None:
        gc.collect()

    lost = gettotalrefcount() - num_refs
    # Sometimes we get spurious counts off by 1 or 2.
    # This can't indicate a real leak, as we have looped
    # more than twice!
    if abs(lost)>3: # 2 or 3 :)
        print "*** Lost %d references" % (lost,)

    # sleep to allow the OS to recover
    time.sleep(1)
    try:
        mem_lost = getmemusage() - mem_usage
    except:
        mem_lost = 0 # failed to get memory usage
    # working set size is fickle, and when we were leaking strings, this test
    # would report a leak of 100MB.  So we allow a 3MB buffer - but even this
    # may still occasionally report spurious warnings.  If you are really
    # worried, bump the counter to a huge value, and if there is a leak it will
    # show.
    if mem_lost > 3000000:
        print "*** Lost %.6f MB of memory" % (mem_lost/1000000.0,)

    assert num_errors==0, "There were %d errors testing the Python component" % (num_errors,)

def suite():
    from pyxpcom_test_tools import suite_from_functions
    return suite_from_functions(doit)

if __name__=='__main__':
    num_iters = 10 # times times is *lots* - we do a fair bit of work!
    if __name__=='__main__' and len(sys.argv) > 1:
        num_iters = int(sys.argv[1])

    if "-v" in sys.argv: # Hack the verbose flag for the server
        xpcom.verbose = 1

    print "Testing the Python.TestComponent component"
    doit(num_iters)
    print "The Python test component worked."
    xpcom._xpcom.NS_ShutdownXPCOM()
    ni = xpcom._xpcom._GetInterfaceCount()
    ng = xpcom._xpcom._GetGatewayCount()
    print "test completed with %d interfaces and %d objects." % (ni, ng)
