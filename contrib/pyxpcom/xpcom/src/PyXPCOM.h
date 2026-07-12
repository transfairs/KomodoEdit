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

// PyXPCOM.h - the main header file for the Python XPCOM support.
//
// This code is part of the XPCOM extensions for Python.
//
// Written May 2000 by Mark Hammond.
//
// Based heavily on the Python COM support, which is
// (c) Mark Hammond and Greg Stein.
//
// (c) 2000, ActiveState corp.

#ifndef __PYXPCOM_H__
#define __PYXPCOM_H__

#include "mozilla/mozalloc.h"
#include "nsMemory.h"
#include "nsIWeakReference.h"
#include "nsIInterfaceInfo.h"
#include "nsIInterfaceInfoManager.h"
#include "nsIClassInfo.h"
#include "nsIComponentManager.h"
#include "nsComponentManagerUtils.h" // do_CreateInstance
#include "nsIServiceManager.h"
#include "nsIEnumerator.h"
#include "nsISimpleEnumerator.h"
#include "nsIInputStream.h"
#include "nsIVariant.h"
#include "nsIModule.h"
#include "nsServiceManagerUtils.h"
#include "nsStringAPI.h"

#include "nsCRT.h"
#if defined(__clang__)
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wreturn-type-c-linkage"
#endif /* __clang__ */
#include "nsXPTCUtils.h"
#if defined(__clang__)
#pragma clang diagnostic pop
#endif /* __clang__ */
#include "xpt_xdr.h"

#ifdef HAVE_LONG_LONG
	// Mozilla also defines this - we undefine it to
	// prevent a compiler warning.
#	undef HAVE_LONG_LONG
#endif // HAVE_LONG_LONG

#ifdef _POSIX_C_SOURCE // Ditto here
#	undef _POSIX_C_SOURCE
#endif // _POSIX_C_SOURCE

#include <Python.h>

// python 2.4 doesn't have Py_ssize_t
// => fallback to int
#if PY_VERSION_HEX < 0x02050000 && !defined(PY_SSIZE_T_MIN)
typedef int Py_ssize_t;
#endif

// PYXPCOM_EXPORT means 'exported from the pyxpcom core lib' - which changes
// spelling depending on whether pyxpcom is being built or just referenced.
#ifdef BUILD_PYXPCOM
    /* We are building the main dll */
#   define PYXPCOM_EXPORT NS_EXPORT
#else
    /* This module uses the dll */
#   define PYXPCOM_EXPORT NS_IMPORT
#endif // BUILD_PYXPCOM

#ifdef DEBUG
	/* for Alloc/Free (memory leak tracking) */
#	include <nsClassHashtable.h>
#endif

// An IID we treat as NULL when passing as a reference.
extern nsIID Py_nsIID_NULL;

class Py_nsISupports;

/*************************************************************************
**************************************************************************

 Error and exception related function.

**************************************************************************
*************************************************************************/

#define NS_PYXPCOM_NO_SUCH_METHOD \
  NS_ERROR_GENERATE_SUCCESS(NS_ERROR_MODULE_PYXPCOM, 0)

// The exception object (loaded from the xpcom .py code)
extern PyObject *PyXPCOM_Error;

// A boolean flag indicating if the _xpcom module has been successfully
// imported.  Mainly used to handle errors at startup - if this module
// hasn't been imported yet, we don't try and use the logging module
// for error messages (as that process itself needs the module!)
extern bool PyXPCOM_ModuleInitialized;

// Client related functions - generally called by interfaces before
// they return NULL back to Python to indicate the error.
// All these functions return NULL so interfaces can generally
// just "return PyXPCOM_BuildPyException(hr, punk, IID_IWhatever)"
PyObject *PyXPCOM_BuildPyException(nsresult res);

// Used in gateways to handle the current Python exception
// NOTE: this function assumes it is operating within the Python context
PYXPCOM_EXPORT nsresult PyXPCOM_SetCOMErrorFromPyException();

// Write current exception and traceback to a string.
bool PyXPCOM_FormatCurrentException(nsCString &streamout);
// Write specified exception and traceback to a string.
bool PyXPCOM_FormatGivenException(nsCString &streamout,
                                PyObject *exc_typ, PyObject *exc_val,
                                PyObject *exc_tb);

// A couple of logging/error functions.  These now end up being written
// via the logging module, and via handlers added by the xpcom package,
// then are written to the JSConsole and the ConsoleService.

// Log a warning for the user - something at runtime
// they may care about, but nothing that prevents us actually
// working.
// As it's designed for user error/warning, it exists in non-debug builds.
void PyXPCOM_LogWarning(const char *fmt, ...);

// Log an error for the user - something that _has_ prevented
// us working.  This is probably accompanied by a traceback.
// As it's designed for user error/warning, it exists in non-debug builds.
PYXPCOM_EXPORT void PyXPCOM_LogError(const char *fmt, ...);

// The raw one
void PyXPCOM_Log(const char *level, const nsCString &msg);

