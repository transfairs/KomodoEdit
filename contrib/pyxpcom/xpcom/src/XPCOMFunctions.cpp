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

/**
 * This is the main Python module glue code (i.e. the thing responsible for
 * the "_xpcom" Python module).  In the pure-Python case, it's loaded by
 * _xpcom.so (in module/_xpcom.cpp) after XPCOM has been started.  This extra
 * layer of indirection is to ensure XPCOM (and its dependencies such as NSPR)
 * has been set up, so that we can link against dependent glue, making our lives
 * a whole lot easier.
 */

#include "PyXPCOM_std.h"
#include "nsXPCOM.h"
#include "nsISupportsPrimitives.h"
#include "nsIFile.h"
#include "nsICategoryManager.h"
#include "nsIComponentRegistrar.h"
#include "nsIConsoleService.h"
#include "nsDirectoryServiceDefs.h"
#include "nsDirectoryServiceUtils.h"
#include "nsXPCOMGlue.h"
#include "nsXULAppAPI.h"

#include "nsILocalFile.h"

#ifdef XP_WIN
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include "windows.h"
#endif
#include "prenv.h"

#include "nsIEventTarget.h"

#if PYXPCOM_DEBUG_INTERFACE_COUNT || PYXPCOM_DEBUG_GATEWAY_COUNT
#include "prprf.h"
#endif

#define LOADER_LINKS_WITH_PYTHON

// "boot-strap" methods - interfaces we need to get the base
// interface support!

static PyObject *
PyXPCOMMethod_GetComponentManager(PyObject *self, PyObject *args)
{
	if (!PyArg_ParseTuple(args, ""))
		return NULL;
	nsCOMPtr<nsIComponentManager> cm;
	nsresult rv;
	Py_BEGIN_ALLOW_THREADS;
	rv = NS_GetComponentManager(getter_AddRefs(cm));
	Py_END_ALLOW_THREADS;
	if ( NS_FAILED(rv) )
		return PyXPCOM_BuildPyException(rv);

	return Py_nsISupports::PyObjectFromInterface(cm, NS_GET_IID(nsIComponentManager), false);
}

// No xpcom callable way to get at the registrar, even though the interface
// is scriptable.
static PyObject *
PyXPCOMMethod_GetComponentRegistrar(PyObject *self, PyObject *args)
{
	if (!PyArg_ParseTuple(args, ""))
		return NULL;
	nsCOMPtr<nsIComponentRegistrar> cm;
	nsresult rv;
	Py_BEGIN_ALLOW_THREADS;
	rv = NS_GetComponentRegistrar(getter_AddRefs(cm));
	Py_END_ALLOW_THREADS;
	if ( NS_FAILED(rv) )
		return PyXPCOM_BuildPyException(rv);

	return Py_nsISupports::PyObjectFromInterface(cm, NS_GET_IID(nsISupports), false);
}

static PyObject *
PyXPCOMMethod_GetServiceManager(PyObject *self, PyObject *args)
{
	if (!PyArg_ParseTuple(args, ""))
		return NULL;
	nsCOMPtr<nsIServiceManager> sm;
	nsresult rv;
	Py_BEGIN_ALLOW_THREADS;
	rv = NS_GetServiceManager(getter_AddRefs(sm));
	Py_END_ALLOW_THREADS;
	if ( NS_FAILED(rv) )
		return PyXPCOM_BuildPyException(rv);

	// Return a type based on the IID.
	return Py_nsISupports::PyObjectFromInterface(sm, NS_GET_IID(nsIServiceManager));
}

