/* ***** BEGIN LICENSE BLOCK *****
 * Version: MPL 1.1/GPL 2.0/LGPL 2.1
 *
 * The contents of this file are subject to the Mozilla Public License Version
 * 1.1 (the "License"); you may not use this file except in compliance with
 * the License. You may obtain a copy of the License at
 * http://www.mozilla.org/MPL/
 *
 * Software distributed under the License is distributed on an "AS IS" basis,
 * WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License
 * for the specific language governing rights and limitations under the
 * License.
 *
 * The Original Code is the Python XPCOM language bindings.
 *
 * The Initial Developer of the Original Code is
 * ActiveState Tool Corp.
 * Portions created by the Initial Developer are Copyright (C) 2000
 * the Initial Developer. All Rights Reserved.
 *
 * Contributor(s):
 *   Mark Hammond <mhammond@skippinet.com.au> (original author)
 *
 * Alternatively, the contents of this file may be used under the terms of
 * either the GNU General Public License Version 2 or later (the "GPL"), or
 * the GNU Lesser General Public License Version 2.1 or later (the "LGPL"),
 * in which case the provisions of the GPL or the LGPL are applicable instead
 * of those above. If you wish to allow use of your version of this file only
 * under the terms of either the GPL or the LGPL, and not to allow others to
 * use your version of this file under the terms of the MPL, indicate your
 * decision by deleting the provisions above and replace them with the notice
 * and other provisions required by the GPL or the LGPL. If you do not delete
 * the provisions above, a recipient may use your version of this file under
 * the terms of any one of the MPL, the GPL or the LGPL.
 *
 * ***** END LICENSE BLOCK ***** */

//
// This code is part of the XPCOM extensions for Python.
//
// Written May 2000 by Mark Hammond.
//
// Based heavily on the Python COM support, which is
// (c) Mark Hammond and Greg Stein.
//
// (c) 2000, ActiveState corp.

#include "prenv.h"
#include "nsCOMPtr.h"
#include "nsDirectoryServiceDefs.h"
#include "nsDirectoryServiceUtils.h"
#include "nsIComponentRegistrar.h"
#include "nsIFile.h"
#include "nsStringGlue.h"
#include "nsXPCOMGlue.h"
#include "nsXULAppAPI.h"

#ifdef HAVE_LONG_LONG
	// Mozilla also defines this - we undefine it to
	// prevent a compiler warning.
#	undef HAVE_LONG_LONG
#endif // HAVE_LONG_LONG

#ifdef _POSIX_C_SOURCE // Ditto here
#	undef _POSIX_C_SOURCE
#endif // _POSIX_C_SOURCE

#include <Python.h>

#include "PyAppInfo.h"

#ifdef XP_WIN
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include "windows.h"
#endif

#if defined(XP_UNIX)
  #if !defined(XP_MACOSX)
    #include "mozilla/HashFunctions.h" // see reference to bug 763327
  #endif /* !XP_MACOSX */
#include <dlfcn.h>
#endif /* XP_UNIX */

// Copied from nsXPCOMPrivate.h
#ifndef MAXPATHLEN
#ifdef PATH_MAX
#define MAXPATHLEN PATH_MAX
#elif defined(_MAX_PATH)
#define MAXPATHLEN _MAX_PATH
#elif defined(CCHMAXPATH)
#define MAXPATHLEN CCHMAXPATH
#else
#define MAXPATHLEN 1024
#endif
#endif

#if defined(DEBUG)
	void DUMP(const char *fmt, ...) {
		char *enabled = PR_GetEnv("PYXPCOM_DEBUG");
		if (!enabled || !*enabled || *enabled != '1') {
			return; /* default to being silent */
		}
		va_list marker;
		va_start(marker, fmt);
		vfprintf(stderr, fmt, marker);
		va_end(marker);
	}
#else
	#define DUMP(...) do { } while(0)
#endif