#ifdef DEBUG
// Mainly designed for developers of the XPCOM package.
// Only enabled in debug builds.
void PyXPCOM_LogDebug(const char *fmt, ...);
#define PYXPCOM_LOG_DEBUG PyXPCOM_LogDebug
#else
#define PYXPCOM_LOG_DEBUG()
#endif // DEBUG

// Some utility converters
// moz strings to PyObject.
PyObject *PyObject_FromNSString( const nsACString &s,
                                                bool bAssumeUTF8 = false );
PyObject *PyObject_FromNSString( const nsAString &s );
PyObject *PyObject_FromNSString( const char16_t *s,
                                                PRUint32 len = (PRUint32)-1);

// PyObjects to moz strings.  As per the moz string guide, we pass a reference
// to an abstract string
bool PyObject_AsNSString( PyObject *ob, nsAString &aStr);

// Variants.
nsresult PyObject_AsVariant( PyObject *ob, nsIVariant **aRet);
PyObject *PyObject_FromVariant( Py_nsISupports *parent,
                                               nsIVariant *v);

// Interfaces - these are the "official" functions
PyObject *PyObject_FromNSInterface( nsISupports *aInterface,
                                                   const nsIID &iid, 
                                                   bool bMakeNicePyObject = true);

/*************************************************************************
**************************************************************************

 Support for CALLING (ie, using) interfaces.

**************************************************************************
*************************************************************************/

typedef Py_nsISupports* (* PyXPCOM_I_CTOR)(nsISupports *, const nsIID &);

//////////////////////////////////////////////////////////////////////////
// class PyXPCOM_TypeObject
// Base class for (most of) the type objects.

class PyXPCOM_TypeObject : public PyTypeObject {
public:
	PyXPCOM_TypeObject( 
		const char *name, 
		PyXPCOM_TypeObject *pBaseType, 
		int typeSize, 
		struct PyMethodDef* methodList,
		PyXPCOM_I_CTOR ctor);
	~PyXPCOM_TypeObject();

	PyMethodChain chain;
	PyXPCOM_TypeObject *baseType;
	PyXPCOM_I_CTOR ctor;

	static bool IsType(PyTypeObject *t);
	// Static methods for the Python type.
	static void Py_dealloc(PyObject *ob);
	static PyObject *Py_repr(PyObject *ob);
	static PyObject *Py_str(PyObject *ob);
	static PyObject *Py_getattr(PyObject *self, char *name);
	static int Py_setattr(PyObject *op, char *name, PyObject *v);
	static int Py_cmp(PyObject *ob1, PyObject *ob2);
	static long Py_hash(PyObject *self);
};

//////////////////////////////////////////////////////////////////////////
// class Py_nsISupports
// This class serves 2 purposes:
// * It is a base class for other interfaces we support "natively"
// * It is instantiated for _all_ other interfaces.
//
// This is different than win32com, where a PyIUnknown only
// ever holds an IUnknown - but here, we could be holding
// _any_ interface.
class PYXPCOM_EXPORT Py_nsISupports : public PyObject
{
public:
	// Check if a Python object can safely be cast to an Py_nsISupports,
	// and optionally check that the object is wrapping the specified
	// interface.
	static bool Check( PyObject *ob, const nsIID &checkIID = Py_nsIID_NULL) {
		Py_nsISupports *self = static_cast<Py_nsISupports *>(ob);
		if (ob==NULL || !PyXPCOM_TypeObject::IsType(ob->ob_type ))
			return false;
		if (!checkIID.Equals(Py_nsIID_NULL))
			return self->m_iid.Equals(checkIID) != 0;
		return true;
	}
	// Get the nsISupports interface from the PyObject WITH NO REF COUNT ADDED
	static nsISupports *GetI(PyObject *self, nsIID *ret_iid = NULL);
	nsCOMPtr<nsISupports> m_obj;
	nsIID m_iid;

	// Given an nsISupports and an Interface ID, create and return an object
	// Does not QI the object - the caller must ensure the nsISupports object
	// is really a pointer to an object identified by the IID (although
	// debug builds should check this)
	// bool bMakeNicePyObject indicates if we should call back into
	//  Python to wrap the object.  This allows Python code to
	//  see the correct xpcom.client.Interface object even when calling
	//  xpcom functions directly from C++.
	// NOTE: There used to be a bAddRef param to this as an internal
	// optimization, but  since removed.  This function *always* takes a
	// reference to the nsISupports.
	static PyObject *PyObjectFromInterface(nsISupports *ps, 
	                                       const nsIID &iid, 
	                                       bool bMakeNicePyObject = true,
	                                       bool bIsInternalCall = false);

	// Given a Python object that is a registered COM type, return a given
	// interface pointer on its underlying object, with a NEW REFERENCE ADDED.
	// bTryAutoWrap indicates if a Python instance object should attempt to
	//  be automatically wrapped in an XPCOM object.  This is really only
	//  provided to stop accidental recursion should the object returned by
	//  the wrap process itself be in instance (where it should already be
	//  a COM object.
	// If |iid|==nsIVariant, then arbitary Python objects will be wrapped
	// in an nsIVariant.
	static bool InterfaceFromPyObject(
		PyObject *ob,
		const nsIID &iid,
		nsISupports **ppret,
		bool bNoneOK,
		bool bTryAutoWrap = true);

