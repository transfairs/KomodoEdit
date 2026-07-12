/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

/**
 * Global defines to be used throughout Komodo code base.
 */

const Cc = Components.classes;
const Ci = Components.interfaces;
const Cu = Components.utils;

/**
 * Global utility modules.
 */
const koGlobalServices = Cu.import("resource://gre/modules/Services.jsm", {}).Services;
const {XPCOMUtils} = Cu.import("resource://gre/modules/XPCOMUtils.jsm", {});

/**
 * Define the main Komodo namespace.
 */
if (typeof(ko) == 'undefined') {
    var ko = {};
}

/* Komodo version */
ko.version = "PP_KOMODO_VERSION";

JetPack.defineDeprecatedProperty(ko, "logging", "ko/logging", {since: "9.0.0a1"});
JetPack.defineDeprecatedProperty(ko, "printing", "ko/printing", {since: "9.0.0a1"});

require("ko/profiler").start("startup");

/**
 * Global Komodo services, defined on the Services object (once per app).
 */
if (!koGlobalServices.koInfo) {
    XPCOMUtils.defineLazyGetter(koGlobalServices, "koInfo", () =>
        Cc["@activestate.com/koInfoService;1"].getService(Ci.koIInfoService));

    XPCOMUtils.defineLazyGetter(koGlobalServices, "koDirs", () =>
        Cc["@activestate.com/koDirs;1"].getService(Ci.koIDirs));

    XPCOMUtils.defineLazyGetter(koGlobalServices, "koFileSvc", () =>
        Cc["@activestate.com/koFileService;1"].getService(Ci.koIFileService));

    XPCOMUtils.defineLazyGetter(koGlobalServices, "koFileStatus", () =>
        Cc["@activestate.com/koFileStatusService;1"].getService(Ci.koIFileStatusService));

    XPCOMUtils.defineLazyGetter(koGlobalServices, "koDocSvc", () =>
        Cc["@activestate.com/koDocumentService;1"].getService(Ci.koIDocumentService));

    XPCOMUtils.defineLazyGetter(koGlobalServices, "koViewSvc", () =>
        Cc["@activestate.com/koViewService;1"].getService(Ci.koIViewService));

    XPCOMUtils.defineLazyGetter(koGlobalServices, "koTextUtils", () =>
        Cc["@activestate.com/koTextUtils;1"].getService(Ci.koITextUtils));

    XPCOMUtils.defineLazyGetter(koGlobalServices, "koEncodingSvc", () =>
        Cc["@activestate.com/koEncodingServices;1"].getService(Ci.koIEncodingServices));

    XPCOMUtils.defineLazyGetter(koGlobalServices, "koSysUtils", () =>
        Cc["@activestate.com/koSysUtils;1"].getService(Ci.koISysUtils));

    XPCOMUtils.defineLazyGetter(koGlobalServices, "koLangRegistry", () =>
        Cc["@activestate.com/koLanguageRegistryService;1"].getService(Ci.koILanguageRegistryService));

    XPCOMUtils.defineLazyGetter(koGlobalServices, "koAsync", () =>
        Cc["@activestate.com/koAsyncService;1"].getService(Ci.koIAsyncService));

    XPCOMUtils.defineLazyGetter(koGlobalServices, "koRun", () =>
        Cc["@activestate.com/koRunService;1"].getService(Ci.koIRunService));

    XPCOMUtils.defineLazyGetter(koGlobalServices, "koFind", () =>
        Cc["@activestate.com/koFindService;1"].getService(Ci.koIFindService));

    XPCOMUtils.defineLazyGetter(koGlobalServices, "koOs", () =>
        Cc["@activestate.com/koOs;1"].getService(Ci.koIOs));

    XPCOMUtils.defineLazyGetter(koGlobalServices, "koOsPath", () =>
        Cc["@activestate.com/koOsPath;1"].getService(Ci.koIOsPath));

    XPCOMUtils.defineLazyGetter(koGlobalServices, "koLastError", () =>
        Cc["@activestate.com/koLastErrorService;1"].getService(Ci.koILastErrorService));

    XPCOMUtils.defineLazyGetter(koGlobalServices, "koUserEnv", () =>
        Cc["@activestate.com/koUserEnviron;1"].getService(Ci.koIUserEnviron));

    XPCOMUtils.defineLazyGetter(koGlobalServices, "koRemoteConnection", () =>
        Cc["@activestate.com/koRemoteConnectionService;1"].getService(Ci.koIRemoteConnectionService));

    XPCOMUtils.defineLazyGetter(koGlobalServices, "koWebbrowser", () =>
        Cc["@activestate.com/koWebbrowser;1"].getService(Ci.koIWebbrowser));
}
