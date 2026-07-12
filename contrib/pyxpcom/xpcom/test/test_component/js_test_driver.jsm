/**
 * This file is included by js_test_component.js
 * This is the JS code to run a test
 */

const extended_unicode_string = "The Euro Symbol is '\u20ac'";

// Taken from http://www.svendtofte.com/code/usefull_prototypes/prototypes.js
Object.defineProperty(Array.prototype, "compareArrays", {
  enumerable: false,
  configurable: true,
  value: function compareArrays(arr) {
    if (this.length != arr.length) return false;
    for (var i = 0; i < arr.length; i++) {
      if (Array.isArray(this[i])) {
        if (!compareArrays.call(this[i], arr[i])) return false;
        continue;
      }
      if (this[i] !== arr[i]) return false;
    }
    return true;
  },
});

function is(got, expect, message) {
  if (Array.isArray(got) || Array.isArray(expect)) {
    if (Array.prototype.compareArrays.call(got, expect)) {
      return;
    }
  } else {
    if (got === expect) {
      return;
    }
  }
  throw(message + ": got " + JSON.stringify(got) +
        ", expected " + JSON.stringify(expect));
}

JSTestComponent.prototype.run =
function JSTestComponent_run() {
  /**
   * This is a wrapper around the main run() method, to force a GC after it's
   * done running.  This prevents a leak of the python component (even though
   * it should _really_ do nothing, since we should be getting GCs anyway...)
   */
  try {
    this.run_inner();
  } finally {
    Cu.forceGC();
  }
}

JSTestComponent.prototype.run_inner =
function JSTestComponent_run_inner() {
  var c = Cc["Python.TestComponent"]
            .createInstance(Ci.nsIPythonTestInterfaceDOMStrings);

  if (c.boolean_value != 1)
    throw("boolean_value has wrong initial value");
  c.boolean_value = false;
  if (c.boolean_value != false)
    throw("boolean_value has wrong new value");

  // Python's own test does thorough testing of all numeric types
  // Won't bother from here!

  if (c.char_value != 'a')
    throw("char_value has wrong initial value");
  c.char_value = 'b';
  if (c.char_value != 'b')
    throw("char_value has wrong new value");

  if (c.wchar_value != 'b')
    throw("wchar_value has wrong initial value");
  c.wchar_value = 'c';
  if (c.wchar_value != 'c')
    throw("wchar_value has wrong new value");

  if (c.string_value != 'cee')
    throw("string_value has wrong initial value");
  c.string_value = 'dee';
  if (c.string_value != 'dee')
    throw("string_value has wrong new value");

  if (c.wstring_value != 'dee')
    throw("wstring_value has wrong initial value");
  c.wstring_value = 'eee';
  if (c.wstring_value != 'eee')
    throw("wstring_value has wrong new value");
  c.wstring_value = extended_unicode_string;
  if (c.wstring_value != extended_unicode_string)
    throw("wstring_value has wrong new value");

  // Test NULL astring values are supported.
  // https://bugzilla.mozilla.org/show_bug.cgi?id=450784
  if (c.astring_value != 'astring')
    throw("astring_value has wrong initial value");
  c.astring_value = 'New value';
  if (c.astring_value != 'New value')
    throw("astring_value has wrong new value");
  c.astring_value = extended_unicode_string;
  if (c.astring_value != extended_unicode_string)
    throw("astring_value has wrong new value");
  c.astring_value = null;
  if (c.astring_value != null)
    throw("astring_value did not support null string");

  if (c.domstring_value != 'dom')
    throw("domstring_value has wrong initial value");
  c.domstring_value = 'New value';
  if (c.domstring_value != 'New value')
    throw("domstring_value has wrong new value");
  c.domstring_value = extended_unicode_string;
  if (c.domstring_value != extended_unicode_string)
    throw("domstring_value has wrong new value");

  if (c.utf8string_value != 'utf8string')
    throw("utf8string_value has wrong initial value");
  c.utf8string_value = 'New value';
  if (c.utf8string_value != 'New value')
    throw("utf8string_value has wrong new value");
  c.utf8string_value = extended_unicode_string;
  if (c.utf8string_value != extended_unicode_string)
    throw("utf8string_value has wrong new value");

  var v = new Object();
  v.value = "Hello"
  var l = new Object();
  l.value = v.value.length;
  c.DoubleString(l, v);
  if ( v.value != "HelloHello")
    throw("Could not double the string!");

  var v = new Object();
  v.value = "Hello"
  var l = new Object();
  l.value = v.value.length;
  c.DoubleWideString(l, v);
  if ( v.value != "HelloHello")
    throw("Could not double the wide string!");

  // Some basic array tests
  var v = [1, , 2, 3], v2 = [4, , 5, 6];
  if (c.SumArrays(v.length, v, v2) != 21)
    throw("Could not sum an array of integers!");

  var count = new Object();
  count.value = 0;
  var out = [];
  c.DoubleStringArray(count, out);

  v = [];
  var v2 = c.CopyVariant(v);
  if (!v.compareArrays(v2))
    throw("Could not copy an empty array of nsIVariant");

  v = [1, "test"];
  var v2 = c.CopyVariant(v);
  if (!v.compareArrays(v2))
    throw("Could not copy a non-empty array of nsIVariant");

  v = {};
  v2 = c.ReturnArray(v);
  is(v.value, [1,2,3], "Did not return correct array");
  is(v2, 3, "Did not return correct value");
};