	// Given a Py_nsISupports, return an interface.
	// Object *must* be Py_nsISupports - there is no
	// "autowrap", no "None" support, etc
	static bool InterfaceFromPyISupports(PyObject *ob, 
	                                       const nsIID &iid, 
	                                       nsISupports **ppv);

	static Py_nsISupports *Constructor(nsISupports *pInitObj, const nsIID &iid);
	// The Python methods
	static PyObject *QueryInterface(PyObject *self, PyObject *args);

	// Internal (sort-of) objects.
	static NS_EXPORT_STATIC_MEMBER_(PyXPCOM_TypeObject) *type;
	static NS_EXPORT_STATIC_MEMBER_(PyMethodDef) methods[];
	static PyObject *mapIIDToType;
	static void SafeRelease(Py_nsISupports *ob);
	static void RegisterInterface( const nsIID &iid, PyTypeObject *t);
	static void InitType();

	virtual ~Py_nsISupports();
	virtual PyObject *getattr(const char *name);
	virtual int setattr(const char *name, PyObject *val);
	// A virtual function to sub-classes can customize the way
	// nsISupports objects are returned from their methods.
	// ps is a new object just obtained from some operation performed on us
	virtual PyObject *MakeInterfaceResult(nsISupports *ps, const nsIID &iid,
	                                      bool bMakeNicePyObject = true) {
		return PyObjectFromInterface(ps, iid, bMakeNicePyObject);
	}

protected:
	// ctor is protected - must create objects via
	// PyObjectFromInterface()
	Py_nsISupports(nsISupports *p, 
		            const nsIID &iid, 
			    PyTypeObject *type);

	// Make a default wrapper for an ISupports (which is an
	// xpcom.client.Component instance)
	static PyObject *MakeDefaultWrapper(PyObject *pyis, const nsIID &iid);

};

// Python/XPCOM IID support 
class PYXPCOM_EXPORT Py_nsIID : public PyObject
{
public:
	Py_nsIID(const nsIID &riid);
	nsIID m_iid;

	bool 
	IsEqual(const nsIID &riid) {
		return m_iid.Equals(riid);
	}

	bool
	IsEqual(PyObject *ob) {
		return ob && 
		       ob->ob_type== &type && 
		       m_iid.Equals(((Py_nsIID *)ob)->m_iid);
	}

	bool
	IsEqual(Py_nsIID &iid) {
		return m_iid.Equals(iid.m_iid);
	}

	static PyObject *
	PyObjectFromIID(const nsIID &iid) {
		return new Py_nsIID(iid);
	}

	static bool IIDFromPyObject(PyObject *ob, nsIID *pRet);
	/* Python support */
	static PyObject *PyTypeMethod_getattr(PyObject *self, char *name);
	static int PyTypeMethod_compare(PyObject *self, PyObject *ob);
	static PyObject *PyTypeMethod_repr(PyObject *self);
	static long PyTypeMethod_hash(PyObject *self);
	static PyObject *PyTypeMethod_str(PyObject *self);
	static void PyTypeMethod_dealloc(PyObject *self);
	static NS_EXPORT_STATIC_MEMBER_(PyTypeObject) type;
	static NS_EXPORT_STATIC_MEMBER_(PyMethodDef) methods[];
};


/**
 * Helper class for leak tracking
 * Pretty much debug-only
 */
class PyXPCOM_AllocHelper {
protected:
	#ifdef DEBUG
	PyXPCOM_AllocHelper() {
		mAllocations.Init();
	}
	~PyXPCOM_AllocHelper();
	struct LineRef {
		const char* file;
		const unsigned line;
		LineRef(const char* aFile, const unsigned aLine)
			: file(aFile), line(aLine) {}
	};
	nsClassHashtable<nsPtrHashKey<void>, LineRef> mAllocations;
	template<typename T> MOZ_ALWAYS_INLINE
	T* Alloc(T*& dest, size_t count, const char* file, const unsigned line);
	MOZ_ALWAYS_INLINE void* Alloc(size_t size, size_t count, const char* file, const unsigned line);
	MOZ_ALWAYS_INLINE void MarkAlloc(void* buf, const char* file, const unsigned line);
	template<typename T> MOZ_ALWAYS_INLINE void Free(T* buf);
	MOZ_ALWAYS_INLINE void Free(void* buf);
	MOZ_ALWAYS_INLINE void MarkFree(void* buf);
	static PLDHashOperator ReadAllocation(void* key, LineRef* value, void* userData);
	#else
	template<typename T>
	MOZ_ALWAYS_INLINE T* Alloc(T*& dest, size_t count, const char*, const unsigned) {
		dest = reinterpret_cast<T*>(moz_calloc(sizeof(T), count));
		for (size_t i = 0; i < count; ++i)
			new (&dest[i]) T();
		return dest;
	}
	MOZ_ALWAYS_INLINE void* Alloc(size_t size, size_t count, const char*, const unsigned) {
		return moz_calloc(size, count);
	}
	MOZ_ALWAYS_INLINE void MarkAlloc(void*, const char*, const unsigned) {}
	template<typename T>
	MOZ_ALWAYS_INLINE void Free(T* buf) {
		delete[] buf;
	}
	MOZ_ALWAYS_INLINE void Free(void* buf) {
		moz_free(buf);
	}
	MOZ_ALWAYS_INLINE void MarkFree(void* buf) {}
	#endif
};


