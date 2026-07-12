/**
 * This file is included by js_test_component.js
 * This is the JS implementation of nsIPythonTestInterface / nsIPythonTestInterfaceExtra
 */

// boolean do_boolean(in boolean p1, inout boolean p2, out boolean p3);
JSTestComponent.prototype.do_boolean = function(p1, p2, p3) {
  let ret = p1 ^ p2.value;
  [p2.value, p3.value] = [!ret, ret];
  return ret;
};

JSTestComponent.prototype.do_octet =
JSTestComponent.prototype.do_short =
JSTestComponent.prototype.do_unsigned_short =
JSTestComponent.prototype.do_long =
JSTestComponent.prototype.do_unsigned_long =
JSTestComponent.prototype.do_long_long =
JSTestComponent.prototype.do_unsigned_long_long =
JSTestComponent.prototype.do_float =
JSTestComponent.prototype.do_double = function(p1, p2, p3) {
  let p2val = p2.value;
  [p2.value, p3.value] = [p1 - p2val, p1 * p2val];
  return p1 + p2val;
};

JSTestComponent.prototype.do_char =
JSTestComponent.prototype.do_wchar = function(p1, p2, p3) {
  p3.value = p1;
  return String.fromCharCode(p1.charCodeAt(0) + p2.value.charCodeAt(0));
};
JSTestComponent.prototype.do_string =
JSTestComponent.prototype.do_wstring = function(p1, p2, p3) {
  [p2.value, p3.value] = [p1, p2.value];
  return (p1||"") + (p3.value||"");
};
JSTestComponent.prototype.do_nsIIDRef = function(p1, p2, p3) {
  [p2.value, p3.value] = [this.iid_value, p2.value];
  return p1;
};
JSTestComponent.prototype.do_nsIPythonTestInterface = function(p1, p2, p3) {
  let p2val = p2.value;
  [p2.value, p3.value] = [p1, this];
  return p2val;
};
JSTestComponent.prototype.do_nsISupports = function(p1, p2, p3) {
  [p2.value, p3.value] = [p1, p2.value];
  return this;
};
JSTestComponent.prototype.do_nsISupportsIs = function() this;

JSTestComponent.prototype.MultiplyEachItemInIntegerArray =
  function(v, c, va) va.value = [x * v for each (x in va.value)];
JSTestComponent.prototype.MultiplyEachItemInIntegerArrayAndAppend =
  function(v, c, va) {
    va.value = va.value.concat([x * v for each (x in va.value)]);
    c.value = va.value.length;
  }
JSTestComponent.prototype.CompareStringArrays = function(a1, a2, c) {
  let scale = function(x) (x) / Math.abs(x);
  if (a1.length != a2.length)
    return scale(a1.length - a2.length);
  for (let i = 0; i < a1.length; ++i) {
    if (a1[i].localeCompare(a2[i]))
      return scale(a1[i].localeCompare(a2.i));
  }
  return 0;
}
JSTestComponent.prototype.DoubleStringArray = function(c, v) {
  v.value = [x + x for each (x in v.value)];
}
JSTestComponent.prototype.ReverseStringArray = function(c, v) v.value.reverse();
JSTestComponent.prototype.DoubleString =
JSTestComponent.prototype.DoubleWideString = function(c, v) {
  v.value += v.value;
  c.value = v.length;
};
JSTestComponent.prototype.DoubleString2 =
JSTestComponent.prototype.DoubleWideString2 = function(c, v, d, w) { w.value = v.value + v.value; };
JSTestComponent.prototype.DoubleString3 =
JSTestComponent.prototype.DoubleWideString3 = function(c, v, d) v.value + v.value;
JSTestComponent.prototype.DoubleString4 =
JSTestComponent.prototype.DoubleWideString4 = function(a, b, c) c.value = a + a;
JSTestComponent.prototype.UpString =
JSTestComponent.prototype.UpWideString = function(c, v) v.value = v.value.toUpperCase();
JSTestComponent.prototype.UpString2 =
JSTestComponent.prototype.UpWideString2 = function(c, v, w) w.value = v.toUpperCase();
JSTestComponent.prototype.CopyUTF8String =
JSTestComponent.prototype.CopyUTF8String2 = function(i, o) o.value = i;
JSTestComponent.prototype.GetFixedString =
JSTestComponent.prototype.GetFixedWideString = function(c, v) {
  if (c > 1024) {
    throw Components.Exception("count of " + c + " is too large",
                               Components.results.NS_ERRIR_INVALID_ARG);
  }
  v.value = Array(c + 1).join("A");
}