static bool GetModulePath(char dest[MAXPATHLEN], const char* moduleName) {
	#if defined(XP_WIN)
		// On Windows, we need to locate the Mozilla bin
		// directory.  This by using locating a Moz DLL we depend
		// on, and assume it lives in that bin dir.  Different
		// moz build types (eg, xulrunner, suite) package
		// XPCOM itself differently - but all appear to require
		// mozalloc.dll or nss3.dll - so this is what we use.
		wchar_t landmark[MAXPATHLEN];
		HMODULE hmod = GetModuleHandle("mozalloc.dll");
		if (!hmod) {
			DUMP("no malloc, trying for nss3.dll\n");
			// Try for nss3 then.
			hmod = GetModuleHandle("nss3.dll");
			if (!hmod) {
				PyErr_SetString(PyExc_RuntimeError, "We dont appear to be linked against mozalloc.dll.");
				return false;
			}
		}
		GetModuleFileNameW(hmod, landmark, sizeof(landmark)/sizeof(landmark[0]));
		landmark[sizeof(landmark)/sizeof(landmark[0]) - 1] = L'\0';
		DUMP("landmark is %S\n", landmark);
		wchar_t *end = wcsrchr(landmark, L'\\');
		if (end) *end = L'\0';
		DUMP("landmark is %S\n", landmark);
		WideCharToMultiByte(CP_UTF8, 0, landmark, -1, dest, MAXPATHLEN,
				    NULL, NULL);
		DUMP("dest is %s\n", dest);
		strcat(dest, "\\");
		strcat(dest, moduleName);
	#elif defined(XP_UNIX)
		// Elsewhere, try to check MOZILLA_FIVE_HOME
		char* mozFiveHome = PR_GetEnv("MOZILLA_FIVE_HOME");
		if (mozFiveHome && *mozFiveHome) {
			snprintf(dest, MAXPATHLEN, "%s/%s",
			         mozFiveHome, moduleName);
		} else {
			// no MOZILLA_FIVE_HOME, try finding libxul
			char buf[MAXPATHLEN];
			bool found = false;
			void *hMain = dlopen(NULL, RTLD_LAZY|RTLD_NOLOAD),
			     *hFunc = nullptr;
			Dl_info info;
			if (hMain)
				hFunc = dlsym(hMain, "NS_Alloc");
			if (hFunc && dladdr(hFunc, &info) && info.dli_fname) {
				// We found NS_Alloc; that's probably libxul
				strncpy(buf, info.dli_fname, MAXPATHLEN);
				char* basename = strrchr(buf, '/');
				if (basename) {
					++basename;
					strncpy(basename, moduleName, MAXPATHLEN - (basename - buf));
					buf[MAXPATHLEN - 1] = '\0';
					if (!access(buf, F_OK)) {
						strncpy(dest, buf, MAXPATHLEN);
						found = true;
					}
				}
			}
			if (hMain)
				dlclose(hMain);
			return found;
		}
	#else
		#error Implement me
	#endif
	return true;
}

XRE_GetFileFromPathType XRE_GetFileFromPath NS_HIDDEN;
XRE_AddManifestLocationType XRE_AddManifestLocation NS_HIDDEN;
XRE_InitEmbedding2Type XRE_InitEmbedding2 NS_HIDDEN;
typedef bool (NS_FROZENCALL * init_xpcom_realType)();
void *hLibPyXPCOM; // handle to main pyxpcom library

static already_AddRefed<nsIFile> GetAppDir() {
	nsCOMPtr<nsIFile> app_dir;
	nsresult rv;
	char* app_path = PR_GetEnv("PYXPCOM_APPDIR");
	if (app_path && *app_path) {
		rv = XRE_GetFileFromPath(app_path,
	                                 getter_AddRefs(app_dir));
		if (NS_FAILED(rv)) {
			app_dir = nullptr;
		}
	}
	if (!app_dir) {
		// look in the GRE directory for pyxpcom.manifest
		char manifestPath[MAXPATHLEN];
		bool found = GetModulePath(manifestPath, "pyxpcom.manifest");
		if (found) {
			nsCOMPtr<nsIFile> leaf;
			rv = XRE_GetFileFromPath(manifestPath,
						 getter_AddRefs(leaf));
			if (NS_SUCCEEDED(rv) && leaf) {
				rv = leaf->GetParent(getter_AddRefs(app_dir));
			}
			if (NS_FAILED(rv)) {
				app_dir = nullptr;
			}
		}
	}
	if (!app_dir) {
		DUMP("Failed to find PyXPCOM application directory\n");
		return nullptr;
	}
	#if defined(DEBUG)
		nsString path;
		(void)app_dir->GetPath(path);
		DUMP("Using appdir %s\n", NS_ConvertUTF16toUTF8(path).get());
	#endif
	return app_dir.forget();
}