///////////////////////////////////////////////////////
//
// Helper classes for managing arrays of variants.
// ------------------------------------------------------------------------
// TypeDescriptor helper class
// ------------------------------------------------------------------------
class PythonTypeDescriptor {
public:
	PythonTypeDescriptor() {
		param_flags = argnum = argnum2 = 0;
		type_flags = TD_VOID;
		iid = NS_GET_IID(nsISupports); // always a valid IID
		array_type = 0;
		is_auto_in = false;
		is_auto_out = false;
		have_set_auto = false;
	}
	~PythonTypeDescriptor() {
	}
	uint8_t param_flags;  // XPT_PD_*
	uint8_t type_flags;   // XPT_TDP_TAG + XPT_TDP_* flags
	union {
		uint8_t argnum;
		uint8_t iid_is;
		uint8_t size_is;
	};
	union {
		uint8_t argnum2;
		uint8_t length_is;
	};
	uint8_t array_type; // The type of the array.
	nsID iid; // The IID of the object or each elt of the array.
	// Extra items to help our processing.
	// Is this auto-filled by some other "in" param?
	bool is_auto_in;
	// Is this auto-filled by some other "out" param?
	// (This can't be merged with is_auto_in because things might be auto in
	// only one direction, e.g. in unsigned int count + out array size_is(count) )
	bool is_auto_out;
	// If is_auto_out, have I already filled it?  Used when multiple
	// params share a size_is fields - first time sets it, subsequent
	// time check it.
	bool have_set_auto;

	///// Accessor helpers

	// Nothing should be using the flag parts of type_flags, see Mozilla bug 692342
	uint8_t TypeFlags() const {
		return this->type_flags & XPT_TDP_FLAGMASK;
	}
	XPTTypeDescriptorTags TypeTag() const {
		return static_cast<XPTTypeDescriptorTags>(this->type_flags & XPT_TDP_TAGMASK);
	}
	uint8_t ArrayTypeFlags() const {
		return this->array_type & XPT_TDP_FLAGMASK;
	}
	XPTTypeDescriptorTags ArrayTypeTag() const {
		return static_cast<XPTTypeDescriptorTags>(this->array_type & XPT_TDP_TAGMASK);
	}

	// NOTE: these are deprecated and should only be used in assertions
	// (See Mozilla bug 692342)
	MOZ_ALWAYS_INLINE bool IsPointer()   const { return 0 != (XPT_TDP_IS_POINTER(type_flags)); }
	MOZ_ALWAYS_INLINE bool IsReference() const { return 0 != (XPT_TDP_IS_REFERENCE(type_flags)); }

	MOZ_ALWAYS_INLINE bool IsIn()        const { return 0 != (XPT_PD_IS_IN(param_flags)) ; }
	MOZ_ALWAYS_INLINE bool IsOut()       const { return 0 != (XPT_PD_IS_OUT(param_flags)) ; }
	MOZ_ALWAYS_INLINE bool IsRetval()    const { return 0 != (XPT_PD_IS_RETVAL(param_flags)) ; }
	MOZ_ALWAYS_INLINE bool IsShared()    const { return 0 != (XPT_PD_IS_SHARED(param_flags)) ; }
	MOZ_ALWAYS_INLINE bool IsDipper()    const { return 0 != (XPT_PD_IS_DIPPER(param_flags)) ; }
	MOZ_ALWAYS_INLINE bool IsOptional()  const { return 0 != (XPT_PD_IS_OPTIONAL(param_flags)) ; }

	// These are just to match the style
	MOZ_ALWAYS_INLINE bool IsAutoIn()    const { return is_auto_in; }
	MOZ_ALWAYS_INLINE bool IsAutoOut()   const { return is_auto_out; }
	MOZ_ALWAYS_INLINE bool IsAutoSet()   const { return have_set_auto; }

	#if DEBUG
	bool IsDipperType() const {
		switch (TypeTag()) {
			case TD_DOMSTRING:
			case TD_UTF8STRING:
			case TD_CSTRING:
			case TD_ASTRING:
				return true;
			default:
				return false;
		}
	}
	// Debugging helper; never called in code.  This will leak.
	MOZ_NEVER_INLINE char* Describe() const;
	MOZ_NEVER_INLINE char* Describe(const nsXPTCVariant&) const;
	#endif
};

