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
 *   Todd Whiteman <twhitema@gmail.com>
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

// pyloader
//
// A Mozilla component loader that loads the Python xpcom components.
//
// This is really a thin C++ wrapper around a Python implemented component
// loader. The Mozilla 2.0 xpcom component loader requires this to be a binary
// file as some of the component interfacing is not exposed through XPCOM.

/* Allow logging in the release build */
#ifdef MOZ_LOGGING
#define FORCE_PR_LOG
#endif

#include "prlog.h"
#include "prinit.h"
#include "prerror.h"

#include "pyloader.h"
#include "nsXPCOM.h"
#include "nsThreadUtils.h"


static PRLogModuleInfo *nsPythonModuleLoaderLog =
    PR_NewLogModule("nsPythonModuleLoader");

#define LOG(level, args) PR_LOG(nsPythonModuleLoaderLog, level, args)


// This class instance will be loaded and used for component management, it will
// be loaded by the static XPCOM component loader at the end of this file.
//
// It's job is to load and return nsIModule (Python-XPCOM) objects that will
// then be used to instantiate Python XPCOM components.
nsPythonModuleLoader::nsPythonModuleLoader(): mPyLoader(NULL) {
    Init();
}
nsPythonModuleLoader::~nsPythonModuleLoader() {}

NS_IMPL_ISUPPORTS(nsPythonModuleLoader, mozilla::ModuleLoader)

nsresult
nsPythonModuleLoader::Init()
{
    MOZ_ASSERT(NS_IsMainThread(), "nsPythonModuleLoader::Init not on main thread?");

    LOG(PR_LOG_DEBUG, ("nsPythonModuleLoader::Init()"));

    /* Ensure Python environment is initialized. */
    PyXPCOM_EnsurePythonEnvironment();

    CEnterLeavePython _celp;
    PyObject *func = NULL;
    /* Setup the Python modules and variables that will be needed later. */
    mPyLoadModuleName = PyString_FromString("loadModule");
    PyObject *mod = PyImport_ImportModule("xpcom.server");
    if (!mPyLoadModuleName) goto done;
    if (!mod) goto done;
    func = PyObject_GetAttrString(mod, "PythonModuleLoader");
    if (func==NULL) goto done;
    mPyLoader = PyEval_CallObject(func, NULL);
done:
    nsresult nr = (mPyLoader != NULL) ? NS_OK : NS_ERROR_FAILURE;
    if (PyErr_Occurred()) {
            PyXPCOM_LogError("Obtaining the module object from Python failed.\n");
            nr = PyXPCOM_SetCOMErrorFromPyException();
    }
    Py_XDECREF(func);
    Py_XDECREF(mod);

    return nr;
}

const mozilla::Module*
nsPythonModuleLoader::LoadModule(mozilla::FileLocation& aFileLocation)
{
    if (aFileLocation.IsZip()) {
        NS_ERROR("Python components cannot be loaded from JARs");
        return NULL;
    }

    /* XXX temp hack */
    nsCOMPtr<nsIFile> file;
    #if 0
        file = aFileLocation.GetBaseFile();
    #else
        file = *reinterpret_cast<nsIFile**>(&aFileLocation);
    #endif

    if (PR_LOG_TEST(nsPythonModuleLoaderLog, PR_LOG_DEBUG)) {
        nsAutoCString filePath;
        file->GetNativePath(filePath);
        LOG(PR_LOG_DEBUG,
            ("nsPythonModuleLoader::LoadModule(\"%s\")", filePath.get()));
    }

    PyObject *obLocation = NULL;
    PyObject *obPythonModule = NULL;
    PythonModule* entry = NULL;
    CEnterLeavePython _celp;
    obLocation = Py_nsISupports::PyObjectFromInterface(file, NS_GET_IID(nsIFile));
    if (obLocation==NULL) goto done;
    obPythonModule = PyObject_CallMethodObjArgs(mPyLoader, mPyLoadModuleName, obLocation, NULL);
    if (!obPythonModule) goto done;

    /* entry is a Python XPCOM object, implementing the nsIModule interface. */
    entry = new PythonModule(obPythonModule, obLocation);

done:
    if (PyErr_Occurred()) {
        nsAutoString filePath;
        file->GetPath(filePath);
        PyXPCOM_LogError("Failed to load the Python module: '%s'\n",
                         NS_ConvertUTF16toUTF8(filePath).get());
    }
    Py_XDECREF(obLocation);
    Py_XDECREF(obPythonModule);
    if (!entry)
        return NULL;
    return entry;
}

void
nsPythonModuleLoader::UnloadLibraries()
{
    MOZ_ASSERT(NS_IsMainThread(), "nsPythonModuleLoader::UnloadLibraries not on main thread?");
}