// local helper to check that xpcom itself has been initialized.
// Theoretically this should only happen when a standard python program
// (ie, hosted by python itself) imports the xpcom module (ie, as part of
// the pyxpcom test suite), hence it lives here...
static bool EnsureXPCOM()
{
	DUMP("EnsureXPCOM...\n");
	static bool bHaveInitXPCOM = false;
	if (bHaveInitXPCOM) {
		// already initialized
		return true;
	}

	#if defined(XP_UNIX) && !defined(XP_MACOSX)
		// Linux only:
		// Check if XPCOM is already loaded and initialized. If we try
		// to load it again, Komodo will crash. We do this check by
		// seeing if the the XRE_main symbol is already exposed, if it
		// is visible then Komodo has already loaded libxul and we don't
		// need to do it again.
		if (!dlsym(RTLD_DEFAULT, "XRE_main")) {
			// Re-open ourselves with RTLD_GLOBAL so we can export
			// mozilla::HashBytes, so that libxul can use it.
			// See https://bugzilla.mozilla.org/show_bug.cgi?id=763327
			// (Python loads _xpcom.so without RTLD_GLOBAL, so the fact that we're
			// exporting the symbol isn't enough for libxul to find it)
			// Note that this is combined with MKSHLIB_FORCE_ALL in the makefile
			// due to more symbols being missing this way
			// (WebCore::Decimal::Decimal())
			Dl_info hash_info;
			if (!dladdr(reinterpret_cast<void*>(mozilla::HashBytes), &hash_info)) {
				// well, we're buggered
				PyErr_Format(PyExc_RuntimeError,
				             "Failed to find _xpcom.so: %s", dlerror());
				return false;
			}
			DUMP("Reloading %s\n", hash_info.dli_fname);
			void *hlib_xpcom = dlopen(hash_info.dli_fname, RTLD_NOW | RTLD_GLOBAL | RTLD_NOLOAD);
			if (!hlib_xpcom) {
				PyErr_Format(PyExc_RuntimeError,
				             "Failed to load %s: %s\n", hash_info.dli_fname, dlerror());
				// Failed to reload _xpcom.so
				return false;
			}
			// Python still has a handle on us, no worries about being closed
			dlclose(hlib_xpcom);
		}
	#endif /* defined(XP_UNIX) && !defined(XP_MACOSX) */

	nsresult rv;
	char libMozallocPath[MAXPATHLEN] = {0};
	if (!GetModulePath(libMozallocPath, MOZ_DLL_PREFIX "mozalloc" MOZ_DLL_SUFFIX)) {
		DUMP("Failed to find " MOZ_DLL_PREFIX "mozalloc" MOZ_DLL_SUFFIX "\n");
		return false;
	}
	DUMP("Using mozalloc library: %s\n", libMozallocPath);
	rv = XPCOMGlueStartup(libMozallocPath);
	if (NS_FAILED(rv)) {
		PyErr_SetString(PyExc_RuntimeError, "Failed to starting XPCOM glue");
		return false;
	}

	const struct nsDynamicFunctionLoad kXULFuncs[] = {
		{"XRE_GetFileFromPath", (NSFuncPtr*) &XRE_GetFileFromPath},
		{"XRE_AddManifestLocation", (NSFuncPtr*) &XRE_AddManifestLocation},
		{"XRE_InitEmbedding2", (NSFuncPtr*) &XRE_InitEmbedding2},
		{nullptr, nullptr },
	};
	rv = XPCOMGlueLoadXULFunctions(kXULFuncs);
	if (rv != NS_OK) {
		// Specifically check for NS_OK, failing to load anything
		// is bad for us
		PyErr_SetString(PyExc_RuntimeError, "Failed to locate XPCOM initialization functions");
		return false;
	}

	// xpcom appears to assert if already initialized, but there
	// is no official way to determine this!  Sadly though,
	// apparently this problem is not real ;) See bug 38671.
	// For now, getting the app directories appears to work.
	nsCOMPtr<nsIFile> file;
	if (NS_SUCCEEDED(NS_GetSpecialDirectory(NS_GRE_DIR, getter_AddRefs(file)))) {
		// We already have XPCOM; no need to re-initialize
		bHaveInitXPCOM = true;
		return true;
	}

	DUMP("Trying to init xpcom...\n");

	// not already initialized.
	nsCOMPtr<nsIFile> ns_bin_dir;
	// Chop off the libxpcom bit
	#ifdef XP_WIN
		const char PATH_SEP = '\\';
	#else
		const char PATH_SEP = '/';
	#endif
	char* end = strrchr(libMozallocPath, PATH_SEP);
	*end = '\0';
	DUMP("Using ns_bin_dir %s\n", libMozallocPath);
	rv = XRE_GetFileFromPath(libMozallocPath, getter_AddRefs(ns_bin_dir));
	if (NS_FAILED(rv)) {
		PyErr_SetString(PyExc_RuntimeError, "Failed to get GRE directory");
		return false;
	}

	DUMP("About to init xpcom\n");
	rv = XRE_InitEmbedding2(ns_bin_dir, nullptr, nullptr);
	DUMP("InitXPCOM2: %08x\n", rv);
	if (NS_FAILED(rv)) {
		DUMP("Failed to init xpcom: %08x\n", rv);
		PyErr_Format(PyExc_RuntimeError,
		             "The XPCOM subsystem could not be initialized: %08x", rv);
		return false;
	}
	bHaveInitXPCOM = true;
	return true;
}