class PyXPCOM_InterfaceVariantHelper : public PyXPCOM_AllocHelper {
public:
	PyXPCOM_InterfaceVariantHelper(Py_nsISupports *parent);
	~PyXPCOM_InterfaceVariantHelper();
	bool Init(PyObject *obParams);
	/**
	 * Prepare for the call; this converts the params, etc.
	 */
	bool PrepareCall();

	PyObject *MakePythonResult();

	// The array of variants to pass to XPTCall
	nsAutoTArray<nsXPTCVariant, 8> mDispatchParams;
protected:
	PyObject *MakeSinglePythonResult(int index);
	/**
	 * Fill in a single variant value
	 * @param td The type descriptor about the parameter we need to fill
	 * @param value_index The index of the params (incl. hidden) we are filling
	 * @param param_index The index in m_pyparams to gather the Python argument from
	 * @postcondition m_var_array[value_index] is ready for call
	 */
	bool FillInVariant(const PythonTypeDescriptor &td, int value_index, int param_index);
	/**
	 * Allocate space for 'out' parameters
	 * @param td The type descriptor about the parameter
	 * @param value_index The index of params (incl. hidden) we are filling
	 * @postcondition m_var_array[value_index] is ready for call
	 */
	bool PrepareOutVariant(const PythonTypeDescriptor &td, int value_index);
	bool SetSizeOrLengthIs(int var_index, bool is_size, uint32_t new_size);
	uint32_t GetSizeOrLengthIs(int var_index, bool is_size);
	MOZ_ALWAYS_INLINE bool SetSizeIs(int var_index, uint32_t new_size) {
		return SetSizeOrLengthIs(var_index, true, new_size);
	}
	MOZ_ALWAYS_INLINE bool SetLengthIs(int var_index, uint32_t new_size) {
		return SetSizeOrLengthIs(var_index, false, new_size);
	}
	MOZ_ALWAYS_INLINE uint32_t GetSizeIs(int var_index) {
		return GetSizeOrLengthIs(var_index, true);
	}
	MOZ_ALWAYS_INLINE uint32_t GetLengthIs(int var_index) {
		return GetSizeOrLengthIs(var_index, false);
	}

	/**
	 * Clean up a single nsXPTCMiniVariant (free memory as appropriate)
	 */
	void CleanupParam(void* p, nsXPTType& type);

	PyObject *m_pyparams; // sequence of actual params passed (ie, not including hidden)

	nsTArray<PythonTypeDescriptor> mPyTypeDesc; // type descriptors for all params

	// The XPCOM interface this method is being called on
	// (This holds a strong reference)
	Py_nsISupports *m_parent;

};

/*************************************************************************
**************************************************************************

 Support for IMPLEMENTING interfaces.

**************************************************************************
*************************************************************************/
#define NS_IINTERNALPYTHON_IID_STR "AC7459FC-E8AB-4f2e-9C4F-ADDC53393A20"
#define NS_IINTERNALPYTHON_IID \
	{ 0xac7459fc, 0xe8ab, 0x4f2e, { 0x9c, 0x4f, 0xad, 0xdc, 0x53, 0x39, 0x3a, 0x20 } }

// This interface is needed primarily to give us a known vtable base.
// If we QI a Python object for this interface, we can safely cast the result
// to a PyG_Base.  Any other interface, we do now know which vtable we will get.
// We also allow the underlying PyObject to be extracted
class nsIInternalPython : public nsISupports {
public: 
	NS_DECLARE_STATIC_IID_ACCESSOR(NS_IINTERNALPYTHON_IID)
	// Get the underlying Python object with new reference added
	virtual PyObject *UnwrapPythonObject(void) = 0;
};

NS_DEFINE_STATIC_IID_ACCESSOR(nsIInternalPython, NS_IINTERNALPYTHON_IID)

// This is roughly equivalent to PyGatewayBase in win32com
//
class PyG_Base : public nsIInternalPython, public nsISupportsWeakReference
{
public:
	NS_DECL_THREADSAFE_ISUPPORTS
	NS_DECL_NSISUPPORTSWEAKREFERENCE
	PyObject *UnwrapPythonObject(void);

	// A static "constructor" - the real ctor is protected.
	static nsresult CreateNew(PyObject *pPyInstance, 
		                  const nsIID &iid, 
				  void **ppResult);

	// A utility to auto-wrap an arbitary Python instance 
	// in a COM gateway.
	static bool AutoWrapPythonInstance(PyObject *ob, 
		                           const nsIID &iid, 
					   nsISupports **ppret);


	// A helper that creates objects to be passed for nsISupports
	// objects.  See extensive comments in PyG_Base.cpp.
	PyObject *MakeInterfaceParam(nsISupports *pis, 
	                                     const nsIID *piid, 
					     int methodIndex = -1,
					     const XPTParamDescriptor *d = NULL, 
					     int paramIndex = -1);

	// A helper that ensures all casting and vtable offsetting etc
	// done against this object happens in the one spot!
	virtual void *ThisAsIID( const nsIID &iid ) = 0;