static PyObject *
PyXPCOMMethod_XPTI_GetInterfaceInfoManager(PyObject *self, PyObject *args)
{
	if (!PyArg_ParseTuple(args, ""))
		return NULL;
	nsCOMPtr<nsIInterfaceInfoManager> im;
	Py_BEGIN_ALLOW_THREADS;
	im = do_GetService(NS_INTERFACEINFOMANAGER_SERVICE_CONTRACTID);
	Py_END_ALLOW_THREADS;
	if ( im == nullptr )
		return PyXPCOM_BuildPyException(NS_ERROR_FAILURE);

	/* Return a type based on the IID (with no extra ref) */
	// Can not auto-wrap the interface info manager as it is critical to
	// building the support we need for autowrap.
	return Py_nsISupports::PyObjectFromInterface(im, NS_GET_IID(nsIInterfaceInfoManager), false);
}

static PyObject *
PyXPCOMMethod_NS_InvokeByIndex(PyObject *self, PyObject *args)
{
	PyObject *obIS, *obParams;
	nsCOMPtr<nsISupports> pis;
	int index;

	// We no longer rely on PyErr_Occurred() for our error state,
	// but keeping this assertion can't hurt - it should still always be true!
	NS_ASSERTION(!PyErr_Occurred(), "Should be no pending Python error!");

	if (!PyArg_ParseTuple(args, "OiO", &obIS, &index, &obParams))
		return NULL;

	if (!Py_nsISupports::Check(obIS)) {
		return PyErr_Format(PyExc_TypeError,
		                    "First param must be a native nsISupports wrapper (got %s)",
		                    obIS->ob_type->tp_name);
	}
	// Ack!  We must ask for the "native" interface supported by
	// the object, not specifically nsISupports, else we may not
	// back the same pointer (eg, Python, following identity rules,
	// will return the "original" gateway when QI'd for nsISupports)
	if (!Py_nsISupports::InterfaceFromPyObject(
			obIS,
			Py_nsIID_NULL,
			getter_AddRefs(pis),
			false))
		return NULL;

	PyXPCOM_InterfaceVariantHelper arg_helper((Py_nsISupports *)obIS);
	if (!arg_helper.Init(obParams))
		return NULL;

	if (!arg_helper.PrepareCall())
		return NULL;

	nsresult r;
	Py_BEGIN_ALLOW_THREADS;
	r = NS_InvokeByIndex(pis, index,
	                     arg_helper.mDispatchParams.Length(),
	                     arg_helper.mDispatchParams.Elements());
	Py_END_ALLOW_THREADS;
	if ( NS_FAILED(r) )
		return PyXPCOM_BuildPyException(r);

	return arg_helper.MakePythonResult();
}

/**
 * Wrap the given Python object in a new XPCOM stub (and re-wrap it in python
 * in order to return it)
 * @see xpcom.server.WrapObject
 * @param ob the Python object to wrap
 * @param iid the IID to wrap as
 * @param bWrapClient [default true] whether to allow extra wrapping for Python
 * 	consumers
 * @note This always creates a new wrapper, which is unlikely to be what you want
 */
static PyObject *
PyXPCOMMethod_WrapObject(PyObject *self, PyObject *args)
{
	PyObject *ob, *obIID;
	int bWrapClient = 1;
	if (!PyArg_ParseTuple(args, "OO|i", &ob, &obIID, &bWrapClient))
		return NULL;

	nsIID	iid;
	if (!Py_nsIID::IIDFromPyObject(obIID, &iid))
		return NULL;

	nsCOMPtr<nsISupports> ret;
	nsresult r = PyXPCOM_XPTStub::CreateNew(ob, iid, getter_AddRefs(ret));
	if ( NS_FAILED(r) )
		return PyXPCOM_BuildPyException(r);

	// _ALL_ wrapped objects are associated with a weak-ref
	// to their "main" instance.
	AddDefaultGateway(ob, ret); // inject a weak reference to myself into the instance.

	// Now wrap it in an interface.
	return Py_nsISupports::PyObjectFromInterface(ret, iid, bWrapClient);
}