/**
 * Ensure the main libpyxpcom shared library is loaded.
 * @precondition XPCOM has been initialized
 * @postcondition libpyxpcom.so / pyxpcom.dll / libpyxpcom.dylib is loaded
 */
bool EnsurePyXPCOM(init_xpcom_realType* init_xpcom_real) {
	#if defined(XP_UNIX)
		{
			// On Linux, we might already have libpyxpcom loaded from a different spot
			// (e.g. dist/lib instead of dist/bin).  Annoying that we have to do this
			// check, but c'est la vie.
			void *hLibPyXPCOMLocal = dlopen(MOZ_DLL_PREFIX "pyxpcom" MOZ_DLL_SUFFIX,
			                                RTLD_LAZY|RTLD_NOLOAD),
			     *hFunc = nullptr;
			if (hLibPyXPCOMLocal) {
				hFunc = dlsym(hLibPyXPCOMLocal, "init_xpcom_real");
				dlclose(hLibPyXPCOMLocal);
			}
			if (hFunc) {
				*init_xpcom_real = (init_xpcom_realType)hFunc;
				return true;
			}
		}
	#endif
	char libpyxpcomPath[MAXPATHLEN];
	// Find pyxpcom.dll / libpyxpcom.so / libpyxpcom.dylib
	if (!GetModulePath(libpyxpcomPath, MOZ_DLL_PREFIX "pyxpcom" MOZ_DLL_SUFFIX)) {
		return false;
	}

	nsresult rv;
	nsCOMPtr<nsIFile> libpyxpcomFile;
	rv = XRE_GetFileFromPath(libpyxpcomPath, getter_AddRefs(libpyxpcomFile));
	bool exists = false;
	if (NS_SUCCEEDED(rv)) {
		// XRE_GetFileFromPath is inconsistent whether it checks if the file exists.
		rv = libpyxpcomFile->Exists(&exists);
	}
	if (NS_FAILED(rv) || !exists) {
		DUMP("Trying alternative libpyxpcom path\n");
		libpyxpcomFile = GetAppDir();
		if (!libpyxpcomFile) {
			PyErr_SetString(PyExc_RuntimeError, "Failed to find app dir");
			return false;
		}
		(void)libpyxpcomFile->AppendNative(NS_LITERAL_CSTRING(MOZ_DLL_PREFIX "pyxpcom" MOZ_DLL_SUFFIX));
		rv = libpyxpcomFile->Exists(&exists);
		if (NS_FAILED(rv) || !exists) {
			PyErr_SetString(PyExc_RuntimeError, "Failed to find " MOZ_DLL_PREFIX "pyxpcom" MOZ_DLL_SUFFIX);
			return false;
		}
	}
	nsString libpyxpcomStr;
	rv = libpyxpcomFile->GetPath(libpyxpcomStr);
	DUMP("Loading libpyxpcom from %s\n", NS_ConvertUTF16toUTF8(libpyxpcomStr).get());

	#if defined(XP_WIN)
		hLibPyXPCOM = LoadLibraryExW(libpyxpcomStr.get(), NULL, LOAD_WITH_ALTERED_SEARCH_PATH);
		if (!hLibPyXPCOM) {
			PyErr_Format(PyExc_RuntimeError,
				     "Failed to load pyxpcom.dll: %08x",
				     GetLastError());
			return false;
		}
		DUMP("hlibpyxpcom: %08x\n", hLibPyXPCOM);
		*init_xpcom_real = (init_xpcom_realType)GetProcAddress((HMODULE)hLibPyXPCOM,
		                                                       "init_xpcom_real");
		if (!*init_xpcom_real) {
			PyErr_Format(PyExc_RuntimeError,
				     "Failed to load pyxpcom.dll entry point: %08x",
				     GetLastError());
			FreeLibrary((HMODULE)hLibPyXPCOM);
			hLibPyXPCOM = nullptr;
			return false;
		}
	#elif defined(XP_UNIX)
		hLibPyXPCOM = dlopen(NS_ConvertUTF16toUTF8(libpyxpcomStr).get(),
		                     RTLD_LAZY | RTLD_GLOBAL);
		if (!hLibPyXPCOM) {
			PyErr_Format(PyExc_RuntimeError,
				     "Failed to load %s: %s",
				     MOZ_DLL_PREFIX "pyxpcom" MOZ_DLL_SUFFIX,
				     dlerror());
			return false;
		}
		DUMP("got dl handle %p\n", hLibPyXPCOM);
		*init_xpcom_real = (init_xpcom_realType)dlsym(hLibPyXPCOM, "init_xpcom_real");
		if (!*init_xpcom_real) {
			DUMP("dlsym returns %p: %s\n", *init_xpcom_real, dlerror());
			PyErr_Format(PyExc_RuntimeError,
				     "Failed to load %s entry point: %s",
				     MOZ_DLL_PREFIX "pyxpcom" MOZ_DLL_SUFFIX,
				     dlerror());
			return false;
		}
	#else
		#error Implment dlopen for this platform!
	#endif
	DUMP("init_xpcom_real loaded: %p\n", *init_xpcom_real);
	return true;
}