	// Helpers for "native" interfaces.
	// Not used by the generic stub interface.
	nsresult HandleNativeGatewayError(const char *szMethodName);

	// These data members used by the converter helper functions - hence public
	nsIID m_iid;
	PyObject * m_pPyObject;
	// We keep a reference count on this object, and the object
	// itself uses normal refcount rules - thus, it will only
	// die when we die, and all external references are removed.
	// This means that once we have created it (and while we
	// are alive) it will never die.
	nsCOMPtr<nsIWeakReference> m_pWeakRef;
#ifdef NS_BUILD_REFCNT_LOGGING
	char refcntLogRepr[64]; // sigh - I wish I knew how to use the Moz string classes :(  OK for debug only tho.
#endif
protected:
	PyG_Base(PyObject *instance, const nsIID &iid);
	virtual ~PyG_Base();
	PyG_Base *m_pBaseObject; // A chain to implement identity rules.
	nsresult InvokeNativeViaPolicy(	const char *szMethodName,
			PyObject **ppResult = NULL,
			const char *szFormat = NULL,
			...
			);
	nsresult InvokeNativeViaPolicyInternal(	const char *szMethodName,
			PyObject **ppResult,
			const char *szFormat,
			va_list va);
};

class PyXPCOM_XPTStub : public PyG_Base, public nsAutoXPTCStub
{
friend class PyG_Base;
public:
	NS_IMETHOD QueryInterface(REFNSIID aIID, void** aInstancePtr)
		{return PyG_Base::QueryInterface(aIID, aInstancePtr);}
	NS_IMETHOD_(MozExternalRefCountType) AddRef(void) {return PyG_Base::AddRef();}
	NS_IMETHOD_(MozExternalRefCountType) Release(void) {return PyG_Base::Release();}

	// call this method and return result
	NS_IMETHOD CallMethod(PRUint16 methodIndex,
                          const XPTMethodDescriptor* info,
                          nsXPTCMiniVariant* params);

	virtual void *ThisAsIID(const nsIID &iid);
protected:
	PyXPCOM_XPTStub(PyObject *instance, const nsIID &iid);
	~PyXPCOM_XPTStub();
	
	// This is used to make sure QIing to the same interface returns the
	// same pointer; necessary to match xpconnect semantics.
	PyXPCOM_XPTStub* m_pNextObject;
private:
};

// For the Gateways we manually implement.
#define PYGATEWAY_BASE_SUPPORT(INTERFACE, GATEWAY_BASE)                    \
	NS_IMETHOD QueryInterface(REFNSIID aIID, void** aInstancePtr)      \
		{return PyG_Base::QueryInterface(aIID, aInstancePtr);}     \
	NS_IMETHOD_(MozExternalRefCountType) AddRef(void) {return PyG_Base::AddRef();}    \
	NS_IMETHOD_(MozExternalRefCountType) Release(void) {return PyG_Base::Release();}  \
	virtual void *ThisAsIID(const nsIID &iid) {                        \
		if (iid.Equals(NS_GET_IID(INTERFACE))) return (INTERFACE *)this; \
		return GATEWAY_BASE::ThisAsIID(iid);                       \
	}                                                                  \

extern void AddDefaultGateway(PyObject *instance, nsISupports *gateway);

extern PRInt32 _PyXPCOM_GetGatewayCount(void);
extern PRInt32 _PyXPCOM_GetInterfaceCount(void);


// Weak Reference class.  This is a true COM object, representing
// a weak reference to a Python object.  For each Python XPCOM object,
// there is exactly zero or one corresponding weak reference instance.
// When both are alive, each holds a pointer to the other.  When the main
// object dies due to XPCOM reference counting, it zaps the pointer
// in its corresponding weak reference object.  Thus, the weak-reference
// can live beyond the XPCOM object (possibly with a NULL pointer back to the 
// "real" object, but as implemented, the weak reference will never be 
// destroyed  before the object
class PyXPCOM_GatewayWeakReference : public nsIWeakReference {
public:
	PyXPCOM_GatewayWeakReference(PyG_Base *base);
	NS_DECL_THREADSAFE_ISUPPORTS
	NS_DECL_NSIWEAKREFERENCE
	virtual size_t SizeOfOnlyThis(mozilla::MallocSizeOf aMallocSizeOf) const;
	PyG_Base *m_pBase; // NO REF COUNT!!!
#ifdef NS_BUILD_REFCNT_LOGGING
	char refcntLogRepr[41];
#endif
private:
	virtual ~PyXPCOM_GatewayWeakReference();
};