JSTestComponent.prototype.GetStrings = function(c) {
  let ret = "Hello from the Python test component".split(" ");
  c.value = ret.length;
  return ret;
}
JSTestComponent.prototype.UpOctetArray =
JSTestComponent.prototype.UpOctetArray2 = function(c, v)
  v.value = v.value.map(function(c) String.fromCharCode(c).toUpperCase().charCodeAt(0));
JSTestComponent.prototype.CheckInterfaceArray = function(c, a) a.every(function(i) !!i);
JSTestComponent.prototype.CopyInterfaceArray = function(_, s, d, c) {
  d.value = s;
  c.value = s.length;
};
JSTestComponent.prototype.GetInterfaceArray = function(c, v) {
  v.value = [this, this, this, null];
  c.value = v.value.length;
};
JSTestComponent.prototype.ExtendInterfaceArray = function(c, v) {
  v.value = v.value.concat(v.value);
  c.value = v.value.length;
};
JSTestComponent.prototype.CheckIIDArray;
JSTestComponent.prototype.GetIIDArray = function(c, v) {
  v.value = [Ci.nsIPythonTestInterfaceDOMStrings,
             Components.ID(Cc["Python.TestComponent"].number)];
  c.value = v.value.length;
}
JSTestComponent.prototype.ExtendIIDArray = function(c, v) {
  v.value = v.value.concat(v.value);
  c.value = v.value.length;
}
JSTestComponent.prototype.SumArrays;
JSTestComponent.prototype.GetArrays = function(c, v1, v2) {
  v1.value = [1, 2, 3];
  v2.value = [4, 5, 6];
  c.value = 3;
}
JSTestComponent.prototype.GetFixedArray;
JSTestComponent.prototype.CopyArray = function(c, s, d) d.value = s;
JSTestComponent.prototype.CopyAndDoubleArray = function(c, s, d) {
  d.value = s.concat(s);
  c.value = d.value.length;
}
JSTestComponent.prototype.AppendArray = function(c, s, d) {
  d.value = s.concat(d.value);
  c.value = d.value.length;
}
JSTestComponent.prototype.AppendVariant = function(s, d) {
  let sum = null;
  let add = function(a, b) a + b;
  let left = Array.isArray(s) ? s.reduce(add) : s;
  let right = Array.isArray(d.value) ? d.value.reduce(add) : d.value;
  d.value = (s === null && d.value === null) ? null : right + left;
}
JSTestComponent.prototype.CopyVariant = function(v) v;
JSTestComponent.prototype.SumVariants = function(c, v)
  c ? v.reduce(function(a, b) a + b) : null;
JSTestComponent.prototype.ReturnArray = function(v) (v.value = [1, 2, 3]).length;

JSTestComponent.prototype.SetOptionalNumbers;
JSTestComponent.prototype.SetOptionalStrings;
JSTestComponent.prototype.SetNumbersAndOptionalStrings;
JSTestComponent.prototype.SetOptionalNumbersAndStrings;

JSTestComponent.prototype.GetDOMStringResult = function(c) {
  if (c > 1024) {
    throw Components.Exception("count of " + c + " is too large",
                               Components.results.NS_ERRIR_INVALID_ARG);
  }
  return c < 0 ? null : new Array(c + 1).join("P");
}
JSTestComponent.prototype.GetDOMStringOut = function(c) {
  if (c > 1024) {
    throw Components.Exception("count of " + c + " is too large",
                               Components.results.NS_ERRIR_INVALID_ARG);
  }
  return c < 0 ? null : new Array(c + 1).join("y");
}
JSTestComponent.prototype.GetDOMStringLength =
JSTestComponent.prototype.GetDOMStringRefLength =
JSTestComponent.prototype.GetDOMStringPtrLength = function(s)
  s === null ? -1 : s.length;
JSTestComponent.prototype.ConcatDOMStrings = function(s1, s2, ret)
  ret.value = s1 + s2;

Object.defineProperty(JSTestComponent.prototype, "domstring_value_ro", {
  get: function() this.domstring_value,
});