static PyObject *
PyXPCOMMethod_UnwrapObject(PyObject *self, PyObject *args)
{
	PyObject *ob;
	if (!PyArg_ParseTuple(args, "O", &ob))
		return NULL;

	nsISupports *uob = NULL;
	nsIInternalPython *iob = NULL;
	PyObject *ret = NULL;
	if (!Py_nsISupports::InterfaceFromPyObject(ob,
				NS_GET_IID(nsISupports),
				&uob,
				false))
		goto done;
	if (NS_FAILED(uob->QueryInterface(NS_GET_IID(nsIInternalPython), reinterpret_cast<void **>(&iob)))) {
		PyErr_SetString(PyExc_ValueError, "This XPCOM object is not implemented by Python");
		goto done;
	}
	ret = iob->UnwrapPythonObject();
done:
	Py_BEGIN_ALLOW_THREADS;
	NS_IF_RELEASE(uob);
	NS_IF_RELEASE(iob);
	Py_END_ALLOW_THREADS;
	return ret;
}

// @pymethod int|pythoncom|_GetInterfaceCount|Retrieves the number of interface objects currently in existance
static PyObject *
PyXPCOMMethod_GetInterfaceCount(PyObject *self, PyObject *args)
{
	// @comm It is occasionally a good idea to call this function before your Python program
	// terminates.  If this function returns non-zero, then you still have PythonCOM objects
	// alive in your program (possibly in global variables).
	if (!PyArg_ParseTuple(args, ":_GetInterfaceCount"))
		return NULL;
	return PyInt_FromLong(_PyXPCOM_GetInterfaceCount());
}

// @pymethod int|pythoncom|_GetGatewayCount|Retrieves the number of gateway objects currently in existance
static PyObject *
PyXPCOMMethod_GetGatewayCount(PyObject *self, PyObject *args)
{
	// @comm This is the number of Python object that implement COM servers which
	// are still alive (ie, serving a client).  The only way to reduce this count
	// is to have the process which uses these PythonCOM servers release its references.
	if (!PyArg_ParseTuple(args, ":_GetGatewayCount"))
		return NULL;
	return PyInt_FromLong(_PyXPCOM_GetGatewayCount());
}

static PyObject *
PyXPCOMMethod_NS_ShutdownXPCOM(PyObject *self, PyObject *args)
{
	if (!PyArg_ParseTuple(args, ":NS_ShutdownXPCOM"))
		return NULL;
	nsresult nr;
	Py_BEGIN_ALLOW_THREADS;
	nr = NS_ShutdownXPCOM(nullptr);
	Py_END_ALLOW_THREADS;
	// NS_ShutdownXPCOM will dispose of various services, so that might
	// itself release some things.  Only check for clean shutdown afterwards.
	MOZ_ASSERT(_PyXPCOM_GetInterfaceCount() == 0);
	MOZ_ASSERT(_PyXPCOM_GetGatewayCount() == 0);

	// Dont raise an exception - as we are probably shutting down
	// and dont really case - just return the status
	return PyInt_FromLong(static_cast<uint32_t>(nr));
}

static PyObject *
PyXPCOMMethod_MakeVariant(PyObject *self, PyObject *args)
{
	PyObject *ob;
	if (!PyArg_ParseTuple(args, "O:MakeVariant", &ob))
		return NULL;
	nsCOMPtr<nsIVariant> pVar;
	nsresult nr = PyObject_AsVariant(ob, getter_AddRefs(pVar));
	if (NS_FAILED(nr))
		return PyXPCOM_BuildPyException(nr);
	if (pVar == nullptr) {
		NS_ERROR("PyObject_AsVariant worked but returned a NULL ptr!");
		return PyXPCOM_BuildPyException(NS_ERROR_UNEXPECTED);
	}
	return Py_nsISupports::PyObjectFromInterface(pVar, NS_GET_IID(nsIVariant));
}