// Helpers classes for our gateways.
class PyXPCOM_GatewayVariantHelper : public PyXPCOM_AllocHelper
{
public:
	PyXPCOM_GatewayVariantHelper( PyG_Base *gateway,
	                              int methodIndex,
	                              const XPTMethodDescriptor *info, 
	                              nsXPTCMiniVariant* params );
	~PyXPCOM_GatewayVariantHelper();
	PyObject *MakePyArgs();
	nsresult ProcessPythonResult(PyObject *ob);
	PyG_Base *m_gateway;
private:
	nsresult BackFillVariant( PyObject *ob, int index);
	PyObject *MakeSingleParam(int index, PythonTypeDescriptor &td);
	bool GetIIDForINTERFACE_ID(int index, const nsIID **ppret);
	nsresult GetArrayType(PRUint8 index, XPTTypeDescriptorTags *ret, nsIID *ppiid);
	PRUint32 GetSizeOrLengthIs( int var_index, bool is_size);
	MOZ_ALWAYS_INLINE uint32_t GetSizeIs(int var_index) {
		return GetSizeOrLengthIs(var_index, true);
	}
	MOZ_ALWAYS_INLINE uint32_t GetLengthIs(int var_index) {
		return GetSizeOrLengthIs(var_index, false);
	}
	bool SetSizeOrLengthIs(int var_index, bool is_size, uint32_t new_size);
	MOZ_ALWAYS_INLINE bool SetSizeIs(int var_index, uint32_t new_size) {
		return SetSizeOrLengthIs(var_index, true, new_size);
	}
	MOZ_ALWAYS_INLINE bool SetLengthIs(int var_index, uint32_t new_size) {
		return SetSizeOrLengthIs(var_index, false, new_size);
	}
	bool CanSetSizeOrLengthIs(int var_index, bool is_size);
	MOZ_ALWAYS_INLINE bool CanSetSizeIs(int var_index) {
		return CanSetSizeOrLengthIs(var_index, true);
	}
	MOZ_ALWAYS_INLINE bool CanSetLengthIs(int var_index) {
		return CanSetSizeOrLengthIs(var_index, false);
	}
	nsIInterfaceInfo *GetInterfaceInfo(); // NOTE: no ref count on result.


	nsXPTCMiniVariant* m_params;
	const XPTMethodDescriptor *m_info;
	int m_method_index;
	nsTArray<PythonTypeDescriptor> mPyTypeDesc;
	nsCOMPtr<nsIInterfaceInfo> m_interface_info;
};

// Misc converters.
PyObject *PyObject_FromXPTType( const nsXPTType *d);
// XPTTypeDescriptor derived from XPTType - latter is automatically processed via PyObject_FromXPTTypeDescriptor XPTTypeDescriptor 
PyObject *PyObject_FromXPTTypeDescriptor( const XPTTypeDescriptor *d);

PyObject *PyObject_FromXPTParamDescriptor( const XPTParamDescriptor *d);
PyObject *PyObject_FromXPTMethodDescriptor( const XPTMethodDescriptor *d);
PyObject *PyObject_FromXPTConstant( const XPTConstDescriptor *d);

// DLL reference counting functions.
// Although we maintain the count, we never actually
// finalize Python when it hits zero!
void PyXPCOM_DLLAddRef();
void PyXPCOM_DLLRelease();

/*************************************************************************
**************************************************************************

 LOCKING AND THREADING

**************************************************************************
*************************************************************************/

//
// We have 2 discrete locks in use (when no free-threaded is used, anyway).
// The first type of lock is the global Python lock.  This is the standard lock
// in use by Python, and must be used as documented by Python.  Specifically, no
// 2 threads may _ever_ call _any_ Python code (including INCREF/DECREF) without
// first having this thread lock.
//
// The second type of lock is a "global framework lock", and used whenever 2 threads 
// of C code need access to global data.  This is different than the Python 
// lock - this lock is used when no Python code can ever be called by the 
// threads, but the C code still needs thread-safety.

// We also supply helper classes which make the usage of these locks a one-liner.

// The "framework" lock, implemented as a PRLock
void PyXPCOM_AcquireGlobalLock(void);
void PyXPCOM_ReleaseGlobalLock(void);

// Helper class for the DLL global lock.
//
// This class magically waits for PyXPCOM framework global lock, and releases it
// when finished.  
// NEVER new one of these objects - only use on the stack!
class CEnterLeaveXPCOMFramework {
public:
	CEnterLeaveXPCOMFramework() {PyXPCOM_AcquireGlobalLock();}
	~CEnterLeaveXPCOMFramework() {PyXPCOM_ReleaseGlobalLock();}
};

// Initialize Python and do anything else necessary to get a functioning
// Python environment going...
PYXPCOM_EXPORT void PyXPCOM_EnsurePythonEnvironment(void);

PYXPCOM_EXPORT void PyXPCOM_MakePendingCalls();

// PyXPCOM_Globals_Ensure is deprecated - use PyXPCOM_EnsurePythonEnvironment
// which sets up globals, but also a whole lot more...
inline bool PyXPCOM_Globals_Ensure() {
    PyXPCOM_EnsurePythonEnvironment();
    return true;
}

// Helper class for Enter/Leave Python
//
// This class magically waits for the Python global lock, and releases it
// when finished.  

// Nested invocations will deadlock, so be careful.

