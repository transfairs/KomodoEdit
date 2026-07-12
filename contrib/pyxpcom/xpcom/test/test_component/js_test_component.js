/**
 * JavaScript test component
 * This is used to test that calling Python components from JS works correctly
 */

const { classes: Cc, interfaces: Ci, utils: Cu, results: Cr } = Components;

Cu.import("resource://gre/modules/Services.jsm");
Cu.import("resource://gre/modules/XPCOMUtils.jsm");

function JSTestComponent() {
  this.boolean_value = 1;
  this.octet_value = 2;
  this.short_value = 3;
  this.ushort_value = 4;
  this.long_value = 5;
  this.ulong_value = 6;
  this.long_long_value = 7;
  this.ulong_long_value = 8;
  this.float_value = 9.0;
  this.double_value = 10.0;
  this.char_value = "a";
  this.wchar_value = "b";
  this.string_value = "cee";
  this.wstring_value = "dee";
  this.astring_value = "astring";
  this.acstring_value = "acstring";
  this.utf8string_value = "utf8string";
  this.iid_value = Components.ID(Cc["Python.TestComponent"].number);
  this.interface_value = null;
  this.isupports_value = null;
  this.domstring_value = "dom";
  this.optional_number_1 = 1;
  this.optional_number_2 = 2;
  this.optional_string_1 = "string 1";
  this.optional_string_2 = "string 2";
}

["js_test_impl.jsm", "js_test_driver.jsm"].forEach(function(name) {
  let file = __LOCATION__.parent;
  file.append(name);
  Services.scriptloader.loadSubScript(Services.io.newFileURI(file).spec);
});

JSTestComponent.prototype.QueryInterface =
  XPCOMUtils.generateQI([Ci.nsIRunnable,
                         Ci.nsIPythonTestInterface,
                         Ci.nsIPythonTestInterfaceExtra,
                         Ci.nsIPythonTestInterfaceDOMStrings]);
JSTestComponent.prototype.classID = Components.ID("{7b7d47bd-2cb3-4b4c-9ca0-d157a87e219a}");

const NSGetFactory = XPCOMUtils.generateNSGetFactory([JSTestComponent]);