static PyObject *
PyXPCOMMethod_GetVariantValue(PyObject *self, PyObject *args)
{
	PyObject *ob, *obParent = NULL;
	if (!PyArg_ParseTuple(args, "O|O:GetVariantValue", &ob, &obParent))
		return NULL;

	nsCOMPtr<nsISupports> pSupports;
	if (!Py_nsISupports::InterfaceFromPyObject(ob,
				NS_GET_IID(nsISupports),
				getter_AddRefs(pSupports),
				false))
		return PyErr_Format(PyExc_ValueError,
				    "Object is not an nsISupports (got %s)",
				    ob->ob_type->tp_name);

	Py_nsISupports *parent = nullptr;
	if (obParent && obParent != Py_None) {
		if (!Py_nsISupports::Check(obParent)) {
			PyErr_SetString(PyExc_ValueError,
					"Object not an nsISupports wrapper");
			return NULL;
		}
		parent = (Py_nsISupports *)obParent;
	}
	nsCOMPtr<nsIVariant> var = do_QueryInterface(pSupports);
	if (!var) {
		return PyErr_Format(PyExc_ValueError,
				    "Object is not an nsIVariant (got %s)",
				    ob->ob_type->tp_name);
	}
	return PyObject_FromVariant(parent, var);
}

/**
 * Returns a list of registered category entries matching the given category.
 * The entries returned are space separated - e.g. "DATA CID".
 */
static PyObject *
PyXPCOMMethod_GetCategoryEntries(PyObject *self, PyObject *args)
{
	char *category;
	if (!PyArg_ParseTuple(args, "s:GetCategoryEntries", &category))
		return NULL;

	nsresult rv;

	nsCOMPtr<nsICategoryManager> categoryManager =
			do_GetService(NS_CATEGORYMANAGER_CONTRACTID, &rv);
	if (NS_FAILED(rv)) {
		return PyErr_Format(PyExc_RuntimeError,
				    "Unable to instantiate category manager");
	}

	nsCOMPtr<nsISimpleEnumerator> enumerator;
	rv = categoryManager->EnumerateCategory(category, getter_AddRefs(enumerator));
	if (NS_FAILED(rv)) {
		return PyErr_Format(PyExc_RuntimeError,
				    "Unable to enumerate category %s", category);
	}

	PyObject *ret = PyList_New(0);
	if (!ret) {
		return PyErr_Format(PyExc_RuntimeError,
				    "Unable to create category list");
	}

	PyObject *item;
	nsAutoCString fullString;
	nsAutoCString categoryEntry;
	nsCOMPtr<nsISupports> entry;
	while (NS_SUCCEEDED(enumerator->GetNext(getter_AddRefs(entry)))) {
	    nsCOMPtr<nsISupportsCString> categoryEntryCString = do_QueryInterface(entry, &rv);
	    if (NS_SUCCEEDED(rv)) {
		rv = categoryEntryCString->GetData(categoryEntry);
		fullString.Assign(categoryEntry);
		fullString += NS_LITERAL_CSTRING(" ");
		nsAutoCString contractId;
		categoryManager->GetCategoryEntry(category, 
						  categoryEntry.get(),
						  getter_Copies(contractId));
		fullString += contractId;
		item = PyObject_FromNSString(fullString);
		PyList_Append(ret, item);
		Py_XDECREF(item);
	    }
	}

	return ret;
}

PyObject *PyGetSpecialDirectory(PyObject *self, PyObject *args)
{
	char *dirname;
	if (!PyArg_ParseTuple(args, "s:GetSpecialDirectory", &dirname))
		return NULL;
	nsCOMPtr<nsIFile> file;
	nsresult r;
	Py_BEGIN_ALLOW_THREADS;
	NS_GetSpecialDirectory(dirname, getter_AddRefs(file));
	Py_END_ALLOW_THREADS;
	if ( NS_FAILED(r) )
		return PyXPCOM_BuildPyException(r);
	// returned object swallows our reference.
	return Py_nsISupports::PyObjectFromInterface(file, NS_GET_IID(nsIFile));
}

PyObject *AllocateBuffer(PyObject *self, PyObject *args)
{
	int bufSize;
	if (!PyArg_ParseTuple(args, "i", &bufSize))
		return NULL;
	return PyBuffer_New(bufSize);
}