/**
 * Register AppInfo for PyXPCOM
 */
bool RegisterPyAppInfo() {
	DUMP("Attempting to register PyAppInfo\n");
	nsresult rv;
	nsCOMPtr<nsIComponentRegistrar> registrar;
	rv = NS_GetComponentRegistrar(getter_AddRefs(registrar));
	if (NS_FAILED(rv) || !registrar) {
		PyErr_SetString(PyExc_RuntimeError, "Failed to get XPCOM component registrar");
		return false;
	}

	const char kAppInfoContractId[] = "@mozilla.org/xre/app-info;1";
	nsCOMPtr<nsIXULAppInfo> appInfo = do_GetService(kAppInfoContractId);
	if (appInfo) {
		// It's already there
		DUMP("AppInfo already exists, ignoring\n");
		return true;
	}

	nsCOMPtr<nsIFile> app_dir = GetAppDir(); // Ignore failures

	// We need to try to implement nsIXULRuntime (which uses the
	// appinfo contract id), so that the manifest can figure out
	// what OS/API we are using
	PyAppInfo* appinfo = PyAppInfo::GetSingleton(app_dir);
	if (!appinfo) {
		PyErr_SetString(PyExc_RuntimeError, "Failed to create PyAppInfo");
		return false;
	}
	const nsCID APPINFO_CID = {
			/* cccd5dab-efc5-4d14-8ee5-7fe30e2a23ba */
			0xcccd5dab, 0xefc5, 0x4d14,
			{0x8e, 0xe5, 0x7f, 0xe3, 0x0e, 0x2a, 0x23, 0xba}
		};
	rv = registrar->RegisterFactory(APPINFO_CID,
					"Python XPCOM App Info",
					kAppInfoContractId,
					appinfo);
	DUMP("Register appinfo: %08x\n", rv);
	// Ignore appinfo registration failure, and hope it's good enough
	return true;
}