// NEVER new one of these objects - only use on the stack!

class CEnterLeavePython {
public:
	CEnterLeavePython() {
		state = PyGILState_Ensure();
		// See "pending calls" comment below.  We reach into the Python
		// implementation to see if we are the first call on the stack.
		if (PyThreadState_Get()->gilstate_counter==1) {
			PyXPCOM_MakePendingCalls();
		}
	}
	~CEnterLeavePython() {
		PyGILState_Release(state);
	}
	PyGILState_STATE state;
};

// Our classes.
// Hrm - So we can't have templates, eh??
// preprocessor to the rescue, I guess.
#define PyXPCOM_INTERFACE_DECLARE(ClassName, InterfaceName, Methods )     \
                                                                          \
extern struct PyMethodDef Methods[];                                      \
                                                                          \
class ClassName : public Py_nsISupports                                   \
{                                                                         \
public:                                                                   \
	static PyXPCOM_TypeObject *type;                                  \
	static Py_nsISupports *Constructor(nsISupports *pInitObj, const nsIID &iid) { \
		return new ClassName(pInitObj, iid);                      \
	}                                                                 \
	static void InitType() {                                          \
		type = new PyXPCOM_TypeObject(                            \
				#InterfaceName,                           \
				Py_nsISupports::type,                     \
				sizeof(ClassName),                        \
				Methods,                                  \
				Constructor);                             \
		const nsIID &iid = NS_GET_IID(InterfaceName);             \
		RegisterInterface(iid, type);                             \
	}                                                                 \
protected:                                                                \
	ClassName(nsISupports *p, const nsIID &iid) :                     \
		Py_nsISupports(p, iid, type) {                            \
		/* The IID _must_ be the IID of the interface we are wrapping! */    \
		NS_ABORT_IF_FALSE(iid.Equals(NS_GET_IID(InterfaceName)), "Bad IID"); \
	}                                                                 \
};                                                                        \
                                                                          \
// End of PyXPCOM_INTERFACE_DECLARE macro

#define PyXPCOM_ATTR_INTERFACE_DECLARE(ClassName, InterfaceName, Methods )\
                                                                          \
extern struct PyMethodDef Methods[];                                      \
                                                                          \
class ClassName : public Py_nsISupports                                   \
{                                                                         \
public:                                                                   \
	static PyXPCOM_TypeObject *type;                                  \
	static Py_nsISupports *Constructor(nsISupports *pInitObj, const nsIID &iid) { \
		return new ClassName(pInitObj, iid);                      \
	}                                                                 \
	static void InitType() {                                          \
		type = new PyXPCOM_TypeObject(                            \
				#InterfaceName,                           \
				Py_nsISupports::type,                     \
				sizeof(ClassName),                        \
				Methods,                                  \
				Constructor);                             \
		const nsIID &iid = NS_GET_IID(InterfaceName);             \
		RegisterInterface(iid, type);                             \
}                                                                         \
	virtual PyObject *getattr(const char *name);                      \
	virtual int setattr(const char *name, PyObject *val);             \
protected:                                                                \
	ClassName(nsISupports *p, const nsIID &iid) :                     \
		Py_nsISupports(p, iid, type) {                            \
		/* The IID _must_ be the IID of the interface we are wrapping! */    \
		NS_ABORT_IF_FALSE(iid.Equals(NS_GET_IID(InterfaceName)), "Bad IID"); \
	}                                                                 \
};                                                                        \
                                                                          \
// End of PyXPCOM_ATTR_INTERFACE_DECLARE macro

#define PyXPCOM_INTERFACE_DEFINE(ClassName, InterfaceName, Methods )      \
NS_EXPORT_STATIC_MEMBER_(PyXPCOM_TypeObject *) ClassName::type = NULL;


// And the classes
PyXPCOM_INTERFACE_DECLARE(Py_nsIComponentManager, nsIComponentManager, PyMethods_IComponentManager)
PyXPCOM_INTERFACE_DECLARE(Py_nsIInterfaceInfoManager, nsIInterfaceInfoManager, PyMethods_IInterfaceInfoManager)
PyXPCOM_INTERFACE_DECLARE(Py_nsIEnumerator, nsIEnumerator, PyMethods_IEnumerator)
PyXPCOM_INTERFACE_DECLARE(Py_nsISimpleEnumerator, nsISimpleEnumerator, PyMethods_ISimpleEnumerator)
PyXPCOM_INTERFACE_DECLARE(Py_nsIInterfaceInfo, nsIInterfaceInfo, PyMethods_IInterfaceInfo)
PyXPCOM_INTERFACE_DECLARE(Py_nsIInputStream, nsIInputStream, PyMethods_IInputStream)
PyXPCOM_ATTR_INTERFACE_DECLARE(Py_nsIClassInfo, nsIClassInfo, PyMethods_IClassInfo)
PyXPCOM_ATTR_INTERFACE_DECLARE(Py_nsIVariant, nsIVariant, PyMethods_IVariant)
#endif // __PYXPCOM_H__