// Writes a message to the console service.  This could be done via pure
// Python code, but is useful when the logging code is actually the
// xpcom .py framework itself (ie, we don't want our logging framework to
// call back into the very code generating the log messages!
PyObject *LogConsoleMessage(PyObject *self, PyObject *args)
{
	char *msg;
	if (!PyArg_ParseTuple(args, "s", &msg))
		return NULL;

	Py_BEGIN_ALLOW_THREADS;
	nsCOMPtr<nsIConsoleService> consoleService = do_GetService(NS_CONSOLESERVICE_CONTRACTID);
	if (consoleService)
		consoleService->LogStringMessage(NS_ConvertASCIItoUTF16(msg).get());
	else {
	// This either means no such service, or in shutdown - hardly worth
	// the warning, and not worth reporting an error to Python about - its
	// log handler would just need to catch and ignore it.
	// And as this is only called by this logging setup, any messages should
	// still go to stderr or a logfile.
		NS_WARNING("pyxpcom can't log console message.");
	}
	Py_END_ALLOW_THREADS;

	Py_INCREF(Py_None);
	return Py_None;
}

#if DEBUG
// Break into the (C++) debugger
PyObject *PyXPCOMMethod__Break(PyObject *self, PyObject *args)
{
	#if defined(XP_WIN)
		::DebugBreak();
	#elif defined(XP_UNIX)
		raise(SIGTRAP);
	#else
		PyErr_SetString(PyExc_RuntimeError,
		                "_xpcom._Break is not implemented!");
		return nullptr;
	#endif
	Py_INCREF(Py_None);
	return Py_None;
}
#endif /* DEBUG */

extern PyObject *PyXPCOMMethod_IID(PyObject *self, PyObject *args);

static struct PyMethodDef xpcom_methods[]=
{
	{"GetComponentManager", PyXPCOMMethod_GetComponentManager, 1},
	{"GetComponentRegistrar", PyXPCOMMethod_GetComponentRegistrar, 1},
	{"XPTI_GetInterfaceInfoManager", PyXPCOMMethod_XPTI_GetInterfaceInfoManager, 1},
	{"NS_InvokeByIndex", PyXPCOMMethod_NS_InvokeByIndex, 1},
	{"GetServiceManager", PyXPCOMMethod_GetServiceManager, 1},
	{"IID", PyXPCOMMethod_IID, 1}, // IID is wrong - deprecated - not just IID, but CID, etc.
	{"ID", PyXPCOMMethod_IID, 1}, // This is the official name.
	{"NS_ShutdownXPCOM", PyXPCOMMethod_NS_ShutdownXPCOM, 1},
	{"WrapObject", PyXPCOMMethod_WrapObject, 1},
	{"UnwrapObject", PyXPCOMMethod_UnwrapObject, 1},
	{"_GetInterfaceCount", PyXPCOMMethod_GetInterfaceCount, 1},
	{"_GetGatewayCount", PyXPCOMMethod_GetGatewayCount, 1},
	{"GetSpecialDirectory", PyGetSpecialDirectory, 1},
	{"AllocateBuffer", AllocateBuffer, 1},
	{"LogConsoleMessage", LogConsoleMessage, 1, "Write a message to the xpcom console service"},
	{"MakeVariant", PyXPCOMMethod_MakeVariant, 1},
	{"GetVariantValue", PyXPCOMMethod_GetVariantValue, 1},
	{"GetCategoryEntries", PyXPCOMMethod_GetCategoryEntries, 1},
	#if DEBUG
		{"_Break", PyXPCOMMethod__Break, 1, "Break into the C++ debugger"},
	#endif
	{ NULL }
};

#define REGISTER_IID(t) { \
	PyObject *iid_ob = Py_nsIID::PyObjectFromIID(NS_GET_IID(t)); \
	PyDict_SetItemString(dict, "IID_"#t, iid_ob); \
	Py_DECREF(iid_ob); \
	}