/**
 * Register PyXPCOM bits with XPCOM
 */
bool RegisterPyXPCOMComponents() {
	DUMP("Attempting to register pyxpcom components (loader etc)\n");
	const char kPyLoaderContractId[] = "@mozilla.org/module-loader/python;1";
	bool isRegistered;
	nsCOMPtr<nsIComponentRegistrar> registrar;
	nsresult rv = NS_GetComponentRegistrar(getter_AddRefs(registrar));
	if (NS_FAILED(rv) || !registrar) {
		PyErr_SetString(PyExc_RuntimeError, "Failed to get XPCOM component registrar");
		return false;
	}
	rv = registrar->IsContractIDRegistered(kPyLoaderContractId, &isRegistered);
	if (NS_SUCCEEDED(rv) && isRegistered) {
		// pyloader is already loaded, we're good
		DUMP("PyLoader registered, skipping component registration\n");
		return true;
	}

	nsCOMPtr<nsIFile> app_manifest = GetAppDir();
	if (!app_manifest) {
		PyErr_SetString(PyExc_RuntimeError,
		                "Failed to get PyXPCOM application directory");
		return false;
	}
	app_manifest->Append(NS_LITERAL_STRING("pyxpcom.manifest"));
	bool exists = false;
	rv = app_manifest->Exists(&exists);
	if (!exists) {
		PyErr_SetString(PyExc_RuntimeError, "Can't find pyxpcom.manifest");
		return false;
	}
	#if defined(DEBUG)
		nsString path;
		(void)app_manifest->GetPath(path);
		DUMP("pyxpcom.manifest at %s\n", NS_ConvertUTF16toUTF8(path).get());
	#endif
	rv = XRE_AddManifestLocation(NS_COMPONENT_LOCATION, app_manifest);
	DUMP("pyxpcom.manifest registered: %08x\n", rv);

	#if defined(DEBUG)
		rv = registrar->IsContractIDRegistered("Python.TestComponent", &isRegistered);
		DUMP("Is Python.TestComponent registered? rv=%08x result=%s\n",
		     rv, isRegistered ? "yes" : "no");
	#endif

	rv = registrar->IsContractIDRegistered(kPyLoaderContractId, &isRegistered);
	DUMP("Is pyloader registered? rv=%08x result=%s\n",
	     rv, isRegistered ? "yes" : "no");
	if (NS_FAILED(rv) || !isRegistered) {
		// pyloader is already loaded, we're good
		PyErr_SetString(PyExc_RuntimeError, "Failed to register pyloader");
		return false;
	}

	return true;
}

////////////////////////////////////////////////////////////
// The module init code.
//

static init_xpcom_realType init_xpcom_real = nullptr;
extern "C" NS_EXPORT
void 
init_xpcom() {
	if (init_xpcom_real) {
		// We've already done the dance before; just do the real init
		init_xpcom_real();
		return;
	}

	// Ensure XPCOM has been initialized
	if (!EnsureXPCOM()) {
		DUMP("EnsureXPCOM failed\n");
		return;
	}

	if (!RegisterPyAppInfo()) {
		DUMP("RegisterPyAppInfo failed\n");
		return;
	}

	if (!EnsurePyXPCOM(&init_xpcom_real)) {
		DUMP("Failed to load libpyxpcom.so!\n");
		return;
	}

	if (!RegisterPyXPCOMComponents()) {
		DUMP("RegisterPyXPCOMComponents failed\n");
		return;
	}

	DUMP("About to do real xpcom init\n");
	init_xpcom_real();
	DUMP("init_xpcom done\n");

	// Close hLibPyXPCOM now that everything's loaded
	#if defined(XP_WIN)
		if (hLibPyXPCOM) {
			FreeLibrary((HMODULE)hLibPyXPCOM);
		}
	#elif defined(XP_UNIX)
		if (hLibPyXPCOM) {
			dlclose(hLibPyXPCOM);
		}
	#endif
}