/**
 * The module factory is the one that returns a nsIFactory object that is
 * capable of producing Python XPCOM instances/services. This will only be
 * called if the nsPythonModuleLoader::LoadModule method correctly loaded the
 * Python component module (i.e. if Python successfully imported the module).
 */

/* static */ already_AddRefed<nsIFactory>
nsPythonModuleLoader::PythonModule::GetFactory(const mozilla::Module& module,
                                               const mozilla::Module::CIDEntry& entry)
{
    if (PR_LOG_TEST(nsPythonModuleLoaderLog, PR_LOG_DEBUG)) {
        char idstr[NSID_LENGTH];
        entry.cid->ToProvidedString(idstr);
        LOG(PR_LOG_DEBUG, ("nsPythonModuleLoader::PythonModule::GetFactory for cid: %s", idstr));
    }

    CEnterLeavePython _celp;
    PyObject *obFactory = NULL;
    PyObject *obFnName = NULL;
    PyObject *obClsId = Py_nsIID::PyObjectFromIID(*(entry.cid));
    nsCOMPtr<nsISupports> pSupports;
    nsCOMPtr<nsIFactory> f;
    const PythonModule& pyMod = static_cast<const PythonModule&>(module);

    obFnName = PyString_FromString("getClassObject");
    obFactory = PyObject_CallMethodObjArgs(pyMod.mPyObjModule, obFnName, Py_None, obClsId, Py_None, NULL);
    if (obFactory!=NULL) {
        Py_nsISupports::InterfaceFromPyObject(obFactory, NS_GET_IID(nsIFactory), getter_AddRefs(pSupports), false);
        if (pSupports) {
            f = do_QueryInterface(pSupports);
        }
    }

    if (PyErr_Occurred()) {
        PyXPCOM_SetCOMErrorFromPyException();
        PyXPCOM_LogError("Failed to return the Python module factory");
    }
    Py_XDECREF(obFactory);
    Py_XDECREF(obFnName);
    Py_XDECREF(obClsId);

    if (f) {
        return f.forget();
    }
    return NULL;
}



/* Mozilla 2.0 module code - required for XPCOM component registration. */

// CID d96ff456-06dd-4b9c-aabf-af346a576776
#define PYXPCOM_LOADER_CID { 0xd96ff456, 0x06dd, 0x4b9c, \
                        { 0xaa, 0xbf, 0xaf, 0x34, 0x6a, 0x57, 0x67, 0x76 } }

#define PYXPCOM_LOADER_CONTRACTID "@mozilla.org/module-loader/python;1"

static nsresult PyxpcomModuleLoader(nsISupports* aOuter, REFNSIID aIID, void** aResult)
{
    nsresult rv;

    *aResult = nullptr;
    if (aOuter)
        return NS_ERROR_NO_AGGREGATION;
    nsRefPtr<nsPythonModuleLoader> inst = new nsPythonModuleLoader();
    if (!inst) {
        return NS_ERROR_OUT_OF_MEMORY;
    }
    return inst->QueryInterface(aIID, aResult);
}


NS_DEFINE_NAMED_CID(PYXPCOM_LOADER_CID);

// Table of ClassIDs (CIDs) which are implemented by this module. CIDs should be
// completely unique UUIDs. Each entry has the form:
//   { CID, service, factoryproc, constructorproc }
// where factoryproc is usually NULL.
static const mozilla::Module::CIDEntry pyxpcomLoaderClassIds[2] = {
    { &kPYXPCOM_LOADER_CID, false, NULL, PyxpcomModuleLoader },
    { NULL }
};

// Table which maps contract IDs to CIDs. A contract is a string which
// identifies a particular set of functionality. In some cases an extension
// component may override the contract ID of a builtin gecko component to modify
// or extend functionality.
static const mozilla::Module::ContractIDEntry pyxpcomLoaderContracts[2] = {
    { PYXPCOM_LOADER_CONTRACTID, &kPYXPCOM_LOADER_CID },
    { NULL }
};

// Category entries are category/key/value triples which are used to register
// contract ID as content handlers or to observe certain notifications.
//
// This is how Python registers itself as a XPCOM module loader.
static const mozilla::Module::CategoryEntry pyxpcomLoaderCategories[2] = {
    { "module-loader", "py", PYXPCOM_LOADER_CONTRACTID },
    { NULL }
};

static const mozilla::Module PyxpcomNSModule = {
    mozilla::Module::kVersion,
    pyxpcomLoaderClassIds,
    pyxpcomLoaderContracts,
    pyxpcomLoaderCategories
};

// Export the NSModule name, so Mozilla can properly find and load us.
extern "C" {
NS_EXPORT const mozilla::Module * NSModule = &PyxpcomNSModule;
}