#define REGISTER_INT(val) { \
	PyObject *ob = PyInt_FromLong(val); \
	PyDict_SetItemString(dict, #val, ob); \
	Py_DECREF(ob); \
	}

#if PYXPCOM_DEBUG_INTERFACE_COUNT || PYXPCOM_DEBUG_GATEWAY_COUNT
	FILE *gDebugCountLog = nullptr;
#endif /* PYXPCOM_DEBUG_INTERFACE_COUNT || PYXPCOM_DEBUG_GATEWAY_COUNT */

////////////////////////////////////////////////////////////
// The module init code.
//
extern "C" NS_EXPORT
bool
init_xpcom_real() {
    #if PYXPCOM_DEBUG_INTERFACE_COUNT || PYXPCOM_DEBUG_GATEWAY_COUNT
    {
        const char* tmpdir = PR_GetEnv("TEMP");
        const char kLogName[] = "/pyxpcom.debug-count.log";
        if (!tmpdir || !*tmpdir) {
            tmpdir = PR_GetEnv("TMP");
        }
        if (!tmpdir || !*tmpdir) {
            tmpdir = "/tmp";
        }
        size_t bufsize = strlen(tmpdir) + sizeof(kLogName) + 1;
        char* buf = (char*)moz_xmalloc(bufsize);
        PR_snprintf(buf, bufsize - 1, "%s%s", tmpdir, kLogName);
        buf[bufsize - 1] = '\0';
        gDebugCountLog = fopen(buf, "w");
    }
    #endif /* PYXPCOM_DEBUG_INTERFACE_COUNT || PYXPCOM_DEBUG_GATEWAY_COUNT */

    PyObject *oModule;

    // ensure the framework has valid state to work with.
    PyXPCOM_EnsurePythonEnvironment();

    // Must force Python to start using thread locks
    PyEval_InitThreads();

    // Create the module and add the functions
    oModule = Py_InitModule("_xpcom", xpcom_methods);

    PyObject *dict = PyModule_GetDict(oModule);
    PyObject *pycom_Error = PyXPCOM_Error;
    if (pycom_Error == NULL || PyDict_SetItemString(dict, "error", pycom_Error) != 0)
    {
            PyErr_SetString(PyExc_MemoryError, "can't define \"error\"");
            return false;
    }
    PyDict_SetItemString(dict, "IIDType", (PyObject *)&Py_nsIID::type);

    REGISTER_IID(nsISupports);
    REGISTER_IID(nsISupportsCString);
    REGISTER_IID(nsISupportsString);
    REGISTER_IID(nsIModule);
    REGISTER_IID(nsIFactory);
    REGISTER_IID(nsIWeakReference);
    REGISTER_IID(nsISupportsWeakReference);
    REGISTER_IID(nsIClassInfo);
    REGISTER_IID(nsIServiceManager);
    REGISTER_IID(nsIComponentRegistrar);

    // Register our custom interfaces.
    REGISTER_IID(nsIComponentManager);
    REGISTER_IID(nsIInterfaceInfoManager);
    REGISTER_IID(nsIEnumerator);
    REGISTER_IID(nsISimpleEnumerator);
    REGISTER_IID(nsIInterfaceInfo);
    REGISTER_IID(nsIInputStream);
    REGISTER_IID(nsIClassInfo);
    REGISTER_IID(nsIVariant);

    // No good reason not to expose this impl detail, and tests can use it
    REGISTER_IID(nsIInternalPython);

    // Build flags that may be useful.
    PyObject *ob = PyBool_FromLong(
    #if defined(NS_DEBUG)
                                   1
    #else
                                   0
    #endif
                                   );
    PyDict_SetItemString(dict, "NS_DEBUG", ob);
    Py_DECREF(ob);
    // Flag we initialized correctly!
    PyXPCOM_ModuleInitialized = true;
    return true;
}
