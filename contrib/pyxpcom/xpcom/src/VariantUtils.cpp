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
 *   Unicode corrections by Shane Hathaway (http://hathawaymix.org),
 *     inspired by Mikhail Sobolev
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

#include "PyXPCOM_std.h"
#include "mozilla/Assertions.h"

static mozilla::fallible_t fallible;

// ------------------------------------------------------------------------
// nsString utilities
// ------------------------------------------------------------------------

#define PyUnicode_Fromchar16_t(src, size) \
	PyUnicode_DecodeUTF16((char*)(src),sizeof(char16_t)*(size),NULL,NULL)

/**
 * Copy a Python unicode string to a zero-terminated char16_t buffer
 * @param dest_out The resulting buffer.  Must not be null.  If the points to a
 * 		null pointer, memory will be allocated.  If this points to a block of
 * 		memory, it will be used instead.
 * @param size_out [optional] The size of the buffer, in characters.  If
 * 		dest_out is null, returns the size of the memory allocated.  If dest_out
 * 		is not null, should point to the size of the buffer given; on return,
 * 		will return the number of characters written.  This excludes the
 * 		terminating null.
 * @returns 0 on success, -1 on failure (and set a Python exception).
 */
static int
PyUnicode_Aschar16_t(PyObject *obj, char16_t **dest_out, PRUint32 *size_out)
{
	PRUint32 size;
	PyObject *s;
	char16_t *dest;

	MOZ_ASSERT(PyGILState_GetThisThreadState());
	MOZ_ASSERT(dest_out, "PyUnicode_Aschar16_t: dest_out was null");

	s = PyUnicode_AsUTF16String(obj);
	if (!s)
		return -1;
	size = (PyString_GET_SIZE(s) - 2) / sizeof(char16_t); // remove BOM
	if (*dest_out) {
		MOZ_ASSERT(size_out, "Can't have preallocated buffer of unknown size");
		uint32_t buffer_size = *size_out;
		*size_out = size;
		if (buffer_size <= *size_out) {
			PyErr_NoMemory();
			Py_DECREF(s);
			return -1;
		}
		dest = *dest_out;
	} else {
		dest = reinterpret_cast<char16_t *>(moz_malloc(sizeof(char16_t) * (size + 1)));
		if (!dest) {
			PyErr_NoMemory();
			Py_DECREF(s);
			return -1;
		}
	}
	// Drop the UTF-16 byte order mark at the beginning of
	// the string.  (See the docs on PyUnicode_AsUTF16String.)
	// Some Mozilla libraries don't like the mark.
	memcpy(dest, PyString_AS_STRING(s) + 2, sizeof(char16_t) * size);
	Py_DECREF(s);
	dest[size] = 0;
	*dest_out = dest;
	if (size_out)
		*size_out = size;
	return 0;
}

PyObject *
PyObject_FromNSString( const nsACString &s, bool bAssumeUTF8 /*= false */)
{
	MOZ_ASSERT(PyGILState_GetThisThreadState());
	PyObject *ret;
	if (s.IsVoid()) {
		ret = Py_None;
		Py_INCREF(Py_None);
	} else {
		if (bAssumeUTF8) {
			const nsCString temp(s);
			ret = PyUnicode_DecodeUTF8(temp.get(), temp.Length(), NULL);
		} else {
			NS_ConvertASCIItoUTF16 temp(s);
			ret = PyUnicode_Fromchar16_t(temp.get(), temp.Length());
		}
	}
	return ret;
}

/**
 * Create a python str object (PyString) from a NS CString
 */
PyObject *
PyString_FromNSString( const nsACString &s )
{
	MOZ_ASSERT(PyGILState_GetThisThreadState());
	PyObject *ret;
	if (s.IsVoid()) {
		ret = Py_None;
		Py_INCREF(Py_None);
	} else {
		ret = PyString_FromStringAndSize(s.BeginReading(), s.Length());
	}
	return ret;
}

PyObject *
PyObject_FromNSString( const nsAString &s )
{
	MOZ_ASSERT(PyGILState_GetThisThreadState());
	PyObject *ret;
	if (s.IsVoid()) {
		ret = Py_None;
		Py_INCREF(Py_None);
	} else {
		const nsString temp(s);
		ret = PyUnicode_Fromchar16_t(temp.get(), temp.Length());
	}
	return ret;
}

PyObject *
PyObject_FromNSString( const char16_t *s,
                       PRUint32 len /* = (PRUint32)-1*/)
{
	MOZ_ASSERT(PyGILState_GetThisThreadState());
	return PyUnicode_Fromchar16_t(s,
	           len==((PRUint32)-1)? NS_strlen(s) : len);
}

bool
PyObject_AsNSString( PyObject *val, nsAString &aStr)
{
	MOZ_ASSERT(PyGILState_GetThisThreadState());
	if (val == Py_None) {
		aStr.SetIsVoid(true);
		return true;
	}
	if (!PyString_Check(val) && !PyUnicode_Check(val)) {
		PyErr_SetString(PyExc_TypeError, "This parameter must be a string or Unicode object");
		return false;
	}
	PyObject *val_use = NULL;
	if (!(val_use = PyUnicode_FromObject(val)))
		return false;
	if (PyUnicode_GET_SIZE(val_use) == 0) {
		aStr.Truncate();
	}
	else {
		PyObject *s = PyUnicode_AsUTF16String(val_use);
		if (!s) {
			Py_DECREF(val_use);
			return false;
		}
		// Skip the BOM at the start of the string
		// (see PyUnicode_Aschar16_t)
		aStr.Assign(reinterpret_cast<char16_t*>(PyString_AS_STRING(s)) + 1,
			    (PyString_GET_SIZE(s) / sizeof(char16_t)) - 1);
		Py_DECREF(s);
	}
	Py_DECREF(val_use);
	return true;
}

// Array utilities
static PRUint32 GetArrayElementSize(XPTTypeDescriptorTags t)
{
	PRUint32 ret;
	MOZ_ASSERT(0 == (t & ~XPT_TDP_TAGMASK), "Invalid type descriptor");
	switch (t & XPT_TDP_TAGMASK) {
		case nsXPTType::T_U8:
		case nsXPTType::T_I8:
			ret = sizeof(PRInt8); 
			break;
		case nsXPTType::T_I16:
		case nsXPTType::T_U16:
			ret = sizeof(PRInt16); 
			break;
		case nsXPTType::T_I32:
		case nsXPTType::T_U32:
			ret = sizeof(PRInt32); 
			break;
		case nsXPTType::T_I64:
		case nsXPTType::T_U64:
			ret = sizeof(PRInt64); 
			break;
		case nsXPTType::T_FLOAT:
			ret = sizeof(float); 
			break;
		case nsXPTType::T_DOUBLE:
			ret = sizeof(double); 
			break;
		case nsXPTType::T_BOOL:
			ret = sizeof(bool); 
			break;
		case nsXPTType::T_CHAR:
			ret = sizeof(char); 
			break;
		case nsXPTType::T_WCHAR:
			ret = sizeof(char16_t); 
			break;
		case nsXPTType::T_IID:
		case nsXPTType::T_CHAR_STR:
		case nsXPTType::T_WCHAR_STR:
		case nsXPTType::T_INTERFACE:
		case nsXPTType::T_DOMSTRING:
		case nsXPTType::T_INTERFACE_IS:
		case nsXPTType::T_PSTRING_SIZE_IS:
		case nsXPTType::T_CSTRING:
		case nsXPTType::T_ASTRING:
		case nsXPTType::T_UTF8STRING:

			ret = sizeof( void * );
			break;

		case nsXPTType::T_VOID:
		case nsXPTType::T_ARRAY:
		case nsXPTType::T_JSVAL:
			MOZ_CRASH("Unknown array type code!");
			ret = 0;
			break;
	}
	return ret;
}

void FreeSingleArray(void *array_ptr, PRUint32 sequence_size, PRUint8 array_type)
{
	// Free each array element - NOT the array itself
	// Thus, we only need to free arrays or pointers.
	MOZ_ASSERT(PyGILState_GetThisThreadState());
	void **p = (void **)array_ptr;
	PRUint32 i;
	switch(array_type & XPT_TDP_TAGMASK) {
		case nsXPTType::T_IID:
		case nsXPTType::T_CHAR_STR:
		case nsXPTType::T_WCHAR_STR:
			for (i=0; i<sequence_size; i++)
				if (p[i]) NS_Free(p[i]);
			break;
		case nsXPTType::T_INTERFACE:
		case nsXPTType::T_INTERFACE_IS:
			for (i=0; i<sequence_size; i++)
				if (p[i]) {
					Py_BEGIN_ALLOW_THREADS; // MUST release thread-lock, incase a Python COM object that re-acquires.
					reinterpret_cast<nsISupports *>(p[i])->Release();
					Py_END_ALLOW_THREADS;
				}
			break;

		// Ones we know need no deallocation
		case nsXPTType::T_U8:
		case nsXPTType::T_I8:
		case nsXPTType::T_I16:
		case nsXPTType::T_U16:
		case nsXPTType::T_I32:
		case nsXPTType::T_U32:
		case nsXPTType::T_I64:
		case nsXPTType::T_U64:
		case nsXPTType::T_FLOAT:
		case nsXPTType::T_DOUBLE:
		case nsXPTType::T_BOOL:
		case nsXPTType::T_CHAR:
		case nsXPTType::T_WCHAR:
			break;

		// And a warning should new type codes appear, as they may need deallocation.
		default:
			PyXPCOM_LogWarning("Deallocating unknown type %d (0x%x) - possible memory leak\n",
					   array_type & XPT_TDP_TAGMASK, array_type & XPT_TDP_TAGMASK);
			break;
	}
}

#define FILL_SIMPLE_POINTER( type, val ) *reinterpret_cast<type*>(pthis) = (type)(val)
#define BREAK_FALSE {rc=false;break;}


bool FillSingleArray(void *array_ptr, PyObject *sequence_ob, PRUint32 sequence_size,
                     PRUint32 array_element_size, XPTTypeDescriptorTags array_type,
                     const nsIID &iid)
{
	PRUint8 *pthis = reinterpret_cast<uint8_t*>(array_ptr);
	MOZ_ASSERT(PyGILState_GetThisThreadState());
	MOZ_ASSERT(pthis, "Don't have a valid array to fill!");
	MOZ_ASSERT((static_cast<uint8_t>(array_type) & XPT_TDP_FLAGMASK) == 0,
			   "Array type should not have flags");
	bool rc = true;
	// We handle T_U8 specially as a string/Unicode.
	// If it is NOT a string, we just fall through and allow the standard
	// sequence unpack code process it (just slower!)
	if (array_type == TD_UINT8 &&
		(PyString_Check(sequence_ob) || PyUnicode_Check(sequence_ob))) {

		bool release_seq;
		if (PyUnicode_Check(sequence_ob)) {
			release_seq = true;
			sequence_ob = PyObject_Str(sequence_ob);
		} else {
			release_seq = false;
		}
		if (!sequence_ob) // presumably a memory error, or Unicode encoding error.
			return false;
		memcpy(pthis, PyString_AS_STRING(sequence_ob), sequence_size);
		if (release_seq)
			Py_DECREF(sequence_ob);
		return true;
	}

	for (PRUint32 i = 0; rc && i < sequence_size; i++, pthis += array_element_size) {
		PyObject *val = PySequence_GetItem(sequence_ob, i);
		PyObject *val_use = NULL;
		if (val == nullptr)
			return false;
		switch(array_type) {
			  case TD_INT8:
				if ((val_use=PyNumber_Int(val)) == NULL) BREAK_FALSE;
				FILL_SIMPLE_POINTER(PRInt8, PyInt_AsLong(val_use));
				break;
			  case TD_INT16:
				if ((val_use=PyNumber_Int(val)) == NULL) BREAK_FALSE;
				FILL_SIMPLE_POINTER(PRInt16, PyInt_AsLong(val_use));
				break;
			  case TD_INT32:
				if ((val_use=PyNumber_Int(val)) == NULL) BREAK_FALSE;
				FILL_SIMPLE_POINTER(PRInt32, PyInt_AsLong(val_use));
				break;
			  case TD_INT64:
				if ((val_use=PyNumber_Long(val)) == NULL) BREAK_FALSE;
				FILL_SIMPLE_POINTER(PRInt64, PyLong_AsLongLong(val_use));
				break;
			  case TD_UINT8:
				if ((val_use=PyNumber_Int(val)) == NULL) BREAK_FALSE;
				FILL_SIMPLE_POINTER(PRUint8, PyInt_AsLong(val_use));
				break;
			  case TD_UINT16:
				if ((val_use=PyNumber_Int(val)) == NULL) BREAK_FALSE;
				FILL_SIMPLE_POINTER(PRUint16, PyInt_AsLong(val_use));
				break;
			  case TD_UINT32:
				if ((val_use=PyNumber_Int(val)) == NULL) BREAK_FALSE;
				FILL_SIMPLE_POINTER(PRUint32, PyInt_AsLong(val_use));
				break;
			  case TD_UINT64:
				if ((val_use=PyNumber_Long(val)) == NULL) BREAK_FALSE;
				FILL_SIMPLE_POINTER(PRUint64, PyLong_AsUnsignedLongLong(val_use));
				break;
			  case TD_FLOAT:
				if ((val_use=PyNumber_Float(val)) == NULL) BREAK_FALSE
				FILL_SIMPLE_POINTER(float, PyFloat_AsDouble(val_use));
				break;
			  case TD_DOUBLE:
				if ((val_use=PyNumber_Float(val)) == NULL) BREAK_FALSE
				FILL_SIMPLE_POINTER(double, PyFloat_AsDouble(val_use));
				break;
			  case TD_BOOL:
				if ((val_use=PyNumber_Int(val)) == NULL) BREAK_FALSE
				FILL_SIMPLE_POINTER(bool, PyInt_AsLong(val_use) != 0);
				break;
			  case TD_CHAR:
				if (!PyString_Check(val) && !PyUnicode_Check(val)) {
					PyErr_SetString(PyExc_TypeError, "This parameter must be a string or Unicode object");
					BREAK_FALSE;
				}
				if ((val_use = PyObject_Str(val)) == NULL)
					BREAK_FALSE;
				// Sanity check should PyObject_Str() ever loosen its semantics wrt Unicode!
				MOZ_ASSERT(PyString_Check(val_use), "PyObject_Str didn't return a string object!");
				MOZ_ASSERT(PyString_GET_SIZE(val_use) == 1, "String too long");
				FILL_SIMPLE_POINTER(char, *PyString_AS_STRING(val_use));
				break;

			  case TD_WCHAR:
				if (!PyString_Check(val) && !PyUnicode_Check(val)) {
					PyErr_SetString(PyExc_TypeError, "This parameter must be a string or Unicode object");
					BREAK_FALSE;
				}
				if ((val_use = PyUnicode_FromObject(val)) == NULL)
					BREAK_FALSE;
				MOZ_ASSERT(PyUnicode_Check(val_use), "PyUnicode_FromObject didnt return a Unicode object!");
				MOZ_ASSERT(PyUnicode_GET_SIZE(val_use) == 1, "String too long");
				// Lossy!
				FILL_SIMPLE_POINTER(char16_t, *PyUnicode_AS_UNICODE(val_use));
				MOZ_ASSERT(*PyUnicode_AS_UNICODE(val_use) <= 0xFFFF,
						   "Lossy cast of Unicode value to char16_t");
				break;

			  case TD_PNSIID: {
				nsIID **pp = reinterpret_cast<nsIID **>(pthis);
				MOZ_ASSERT(*pp == nullptr, "Existing IID"); // the memory should be fresh, no?
				// If there is an existing IID, free it.
				if (*pp)
					moz_free(*pp);
				*pp = reinterpret_cast<nsIID *>(moz_malloc(sizeof(nsIID)));
				if (*pp == nullptr) {
					PyErr_NoMemory();
					BREAK_FALSE;
				}
				if (!Py_nsIID::IIDFromPyObject(val, *pp)) {
					moz_free(*pp);
					*pp = nullptr;
					BREAK_FALSE;
				}
				break;
				}

			  case TD_PSTRING: {
				// If it is an existing string, free it.
				char **pp = (char **)pthis;
				if (*pp) {
					moz_free(*pp);
					*pp = nullptr;
				}

				if (val == Py_None)
					break; // Remains NULL.
				if (!PyString_Check(val) && !PyUnicode_Check(val)) {
					PyErr_SetString(PyExc_TypeError, "This parameter must be a string or Unicode object");
					BREAK_FALSE;
				}
				if ((val_use = PyObject_Str(val))==NULL)
					BREAK_FALSE;
				// Sanity check should PyObject_Str() ever loosen its semantics wrt Unicode!
				NS_ABORT_IF_FALSE(PyString_Check(val_use), "PyObject_Str didn't return a string object!");

				const char *sz = PyString_AS_STRING(val_use);
				int nch = PyString_GET_SIZE(val_use);

				*pp = (char *)moz_calloc(sizeof(char), nch+1);
				if (!*pp) {
					PyErr_NoMemory();
					BREAK_FALSE;
				}
				strncpy(*pp, sz, nch+1);
				break;
				}
			  case TD_PWSTRING: {
				// If it is an existing string, free it.
				char16_t **pp = (char16_t **)pthis;
				if (*pp)
					nsMemory::Free(*pp);
				*pp = nullptr;
				if (val == Py_None)
					break; // Remains NULL.
				if (!PyString_Check(val) && !PyUnicode_Check(val)) {
					PyErr_SetString(PyExc_TypeError, "This parameter must be a string or Unicode object");
					BREAK_FALSE;
				}
				if ((val_use = PyUnicode_FromObject(val))==NULL)
					BREAK_FALSE;
				NS_ABORT_IF_FALSE(PyUnicode_Check(val_use), "PyUnicode_FromObject didnt return a Unicode object!");
				if (PyUnicode_Aschar16_t(val_use, pp, NULL) < 0)
					BREAK_FALSE;
				break;
				}
			  case TD_INTERFACE_IS_TYPE:
			  case TD_INTERFACE_TYPE:  {
				// We do allow NULL here, even tho doing so will no-doubt crash some objects.
				// (but there will certainly be objects out there that will allow NULL :-(
				nsISupports *pnew;
				if (!Py_nsISupports::InterfaceFromPyObject(val, iid, &pnew, true))
					BREAK_FALSE;
				nsISupports **pp = (nsISupports **)pthis;
				MOZ_ASSERT(*pp == nullptr, "Existing interface?");
				if (*pp) {
					Py_BEGIN_ALLOW_THREADS; // MUST release thread-lock, incase a Python COM object that re-acquires.
					(*pp)->Release();
					Py_END_ALLOW_THREADS;
				}
				*pp = pnew; // ref-count added by InterfaceFromPyObject
				break;
				}
			  case TD_VOID:
			  case TD_DOMSTRING:
			  case TD_ARRAY:
			  case TD_PSTRING_SIZE_IS:
			  case TD_PWSTRING_SIZE_IS:
			  case TD_UTF8STRING:
			  case TD_CSTRING:
			  case TD_ASTRING:
			  case TD_JSVAL:
				// Bail out on cases we can't deal with
				// This makes sure the Python side understands that there's a problem
				PyErr_Format(PyExc_NotImplementedError,
					     "Converting Python object for an array element - "
						"The object type (0x%x) is unknown",
					     array_type);
				BREAK_FALSE;
		}
		Py_XDECREF(val_use);
		Py_DECREF(val);
	}
	return rc;	
}

static PyObject *UnpackSingleArray(Py_nsISupports *parent, void *array_ptr,
				   PRUint32 sequence_size, XPTTypeDescriptorTags array_type, nsIID *iid)
{
	MOZ_ASSERT(PyGILState_GetThisThreadState());
	if (array_ptr==NULL) {
		Py_INCREF(Py_None);
		return Py_None;
	}
	if (array_type == nsXPTType::T_U8)
		return PyString_FromStringAndSize( (char *)array_ptr, sequence_size );

	PRUint32 array_element_size = GetArrayElementSize(array_type);
	PyObject *list_ret = PyList_New(sequence_size);
	PRUint8 *pthis = (PRUint8 *)array_ptr;
	for (PRUint32 i=0; i<sequence_size; i++,pthis += array_element_size) {
		PyObject *val = NULL;
		switch(array_type) {
			  case nsXPTType::T_I8:
				val = PyInt_FromLong( *((PRInt8 *)pthis) );
				break;
			  case nsXPTType::T_I16:
				val = PyInt_FromLong( *((PRInt16 *)pthis) );
				break;
			  case nsXPTType::T_I32:
				val = PyInt_FromLong( *((PRInt32 *)pthis) );
				break;
			  case nsXPTType::T_I64:
				val = PyLong_FromLongLong( *((PRInt64 *)pthis) );
				break;
			  // case nsXPTType::T_U8 - handled above!
			  case nsXPTType::T_U16:
				val = PyInt_FromLong( *((PRUint16 *)pthis) );
				break;
			  case nsXPTType::T_U32:
				val = PyInt_FromLong( *((PRUint32 *)pthis) );
				break;
			  case nsXPTType::T_U64:
				val = PyLong_FromUnsignedLongLong( *((PRUint64 *)pthis) );
				break;
			  case nsXPTType::T_FLOAT:
				val = PyFloat_FromDouble( *((float*)pthis) );
				break;
			  case nsXPTType::T_DOUBLE:
				val = PyFloat_FromDouble( *((double*)pthis) );
				break;
			  case nsXPTType::T_BOOL:
				val = (*((bool *)pthis)) ? Py_True : Py_False;
				Py_INCREF(val);
				break;
			  case nsXPTType::T_IID:
				val = Py_nsIID::PyObjectFromIID( **((nsIID **)pthis) );
				break;

			  case nsXPTType::T_CHAR_STR: {
				char **pp = (char **)pthis;
				if (*pp==NULL) {
					Py_INCREF(Py_None);
					val = Py_None;
				} else
					val = PyString_FromString(*pp);
				break;
				}
			  case nsXPTType::T_WCHAR_STR: {
				char16_t **pp = (char16_t **)pthis;
				if (*pp==NULL) {
					Py_INCREF(Py_None);
					val = Py_None;
				} else {
					val = PyUnicode_Fromchar16_t( *pp, NS_strlen(*pp) );
				}
				break;
				}
			  case nsXPTType::T_INTERFACE_IS:
			  case nsXPTType::T_INTERFACE: {
				nsISupports **pp = (nsISupports **)pthis;
				// If we have an owning parent, let it create
				// the object for us.
				if (iid && iid->Equals(NS_GET_IID(nsIVariant)))
					val = PyObject_FromVariant(parent, (nsIVariant *)*pp);
				else if (parent)
					val = parent->MakeInterfaceResult(*pp, iid ? *iid : NS_GET_IID(nsISupports));
				else
					val = Py_nsISupports::PyObjectFromInterface(
					                *pp,
					                iid ? *iid : NS_GET_IID(nsISupports),
					                true);
				break;
				}
			  default: {
				PyErr_Format(PyExc_NotImplementedError,
					     "Converting an array element to a Python array - "
						"The object type (0x%x) is unknown",
					     array_type);
				break;
				}
		}
		if (val==NULL) {
			NS_ABORT_IF_FALSE(PyErr_Occurred(), "NULL result in array conversion, but no error set!");
			return NULL;
		}
		PyList_SET_ITEM(list_ret, i, val); // ref-count consumed.
	}
	return list_ret;
}


// ------------------------------------------------------------------------
// nsIVariant utilities
// ------------------------------------------------------------------------
/**
 * A result type for BestVariantType
 */
struct BVFTResult {
	BVFTResult() {pis = NULL;iid=Py_nsIID_NULL;}
	nsISupports *pis;
	nsIID iid;
};

static PRUint16 BestVariantTypeForPyObject( PyObject *ob, BVFTResult *pdata)
{
	MOZ_ASSERT(PyGILState_GetThisThreadState());
	nsCOMPtr<nsISupports> ps = NULL;
	nsIID iid;
	MOZ_ASSERT(ob);
	MOZ_ASSERT(pdata);
	// start with some fast concrete checks.
	if (ob==Py_None)
		return nsIDataType::VTYPE_EMPTY;
	if (ob==Py_True || ob == Py_False)
		return nsIDataType::VTYPE_BOOL;
	if (PyInt_Check(ob))
		return nsIDataType::VTYPE_INT32;
	if (PyLong_Check(ob))
		return nsIDataType::VTYPE_INT64;
	if (PyFloat_Check(ob))
		return nsIDataType::VTYPE_DOUBLE;
	if (PyString_Check(ob))
		return nsIDataType::VTYPE_STRING_SIZE_IS;
	if (PyUnicode_Check(ob))
		return nsIDataType::VTYPE_WSTRING_SIZE_IS;
	if (PyTuple_Check(ob) || PyList_Check(ob)) {
		if (PySequence_Length(ob))
			return nsIDataType::VTYPE_ARRAY;
		return nsIDataType::VTYPE_EMPTY_ARRAY;
	}
	// Now do expensive or abstract checks.
	if (Py_nsISupports::InterfaceFromPyObject(ob, NS_GET_IID(nsISupports),
						  getter_AddRefs(ps), true))
	{
		ps.forget(&pdata->pis);
		pdata->iid = NS_GET_IID(nsISupports);
		return nsIDataType::VTYPE_INTERFACE_IS;
	} else
		PyErr_Clear();
	if (Py_nsIID::IIDFromPyObject(ob, &iid)) {
		pdata->iid = iid;
		return nsIDataType::VTYPE_ID;
	} else
		PyErr_Clear();
	if (PySequence_Check(ob)) {
		if (PySequence_Length(ob))
			return nsIDataType::VTYPE_ARRAY;
		return nsIDataType::VTYPE_EMPTY_ARRAY;
	}
	return (PRUint16)-1;
}

nsresult
PyObject_AsVariant( PyObject *ob, nsIVariant **aRet)
{
	MOZ_ASSERT(PyGILState_GetThisThreadState());
	nsresult nr = NS_OK;
	nsCOMPtr<nsIWritableVariant> v = do_CreateInstance("@mozilla.org/variant;1", &nr);
	NS_ENSURE_SUCCESS(nr, nr);
	// *sigh* - I tried the abstract API (PyNumber_Check, etc)
	// but our COM instances too often qualify.
	BVFTResult cvt_result;
	PRUint16 dt = BestVariantTypeForPyObject(ob, &cvt_result);
	switch (dt) {
		case nsIDataType::VTYPE_BOOL:
			nr = v->SetAsBool(ob==Py_True);
			break;
		case nsIDataType::VTYPE_INT32:
			nr = v->SetAsInt32(PyInt_AsLong(ob));
			break;
		case nsIDataType::VTYPE_INT64:
			nr = v->SetAsInt64(PyLong_AsLongLong(ob));
			break;
		case nsIDataType::VTYPE_DOUBLE:
			nr = v->SetAsDouble(PyFloat_AsDouble(ob));
			break;
		case nsIDataType::VTYPE_STRING_SIZE_IS:
			nr = v->SetAsStringWithSize(PyString_Size(ob), PyString_AsString(ob));
			break;
		case nsIDataType::VTYPE_WSTRING_SIZE_IS:
			if (PyUnicode_GetSize(ob) == 0) {
				nr = v->SetAsWStringWithSize(0, (char16_t*)NULL);
			}
			else {
				PRUint32 nch;
				char16_t *p = nullptr;
				if (PyUnicode_Aschar16_t(ob, &p, &nch) < 0) {
					PyXPCOM_LogWarning("Failed to convert object to unicode", ob->ob_type->tp_name);
					nr = NS_ERROR_UNEXPECTED;
					break;
				}
				nr = v->SetAsWStringWithSize(nch, p);
				nsMemory::Free(p);
			}
			break;
		case nsIDataType::VTYPE_INTERFACE_IS:
		{
			nsISupports *ps = cvt_result.pis;
			nr = v->SetAsInterface(cvt_result.iid, ps);
			if (ps) {
				Py_BEGIN_ALLOW_THREADS; // MUST release thread-lock, incase a Python COM object that re-acquires.
				ps->Release();
				Py_END_ALLOW_THREADS;
			}
			break;
		}
		case nsIDataType::VTYPE_ID:
			nr = v->SetAsID(cvt_result.iid);
			break;
		case nsIDataType::VTYPE_ARRAY:
		{
			// To support arrays holding different data types,
			// each element itself is a variant.
			int seq_length = PySequence_Length(ob);
			int i;

			nsIVariant** buf = ::new (fallible) nsIVariant*[seq_length];
			NS_ENSURE_TRUE(buf, NS_ERROR_OUT_OF_MEMORY);
			memset(buf, 0, sizeof(nsIVariant *) * seq_length);
			for (i = 0; NS_SUCCEEDED(nr) && i < seq_length; i++) {
				PyObject *sub = PySequence_GetItem(ob, i);
				if (!sub) {
					nr = PyXPCOM_SetCOMErrorFromPyException();
					break;
				}
				nr = PyObject_AsVariant(sub, &buf[i]);
				Py_DECREF(sub);
			}
			if (NS_SUCCEEDED(nr)) {
				nr = v->SetAsArray(nsXPTType::T_INTERFACE_IS,
				                   &NS_GET_IID(nsIVariant),
				                   seq_length, buf);
			}
			// Clean things up.
			NS_FREE_XPCOM_ISUPPORTS_POINTER_ARRAY(seq_length, buf);
			break;
		}
		case nsIDataType::VTYPE_EMPTY:
			nr = v->SetAsEmpty();
			break;
		case nsIDataType::VTYPE_EMPTY_ARRAY:
			nr = v->SetAsEmptyArray();
			break;
		case (PRUint16)-1:
			PyXPCOM_LogWarning("Objects of type '%s' can not be converted to an nsIVariant", ob->ob_type->tp_name);
			nr = NS_ERROR_UNEXPECTED;
		default:
			MOZ_CRASH("BestVariantTypeForPyObject() returned a variant type not handled here!");
			PyXPCOM_LogWarning("Objects of type '%s' can not be converted to an nsIVariant", ob->ob_type->tp_name);
			nr = NS_ERROR_UNEXPECTED;
	}
	if (NS_FAILED(nr))
		return nr;
	return CallQueryInterface(v, aRet);
}

#define GET_FROM_V(Type, FuncGet, FuncConvert) { \
	Type t; \
	if (NS_FAILED(nr = FuncGet( &t ))) goto done;\
	ret = FuncConvert(t);\
	break; \
}

PyObject *PyObject_FromVariantArray( Py_nsISupports *parent, nsIVariant *v)
{
	nsresult nr;
	NS_PRECONDITION(v, "NULL variant!");
	MOZ_ASSERT(PyGILState_GetThisThreadState());
	if (!v)
		return PyXPCOM_BuildPyException(NS_ERROR_INVALID_POINTER);
#ifdef NS_DEBUG
	PRUint16 dt;
	nr = v->GetDataType(&dt);
	MOZ_ASSERT(dt == nsIDataType::VTYPE_ARRAY, "expected an array variant");
#endif
	nsIID iid;
	void *p;
	PRUint16 dataType;
	PRUint32 count;
	nr = v->GetAsArray(&dataType, &iid, &count, &p);
	XPTTypeDescriptorTags type = static_cast<XPTTypeDescriptorTags>(dataType);
	if (NS_FAILED(nr)) return PyXPCOM_BuildPyException(nr);
	PyObject *ret = UnpackSingleArray(parent, p, count, type, &iid);
	FreeSingleArray(p, count, (PRUint8)type);
	nsMemory::Free(p);
	return ret;
}

PyObject *
PyObject_FromVariant( Py_nsISupports *parent, nsIVariant *v)
{
	MOZ_ASSERT(PyGILState_GetThisThreadState());
	if (!v) {
		Py_INCREF(Py_None);
		return Py_None;
	}
	PRUint16 dt;
	nsresult nr;
	PyObject *ret = NULL;
	nr = v->GetDataType(&dt);
	if (NS_FAILED(nr)) goto done;
	switch (dt) {
		case nsIDataType::VTYPE_VOID:
		case nsIDataType::VTYPE_EMPTY:
			ret = Py_None;
			Py_INCREF(Py_None);
			break;
		case nsIDataType::VTYPE_EMPTY_ARRAY:
			ret = PyList_New(0);
			break;
		case nsIDataType::VTYPE_ARRAY:
			ret = PyObject_FromVariantArray(parent, v);
			break;
		case nsIDataType::VTYPE_INT8:
		case nsIDataType::VTYPE_INT16:
		case nsIDataType::VTYPE_INT32:
			GET_FROM_V(PRInt32, v->GetAsInt32, PyInt_FromLong);
		case nsIDataType::VTYPE_UINT8:
		case nsIDataType::VTYPE_UINT16:
		case nsIDataType::VTYPE_UINT32:
			GET_FROM_V(PRUint32, v->GetAsUint32, PyLong_FromUnsignedLong);
		case nsIDataType::VTYPE_INT64:
			GET_FROM_V(PRInt64, v->GetAsInt64, PyLong_FromLongLong);
		case nsIDataType::VTYPE_UINT64:
			GET_FROM_V(PRUint64, v->GetAsUint64, PyLong_FromUnsignedLongLong);
		case nsIDataType::VTYPE_FLOAT:
		case nsIDataType::VTYPE_DOUBLE:
			GET_FROM_V(double, v->GetAsDouble, PyFloat_FromDouble);
		case nsIDataType::VTYPE_BOOL: {
			bool b;
			if (NS_FAILED(nr = v->GetAsBool(&b))) {
				goto done;
			}
			ret = v ? Py_True : Py_False;
			Py_INCREF(ret);
			break;
		}
		default:
			PyXPCOM_LogWarning("Converting variant to Python object - variant type '%d' unknown - using string.\n", dt);
		// Fall through to the string case
		case nsIDataType::VTYPE_CHAR:
		case nsIDataType::VTYPE_CHAR_STR:
		case nsIDataType::VTYPE_STRING_SIZE_IS:
		case nsIDataType::VTYPE_CSTRING: {
			nsAutoCString s;
			if (NS_FAILED(nr=v->GetAsACString(s))) goto done;
			ret = PyString_FromNSString(s);
			break;
		}
		case nsIDataType::VTYPE_WCHAR:
		case nsIDataType::VTYPE_DOMSTRING:
		case nsIDataType::VTYPE_WSTRING_SIZE_IS:
		case nsIDataType::VTYPE_ASTRING: {
			nsAutoString s;
			if (NS_FAILED(nr=v->GetAsAString(s))) goto done;
			ret = PyObject_FromNSString(s);
			break;
		}
		case nsIDataType::VTYPE_ID:
			GET_FROM_V(nsIID, v->GetAsID, Py_nsIID::PyObjectFromIID);
		case nsIDataType::VTYPE_INTERFACE: {
			nsCOMPtr<nsISupports> p;
			if (NS_FAILED(nr=v->GetAsISupports(getter_AddRefs(p)))) goto done;
			if (parent)
				ret = parent->MakeInterfaceResult(p, NS_GET_IID(nsISupports));
			else
				ret = Py_nsISupports::PyObjectFromInterface(
					                p, NS_GET_IID(nsISupports), true);
			break;
		}
		case nsIDataType::VTYPE_INTERFACE_IS: {
			nsCOMPtr<nsISupports> p;
			nsIID *iid;
			if (NS_FAILED(nr=v->GetAsInterface(&iid, getter_AddRefs(p)))) goto done;
			// If the variant itself holds a variant, we should
			// probably unpack that too?
			ret = parent->MakeInterfaceResult(p, *iid);
			nsMemory::Free((char*)iid);
			break;
		// case nsIDataType::VTYPE_WCHAR_STR
		// case nsIDataType::VTYPE_UTF8STRING
		}
	}
done:
	if (NS_FAILED(nr)) {
		NS_ABORT_IF_FALSE(ret==NULL, "Have an error, but also a return val!");
		PyXPCOM_BuildPyException(nr);
	}
	return ret;
}

static bool ProcessPythonTypeDescriptors(PythonTypeDescriptor *pdescs, int num,
                                         int *min_num_params, int *max_num_params)
{
	// Loop over the array, checking all the params marked as having an arg.
	// If these args nominate another arg as the size_is param, then
	// we reset the size_is param to _not_ requiring an arg.
	MOZ_ASSERT(PyGILState_GetThisThreadState());
	int i;
	for (i = 0; i < num; i++) {
		PythonTypeDescriptor &ptd = pdescs[i];

		// Some sanity checks on the type
		MOZ_ASSERT(0 == (ptd.param_flags & ~XPT_PD_FLAGMASK),
		           "Invalid param flags");
		MOZ_ASSERT_IF(ptd.IsDipper(), ptd.IsDipperType());
		MOZ_ASSERT_IF(ptd.IsDipper(), !ptd.IsOut());
		MOZ_ASSERT_IF(ptd.IsDipperType(), !ptd.IsOut());
		if (ptd.IsDipper() && !(ptd.IsIn() || ptd.IsOut())) {
			// This is broken. Dippers should be 'in'.  See the xptypelib spec.
			ptd.param_flags |= XPT_PD_IN;
		}
		MOZ_ASSERT(ptd.IsIn() || ptd.IsOut());
		if (ptd.IsIn() && ptd.IsRetval() && !ptd.IsDipper()) {
			PyErr_Format(PyExc_ValueError,
			             "'[retval] in' parameter in position %i makes no sense!",
			             i);
			return false; // This is an insane interface, we can't call it, sorry
		}
		if (ptd.IsIn() && ptd.IsShared()) {
			PyErr_Format(PyExc_ValueError,
			             "'[shared] in' parameter in position %i makes no sense!",
			             i);
			return false;
		}

		switch (ptd.TypeTag()) {
			case nsXPTType::T_ARRAY:
				MOZ_ASSERT(ptd.length_is < num, "Bad dependent index");
				if (ptd.length_is < num) {
					if (ptd.IsIn())
						pdescs[ptd.length_is].is_auto_in = true;
					if (ptd.IsOut())
						pdescs[ptd.length_is].is_auto_out = true;
				}
				break;
			case nsXPTType::T_PSTRING_SIZE_IS:
			case nsXPTType::T_PWSTRING_SIZE_IS:
				MOZ_ASSERT(ptd.size_is < num, "Bad dependent index");
				if (ptd.size_is < num) {
					if (ptd.IsIn())
						pdescs[ptd.size_is].is_auto_in = true;
					if (ptd.IsOut())
						pdescs[ptd.size_is].is_auto_out = true;
				}
				break;
			case nsXPTType::T_JSVAL:
				PyErr_Format(PyExc_ValueError,
							 "Can't deal with jsval in position %i in Python-land",
							 i);
				return false;
			default:
				break;
		}
	}
	(*min_num_params) = 0;
	(*max_num_params) = 0;
	for (i=0;i<num;i++) {
		if (pdescs[i].IsIn() && !pdescs[i].IsAutoIn() && !pdescs[i].IsDipper()) {
			(*max_num_params)++;
			if (!pdescs[i].IsOptional()) {
				(*min_num_params)++;
			}
		}
	}
	return true;
}

#ifdef DEBUG
// Allocator wrappers (to debug leaks)
template<typename T>
T* PyXPCOM_AllocHelper::Alloc(T*& dest, size_t count,
                              const char* file, const unsigned line)
{
	dest = reinterpret_cast<T*>(moz_calloc(sizeof(T), count));
	//fprintf(stderr, "ALLOC: %12p [%12p/%12p] @%u\n", dest, this, &mAllocations, __LINE__);
	mAllocations.Put(reinterpret_cast<void*>(dest),
			 new LineRef(file, line));
	for (size_t i = 0; i < count; ++i)
		new (&dest[i]) T();
	return dest;
}
void* PyXPCOM_AllocHelper::Alloc(size_t size, size_t count,
                                 const char* file, const unsigned line)
{
	void* result = moz_calloc(size, count);
	//fprintf(stderr, "ALLOC: %12p [%12p/%12p] @%u\n", result, this, &mAllocations, __LINE__);
	mAllocations.Put(result,
			 new LineRef(file, line));
	return result;
}
void PyXPCOM_AllocHelper::MarkAlloc(void* buf, const char* file,
                                    const unsigned line)
{
	//fprintf(stderr, "ALLOC: %12p [%12p/%12p] @%u\n", buf, this, &mAllocations, __LINE__);
	mAllocations.Put(buf, new LineRef(file, line));
}
template<typename T>
void PyXPCOM_AllocHelper::Free(T* buf) {
	//fprintf(stderr, "FREE: %12p [%12p/%12p] @%u\n", buf, this, &mAllocations, __LINE__);
	mAllocations.Remove(reinterpret_cast<void*>(buf));
	delete[] buf;
}
void PyXPCOM_AllocHelper::Free(void* buf) {
	//fprintf(stderr, "FREE: %12p [%12p/%12p] @%u\n", buf, this, &mAllocations, __LINE__);
	mAllocations.Remove(buf);
	moz_free(buf);
}
void PyXPCOM_AllocHelper::MarkFree(void* buf) {
	//fprintf(stderr, "FREE: %12p [%12p/%12p] @%u\n", buf, this, &mAllocations, __LINE__);
	mAllocations.Remove(buf);
}
PLDHashOperator PyXPCOM_AllocHelper::ReadAllocation(void* key,
                                                    LineRef* value,
                                                    void* userData)
{
	fprintf(stderr, "ERROR: leaked %p @ %s:%u\n",
			key, value->file, value->line);
	return PLDHashOperator::PL_DHASH_NEXT;
}

PyXPCOM_AllocHelper::~PyXPCOM_AllocHelper() {
	mAllocations.EnumerateRead(ReadAllocation, nullptr);
	MOZ_ASSERT(mAllocations.Count() == 0, "Did not free some things");
}

// Debugging helper; never called in code.  This will leak.
char* PythonTypeDescriptor::Describe() const {
	static char buf[1024], typeTagBuf[0x10], arrayTypeTagBuf[0x10];
	const char* kTypeTags[] = {
		"TD_INT8",
		"TD_INT16",
		"TD_INT32",
		"TD_INT64",
		"TD_UINT8",
		"TD_UINT16",
		"TD_UINT32",
		"TD_UINT64",
		"TD_FLOAT",
		"TD_DOUBLE",
		"TD_BOOL",
		"TD_CHAR",
		"TD_WCHAR",
		"TD_VOID",
		"TD_PNSIID",
		"TD_DOMSTRING",
		"TD_PSTRING",
		"TD_PWSTRING",
		"TD_INTERFACE_TYPE",
		"TD_INTERFACE_IS_TYPE",
		"TD_ARRAY",
		"TD_PSTRING_SIZE_IS",
		"TD_PWSTRING_SIZE_IS",
		"TD_UTF8STRING",
		"TD_CSTRING",
		"TD_ASTRING",
		"TD_JSVAL"
	};
	const char *typeTag = typeTagBuf;
	if (TypeTag() < 0 || TypeTag() > NS_ARRAY_LENGTH(kTypeTags)) {
		sprintf(typeTagBuf, "%u", TypeTag());
	} else {
		typeTag = kTypeTags[TypeTag()];
	}
	const char *arrayTypeTag = arrayTypeTagBuf;
	if (ArrayTypeTag() < 0 || ArrayTypeTag() > NS_ARRAY_LENGTH(kTypeTags)) {
		sprintf(arrayTypeTagBuf, "%u", ArrayTypeTag());
	} else {
		arrayTypeTag = kTypeTags[ArrayTypeTag()];
	}
	sprintf(buf, "TD Type=%s ArrayType=%s [%s%s%s%s%s%s%s%s%s%s]",
	        typeTag, arrayTypeTag,
	        IsPointer() ? "pointer " : "",
	        IsReference() ? "ref " : "",
	        IsIn() ? "in " : "",
	        IsOut() ? "out " : "",
	        IsRetval() ? "retval " : "",
	        IsShared() ? "shared " : "",
	        IsDipper() ? (IsDipperType() ? "dipper " : "** DIPPER ** ") :
	                     (IsDipperType() ? "### NOT DIPPER ### " : ""),
	        IsOptional() ? "optional " : "",
	        IsAutoIn() ? (IsAutoSet() ? "*in " : "!in ") : "",
	        IsAutoOut() ? (IsAutoSet() ? "*out " : "!out ") : ""
	       );
	return buf;
}
char* PythonTypeDescriptor::Describe(const nsXPTCVariant& v) const {
	static char buf[1024];
	sprintf(buf, "%s[%s%s]",
	        Describe(),
	        v.DoesValNeedCleanup() ? "cleanup " : "",
	        v.IsIndirect() ? "indirect " : "");
	return buf;
}
#endif

/*************************************************************************
**************************************************************************

Helpers when CALLING interfaces.

**************************************************************************
*************************************************************************/

PyXPCOM_InterfaceVariantHelper::PyXPCOM_InterfaceVariantHelper(Py_nsISupports *parent)
{
	MOZ_ASSERT(PyGILState_GetThisThreadState());
	MOZ_ASSERT(parent);
	m_pyparams = nullptr;
	// Parent should never die before we do, but let's not take the chance.
	m_parent = parent;
	Py_INCREF(parent);
}

PyXPCOM_InterfaceVariantHelper::~PyXPCOM_InterfaceVariantHelper()
{
	MOZ_ASSERT(PyGILState_GetThisThreadState());
	Py_DECREF(m_parent);
	Py_XDECREF(m_pyparams);
	MOZ_ASSERT(mDispatchParams.Length() == mPyTypeDesc.Length());
	for (int i = 0; i < mDispatchParams.Length(); ++i) {
		nsXPTCVariant &ns_v = mDispatchParams.ElementAt(i);

		bool needsCleanup = ns_v.DoesValNeedCleanup();
		nsXPTType type = ns_v.type;
		if (type.IsArray()) {
			type = nsXPTType(mPyTypeDesc[i].array_type);
		}
		if (mPyTypeDesc[i].IsOut()) {
			MOZ_ASSERT(!mPyTypeDesc[i].IsDipper(), "We shouldn't have dipper outs!");
			// For 'out'/'inout' params, we can't trust DoesValNeedCleanup() because
			// it depends on what the callee did with it
			if (type.IsArithmetic()) {
				// These are stashed inside the nsXPTCVariant
				needsCleanup = false;
			} else {
				needsCleanup = (ns_v.val.p != nullptr);
			}
		} else {
			MOZ_ASSERT(mPyTypeDesc[i].IsIn(),
					   "We got a param that's neither in nor out");
		}

		if (ns_v.type.IsArray()) {
			if (needsCleanup) {
				nsXPTType array_type(mPyTypeDesc[i].array_type);
				uint32_t seq_size = GetLengthIs(i);
				void** p = reinterpret_cast<void**>(ns_v.val.p);
				for (uint32_t j = 0; j < seq_size; ++j) {
					CleanupParam(p[j], array_type);
				}
			}
			Free(ns_v.val.p);
		} else {
			if (needsCleanup) {
				CleanupParam(ns_v.val.p, ns_v.type);
			} else {
				MOZ_ASSERT(!mAllocations.Get(ns_v.val.p),
						   "Claims to not need cleanup but we allocated it!");
			}
		}
	}
}

/**
 * Set up the call information from Python
 * @param obParams the Python call arguments; see xpcom/client/__init__.py
 * 		_MakeMethodCode for details.  It should be a sequence of two tuples;
 * 		the first is the types, and the second is the arguments being passed.
 * 		Each element in the tuple of types is itself a tuple, of elements
 * 		(param_flags, type_flags, argnum, argnum2, iid, array_type).
 */
bool PyXPCOM_InterfaceVariantHelper::Init(PyObject *obParams)
{
	bool ok = false;
	int i;
	int min_num_params = 0;
	int max_num_params = 0;
	int num_args_provided;
	MOZ_ASSERT(PyGILState_GetThisThreadState());
	if (!PySequence_Check(obParams) || PySequence_Length(obParams) != 2) {
		PyErr_Format(PyExc_TypeError, "Param descriptors must be a sequence of exactly length 2");
		return false;
	}
	PyObject *typedescs = PySequence_GetItem(obParams, 0);
	if (!typedescs)
		return false;
	// NOTE: The length of the typedescs may be different than the
	// args actually passed.  The typedescs always include all
	// hidden params (such as "size_is"), while the actual 
	// args never include this.
	Py_ssize_t numParams = PySequence_Length(typedescs);
	if (PyErr_Occurred()) goto done;
	mPyTypeDesc.SetLength(numParams);

	m_pyparams = PySequence_GetItem(obParams, 1);
	if (!m_pyparams) goto done;

	// Pull apart the type descs and stash them.
	for (i = 0; i < numParams; i++) {
		PyObject *desc_object = PySequence_GetItem(typedescs, i);
		if (!desc_object)
			goto done;

		// Pull apart the typedesc tuple back into a structure we can work with.
		PyObject *obIID; // This doesn't hold a ref
		PythonTypeDescriptor &ptd = mPyTypeDesc[i];
		// Array-of-array is not supported; use it as a sentiel
		ptd.array_type = nsXPTType::T_ARRAY;
		bool this_ok = PyArg_ParseTuple(desc_object, "bbbbO|b:type_desc",
		                                &ptd.param_flags, &ptd.type_flags,
		                                &ptd.argnum, &ptd.argnum2,
		                                &obIID, &ptd.array_type);
		Py_DECREF(desc_object);
		if (!this_ok) goto done;

		// The .py code may send a 0 as the IID!
		if (obIID != Py_None && !PyInt_Check(obIID)) {
			if (!Py_nsIID::IIDFromPyObject(obIID, &ptd.iid))
				goto done;
		}
	}
	ok = ProcessPythonTypeDescriptors(mPyTypeDesc.Elements(), mPyTypeDesc.Length(),
	                                  &min_num_params, &max_num_params);
	if (!ok) {
		goto done;
	}

	// OK - check we got the number of args we expected.
	// If not, its really an internal error rather than the user.
	num_args_provided = PySequence_Length(m_pyparams);
	if ((num_args_provided < min_num_params) || (num_args_provided > max_num_params)) {
		if (min_num_params == max_num_params) {
			PyErr_Format(PyExc_ValueError,
			             "The type descriptions indicate %d args are needed, but %d were provided",
			             max_num_params, num_args_provided);
		} else {
			PyErr_Format(PyExc_ValueError,
			             "The type descriptions indicate between %d to %d args are needed, but %d were provided",
			             min_num_params, max_num_params, num_args_provided);
		}
		ok = false;
		goto done;
	}

	// Init the parameters to pass to XPCOM
	mDispatchParams.SetLength(numParams);
	// We need to initialize params
	{ /* scope */
		nsXPTCMiniVariant mv;
		memset(&mv, 0, sizeof(mv));
		for (Py_ssize_t i = 0; i < numParams; ++i) {
			mDispatchParams[i].Init(mv, nsXPTType::T_VOID, 0);
			MOZ_ASSERT(!mDispatchParams[i].val.p);
		}
	}

	ok = true;
done:
	if (!ok && !PyErr_Occurred())
		PyErr_NoMemory();

	Py_XDECREF(typedescs);
	return ok;
}


bool PyXPCOM_InterfaceVariantHelper::PrepareCall()
{
	int param_index = 0;
	int i;
	MOZ_ASSERT(PyGILState_GetThisThreadState());
	MOZ_ASSERT(mPyTypeDesc.Length() == mDispatchParams.Length());
	for (i = 0; i < mPyTypeDesc.Length(); ++i) {
		PythonTypeDescriptor &ptd = mPyTypeDesc[i];
		nsXPTCVariant &dp = mDispatchParams[i];
		// stash the type_flags into the variant, and remember how many extra
		// bits of info we have.
		dp.type = ptd.type_flags;
		MOZ_ASSERT(dp.val.p == nullptr || (ptd.IsAutoIn() && ptd.IsAutoSet()));
		MOZ_ASSERT(dp.ptr == nullptr || (ptd.IsAutoIn() && ptd.IsAutoSet()));
		if (ptd.IsIn() && !ptd.IsAutoIn() && !ptd.IsDipper()) {
			if (!FillInVariant(ptd, i, param_index))
				return false;
			param_index++;
		}
		if ((ptd.IsOut() && !ptd.IsAutoOut()) || ptd.IsDipper()) {
			if (!PrepareOutVariant(ptd, i))
				return false;
		}
	}
	// There may be out "size_is" params we havent touched yet
	// (ie, as the param itself is marked "out", we never got to
	// touch the associated "size_is".
	// Final loop to handle this.
	for (i = 0; i < mPyTypeDesc.Length(); ++i) {
		PythonTypeDescriptor &ptd = mPyTypeDesc[i];
		if (ptd.IsOut() && ptd.IsAutoOut() && !ptd.IsAutoSet()) {
			// Call PrepareOutVariant to ensure buffers etc setup.
			if (!PrepareOutVariant(ptd, i))
				return false;
		}
	}
	return true;
}


bool PyXPCOM_InterfaceVariantHelper::SetSizeOrLengthIs(int var_index, bool is_size, uint32_t new_size)
{
	MOZ_ASSERT(PyGILState_GetThisThreadState());
	MOZ_ASSERT(var_index < mPyTypeDesc.Length(), "var_index param is invalid");
	uint8_t argnum = is_size ?
		mPyTypeDesc[var_index].size_is :
		mPyTypeDesc[var_index].length_is;
	MOZ_ASSERT(argnum < mPyTypeDesc.Length(), "size_is param is invalid");
	PythonTypeDescriptor &td_size = mPyTypeDesc[argnum];
	MOZ_ASSERT(td_size.IsAutoIn() || td_size.IsAutoOut(),
			   "Setting size_is/length_is, but param is not marked as auto!");
	MOZ_ASSERT(td_size.TypeTag() == nsXPTType::T_U32,
			   "size param must be Uint32");
	MOZ_ASSERT(!td_size.IsPointer(),
			   "size_is must not be a pointer");
	nsXPTCVariant &ns_v = mDispatchParams[argnum];

	if (!td_size.IsAutoSet()) {
		ns_v.type = td_size.type_flags;
		ns_v.val.u32 = new_size;
		// In case it is "out", setup the necessary pointers.
		if (td_size.IsOut())
			PrepareOutVariant(td_size, argnum);
		td_size.have_set_auto = true;
	} else {
		if (ns_v.val.u32 != new_size) {
			PyErr_Format(PyExc_ValueError,
			             "Array lengths inconsistent; array size previously set to %d, but second array is of size %d",
			             ns_v.val.u32, new_size);
			return false;
		}
	}
	return true;
}

uint32_t PyXPCOM_InterfaceVariantHelper::GetSizeOrLengthIs(int var_index, bool is_size)
{
	MOZ_ASSERT(PyGILState_GetThisThreadState());
	MOZ_ASSERT(var_index < mPyTypeDesc.Length(), "var_index param is invalid");
	PRUint8 argnum = is_size ?
		mPyTypeDesc[var_index].size_is :
		mPyTypeDesc[var_index].length_is;
	MOZ_ASSERT(argnum < mPyTypeDesc.Length(),
			   "size_is param is invalid");
	const PythonTypeDescriptor &ptd = mPyTypeDesc[argnum];
	MOZ_ASSERT(ptd.TypeTag() == nsXPTType::T_U32, "size param must be Uint32");
	MOZ_ASSERT(!ptd.IsPointer(), "size param must not be a pointer");
	nsXPTCVariant &ns_v = mDispatchParams[argnum];
	MOZ_ASSERT(!ptd.IsOut() || ns_v.ptr == &ns_v.val);
	return ns_v.val.u32;
}

#define ASSIGN_INT(type, field, unsigned)                               \
	{                                                                   \
		if (val == Py_None) {                                           \
			ns_v.val.field = 0;                                         \
			break;                                                      \
		}                                                               \
		if (!(val_use = PyNumber_Int(val))) BREAK_FALSE                 \
		long num = PyInt_AsLong(val_use);                               \
		if (num == -1 && PyErr_Occurred()) BREAK_FALSE                  \
		if ((unsigned && num < 0) || static_cast<type>(num) != num) {   \
			PyErr_Format(PyExc_OverflowError,                           \
						 "param %d (%ld) does not fit in %s",           \
						 value_index, num, NS_STRINGIFY(type));         \
			return false;                                            \
		}                                                               \
		ns_v.val.field = static_cast<type>(num);                        \
	}

bool PyXPCOM_InterfaceVariantHelper::FillInVariant(const PythonTypeDescriptor &td, int value_index, int param_index)
{
	bool rc = true;
	MOZ_ASSERT(PyGILState_GetThisThreadState());
	// Get a reference to the variant we are filling for convenience.
	nsXPTCVariant &ns_v = mDispatchParams[value_index];
	MOZ_ASSERT(ns_v.type == td.type_flags,
	           "Expecting variant all setup for us");
	MOZ_ASSERT(td.IsIn(),
	           "Trying to fill 'in' variant that isn't an 'in' param");
	MOZ_ASSERT(!td.IsAutoIn(),
	           "Param is 'auto-in', but we are filling it normally!");
	MOZ_ASSERT(!td.IsDipper(),
	           "Param is 'dipper', we don't konw what to fill it with!");
	// We used to avoid passing internal buffers to PyString etc objects
	// for 2 reasons: paranoia (so incorrect external components couldn't break
	// Python) and simplicity (in vs in-out issues, etc)
	// However, at least one C++ implemented component (nsITimelineService)
	// uses a "char *", and keys on the address (assuming that the same
	// *pointer* is passed rather than value.  Therefore, we have a special case
	// - T_CHAR_STR that is "in" gets the Python string pointer passed.
	PyObject *val_use = nullptr; // a temp object converters can use, and will be DECREF'd
	PyObject *val = PySequence_GetItem(m_pyparams, param_index);
	MOZ_ASSERT(val, "Have an 'in' param, but no Python value!");
	if (!val) {
		PyErr_Format(PyExc_ValueError,
		             "Param %d is marked as 'in', but no value was given", value_index);
		return false;
	}
	// Cast this to the enum so we can get warnings about missing cases
	switch (static_cast<XPTTypeDescriptorTags>(ns_v.type.TagPart())) {
	  case TD_INT8:
		ASSIGN_INT(int8_t, i8, false);
		break;
	  case TD_INT16:
		ASSIGN_INT(int16_t, i16, false);
		break;
	  case TD_INT32:
		ASSIGN_INT(int32_t, i32, false);
		break;
	  case TD_INT64:
		if (val == Py_None) {
			ns_v.val.i64 = 0;
			break;
		}
		if ((val_use=PyNumber_Long(val)) == NULL) BREAK_FALSE
		ns_v.val.i64 = static_cast<int64_t>(PyLong_AsLongLong(val_use));
		if (ns_v.val.i64 == (PY_LONG_LONG)-1 && PyErr_Occurred()) BREAK_FALSE
		break;
	  case TD_UINT8:
		ASSIGN_INT(uint8_t, u8, true);
		break;
	  case TD_UINT16:
		ASSIGN_INT(uint16_t, u16, true);
		break;
	  case TD_UINT32: {
		if (val == Py_None) {
			ns_v.val.u32 = 0;
			break;
		}
		if (!(val_use = PyNumber_Int(val))) BREAK_FALSE
		if (sizeof(long) <= sizeof(PRUint32) && PyLong_Check(val_use)) {
			// Value doesn't fit in an int
			unsigned long num = PyLong_AsUnsignedLong(val_use);
			if (PyErr_Occurred()) {
				// negative value, or something
				BREAK_FALSE
			}
			ns_v.val.u32 = static_cast<uint32_t>(num);
		} else {
			// Value fits in a (signed) int
			long num = PyInt_AsLong(val_use);
			if (num == -1 && PyErr_Occurred()) BREAK_FALSE
			if ((num < 0) || static_cast<uint32_t>(num) != num) {
				PyErr_Format(PyExc_OverflowError,
				             "param %d (%ld) does not fit in %s",
				             value_index, num, "uint32_t");
				BREAK_FALSE
			}
			ns_v.val.u32 = static_cast<uint32_t>(num);
		}
		}
		break;
	  case TD_UINT64:
		if (val == Py_None) {
			ns_v.val.u64 = 0;
			break;
		}
		if ((val_use=PyNumber_Long(val)) == NULL) BREAK_FALSE
		ns_v.val.u64 = static_cast<uint64_t>(PyLong_AsUnsignedLongLong(val_use));
		if (ns_v.val.u64 == (unsigned PY_LONG_LONG)-1 && PyErr_Occurred()) BREAK_FALSE
		break;
	  case TD_FLOAT:
		if (val == Py_None) {
			ns_v.val.f = 0;
			break;
		}
		if ((val_use=PyNumber_Float(val)) == NULL) BREAK_FALSE
		ns_v.val.f = static_cast<float>(PyFloat_AsDouble(val_use));
		break;
	  case TD_DOUBLE:
		if (val == Py_None) {
			ns_v.val.d = 0;
			break;
		}
		if ((val_use=PyNumber_Float(val)) == NULL) BREAK_FALSE
		ns_v.val.d = PyFloat_AsDouble(val_use);
		break;
	  case TD_BOOL:
		if (val == Py_None) {
			ns_v.val.b = false;
			break;
		}
		if ((val_use=PyNumber_Int(val)) == NULL) BREAK_FALSE
		ns_v.val.b = (0 != PyInt_AsLong(val_use));
		break;
	  case TD_CHAR:{
		if (!PyString_Check(val) && !PyUnicode_Check(val)) {
			PyErr_SetString(PyExc_TypeError, "This parameter must be a string or Unicode object");
			BREAK_FALSE;
		}
		if ((val_use = PyObject_Str(val)) == NULL)
			BREAK_FALSE;
		// Sanity check should PyObject_Str() ever loosen its semantics wrt Unicode!
		MOZ_ASSERT(PyString_Check(val_use), "PyObject_Str didn't return a string object!");
		if (PyString_GET_SIZE(val_use) != 1) {
			PyErr_SetString(PyExc_ValueError, "Must specify a one character string for a character");
			BREAK_FALSE;
		}

		ns_v.val.c = *PyString_AS_STRING(val_use);
		break;
		}

	  case TD_WCHAR: {
		if (!PyString_Check(val) && !PyUnicode_Check(val)) {
			PyErr_SetString(PyExc_TypeError, "This parameter must be a string or Unicode object");
			BREAK_FALSE;
		}
		if ((val_use = PyUnicode_FromObject(val)) == NULL)
			BREAK_FALSE;
		// Sanity check should PyObject_Str() ever loosen its semantics wrt Unicode!
		MOZ_ASSERT(PyUnicode_Check(val_use), "PyUnicode_FromObject didnt return a unicode object!");
		if (PyUnicode_GetSize(val_use) != 1) {
			PyErr_SetString(PyExc_ValueError, "Must specify a one character string for a character");
			BREAK_FALSE;
		}
		// Lossy!
		ns_v.val.wc = *PyUnicode_AS_UNICODE(val_use);
		break;
		}

	  case TD_PNSIID: {
		nsIID *iid;
		if (!Alloc(iid, 1, __FILE__, __LINE__)) {
			PyErr_NoMemory();
			BREAK_FALSE;
		}
		if (!Py_nsIID::IIDFromPyObject(val, iid)) {
			Free(iid);
			BREAK_FALSE;
		}
		ns_v.val.p = iid;
		ns_v.SetValNeedsCleanup();
		break;
	  }
	  case TD_ASTRING:
	  case TD_DOMSTRING: {
		nsString *s;
		if (!Alloc(s, 1, __FILE__, __LINE__)) {
			PyErr_NoMemory();
			BREAK_FALSE;
		}
		ns_v.val.p = s;
		// We created it - flag as such for cleanup.
		ns_v.SetValNeedsCleanup();

		if (!PyObject_AsNSString(val, *s))
			BREAK_FALSE;
		break;
	  }
	  case TD_CSTRING:
	  case TD_UTF8STRING: {
		bool bIsUTF8 = ns_v.type.TagPart() == nsXPTType::T_UTF8STRING;
		nsCString* str;
		if (!Alloc(str, 1, __FILE__, __LINE__)) {
			PyErr_NoMemory();
			BREAK_FALSE;
		}
		if (val == Py_None) {
			str->SetIsVoid(true);
		} else {
			// strings are assumed to already be UTF8 encoded.
			if (PyString_Check(val)) {
				val_use = val;
				Py_INCREF(val);
			// Unicode objects are encoded by us.
			} else if (PyUnicode_Check(val)) {
				if (bIsUTF8)
					val_use = PyUnicode_AsUTF8String(val);
				else
					val_use = PyObject_Str(val);
			} else {
				PyErr_SetString(PyExc_TypeError, "UTF8 parameters must be string or Unicode objects");
				val_use = nullptr;
			}
			if (!val_use) {
				delete str;
				BREAK_FALSE;
			}
			str->Assign(PyString_AS_STRING(val_use), PyString_GET_SIZE(val_use));
		}
		ns_v.val.p = str;
		ns_v.SetValNeedsCleanup();
		break;
		}
	  case TD_PSTRING: {
		if (val == Py_None) {
			ns_v.val.p = nullptr;
			break;
		}
		// If an "in" char *, and we have a PyString, then pass the
		// pointer (hoping everyone else plays by the rules too).
		MOZ_ASSERT(!td.IsDipper(), "PSTRING shouldn't be a dipper!");
		if (!td.IsOut() && PyString_Check(val)) {
			ns_v.val.p = PyString_AS_STRING(val);
			MOZ_ASSERT(!ns_v.DoesValNeedCleanup());
			MOZ_ASSERT(!mAllocations.Get(ns_v.val.p),
					   "We didn't allocate that string from Python!");
			// DO NOT need cleanup
			break;
		}

		if (!PyString_Check(val) && !PyUnicode_Check(val)) {
			PyErr_SetString(PyExc_TypeError, "This parameter must be a string or Unicode object");
			BREAK_FALSE;
		}
		if ((val_use = PyObject_Str(val))==NULL)
			BREAK_FALSE;
		// Sanity check should PyObject_Str() ever loosen its semantics wrt Unicode!
		MOZ_ASSERT(PyString_Check(val_use), "PyObject_Str didn't return a string object!");

		char* str;
		if (!Alloc(str, PyString_GET_SIZE(val_use) + 1, __FILE__, __LINE__)) {
			PyErr_NoMemory();
			BREAK_FALSE;
		}
		memcpy(str, PyString_AS_STRING(val_use), PyString_GET_SIZE(val_use) + 1);
		ns_v.val.p = str;
		ns_v.SetValNeedsCleanup();
		break;
		}

	  case TD_PWSTRING: {
		if (val == Py_None) {
			ns_v.val.p = nullptr;
			break;
		}
		if (!PyString_Check(val) && !PyUnicode_Check(val)) {
			PyErr_SetString(PyExc_TypeError, "This parameter must be a string or Unicode object");
			BREAK_FALSE;
		}
		if ((val_use = PyUnicode_FromObject(val))==NULL)
			BREAK_FALSE;
		MOZ_ASSERT(PyUnicode_Check(val_use), "PyUnicode_FromObject didnt return a Unicode object!");
		char16_t *sv = nullptr;
		PRUint32 nch;
		if (PyUnicode_Aschar16_t(val_use, &sv, &nch) < 0)
			BREAK_FALSE;
		ns_v.val.p = sv;
		ns_v.SetValNeedsCleanup();
		break;
		}
	  case TD_INTERFACE_TYPE:  {
		if (!Py_nsISupports::InterfaceFromPyObject(val,
		                                           td.iid,
		                                           reinterpret_cast<nsISupports **>(&ns_v.val.p),
		                                           true))
			BREAK_FALSE;
		if (ns_v.val.p) {
			// We have added a reference - flag as such for cleanup.
			MarkAlloc(ns_v.val.p, __FILE__, __LINE__);
			ns_v.SetValNeedsCleanup();
		}
		break;
		}
	  case TD_INTERFACE_IS_TYPE: {
		nsIID iid;
		nsXPTCVariant &ns_viid = mDispatchParams[td.iid_is];
		MOZ_ASSERT(ns_viid.type.TagPart() == TD_PNSIID,
				   "The INTERFACE_IS iid describer isn't an IID!");
		// This is a pretty serious problem, but not Python's fault!
		// Just return an nsISupports and hope the caller does whatever
		// QI they need before using it.
		if (ns_viid.type.TagPart() == TD_PNSIID &&
			XPT_PD_IS_IN(ns_viid.type))
		{
			nsIID *piid = reinterpret_cast<nsIID *>(ns_viid.val.p);
			if (!piid)
				// Also serious, but like below, not our fault!
				iid = NS_GET_IID(nsISupports);
			else
				iid = *piid;
		} else {
			// Use NULL IID to avoid a QI in this case.
			iid = Py_nsIID_NULL;
		}
		if (!Py_nsISupports::InterfaceFromPyObject(val,
		                                           iid,
		                                           (nsISupports **)&ns_v.val.p,
		                                           true))
			BREAK_FALSE;
		// We have added a reference - flag as such for cleanup.
		MarkAlloc(ns_v.val.p, __FILE__, __LINE__);
		ns_v.SetValNeedsCleanup();
		break;
		}
	  case TD_PSTRING_SIZE_IS: {
		if (val==Py_None) {
			ns_v.val.p = nullptr;
			break;
		}
		if (!PyString_Check(val) && !PyUnicode_Check(val)) {
			PyErr_SetString(PyExc_TypeError, "This parameter must be a string or Unicode object");
			BREAK_FALSE;
		}
		if ((val_use = PyObject_Str(val))==NULL)
			BREAK_FALSE;
		// Sanity check should PyObject_Str() ever loosen its semantics wrt Unicode!
		NS_ABORT_IF_FALSE(PyString_Check(val_use), "PyObject_Str didn't return a string object!");

		char* str;
		const Py_ssize_t size = PyString_GET_SIZE(val_use);
		if (!Alloc(str, size + 1, __FILE__, __LINE__)) {
			PyErr_NoMemory();
			BREAK_FALSE;
		}
		memcpy(str, PyString_AS_STRING(val_use), size);
		str[size] = '\0'; // be safe
		ns_v.val.p = str;
		ns_v.SetValNeedsCleanup();
		rc = SetSizeIs(value_index, size); // excludes terminating null
		break;
		}

	case TD_PWSTRING_SIZE_IS: {
		if (val==Py_None) {
			ns_v.val.p = nullptr;
			break;
		}
		if (!PyString_Check(val) && !PyUnicode_Check(val)) {
			PyErr_SetString(PyExc_TypeError, "This parameter must be a string or Unicode object");
			BREAK_FALSE;
		}
		if ((val_use = PyUnicode_FromObject(val))==NULL)
			BREAK_FALSE;
		// Sanity check should PyObject_Str() ever loosen its semantics wrt Unicode!
		NS_ABORT_IF_FALSE(PyUnicode_Check(val_use), "PyObject_Unicode didnt return a unicode object!");
		char16_t *sv = nullptr;
		PRUint32 nch;
		if (PyUnicode_Aschar16_t(val_use, &sv, &nch) < 0)
			BREAK_FALSE;
		ns_v.val.p = sv;
		ns_v.SetValNeedsCleanup();
		rc = SetSizeIs(value_index, nch); // excludes terminating null
		break;
		}
	case TD_ARRAY: {
		if (val == Py_None) {
			ns_v.val.p = nullptr;
			break;
		}
		if (td.ArrayTypeTag() == nsXPTType::T_ARRAY) {
			// we can't deal with array of array (but then, nor can XPIDL)
			PyErr_SetString(PyExc_TypeError, "The array info is not valid");
			BREAK_FALSE;
		}
		if (!PySequence_Check(val)) {
			PyErr_SetString(PyExc_TypeError, "This parameter must be a sequence");
			BREAK_FALSE;
		}

		PRUint32 element_size = GetArrayElementSize(td.ArrayTypeTag());
		Py_ssize_t seq_length = PySequence_Length(val);
		ns_v.val.p = Alloc(element_size, seq_length, __FILE__, __LINE__);
		if (!ns_v.val.p) {
			PyErr_NoMemory();
			BREAK_FALSE;
		}
		rc = FillSingleArray(ns_v.val.p, val, seq_length,
		                     element_size, td.ArrayTypeTag(),
		                     td.iid);
		rc &= SetLengthIs(value_index, seq_length);
		if (!rc) {
			Free(ns_v.val.p);
			ns_v.val.p = nullptr;
			break;
		}
		if (!static_cast<nsXPTType>(td.ArrayTypeTag()).IsArithmetic())
			ns_v.SetValNeedsCleanup();
		break;
		}
	case TD_VOID:
	case TD_JSVAL:
		PyErr_Format(PyExc_TypeError,
					 "The object type (0x%x) is unknown", ns_v.type.TagPart());
		rc = false;
		break;
	}
	#if DEBUG
		if (rc && !PyErr_Occurred()) {
			if (static_cast<nsXPTType>(td.TypeTag()).IsArithmetic()) {
				MOZ_ASSERT(ns_v.ptr == nullptr,
						   "Arithmetic params shouldn't be pointers");
			} else {
				switch (ns_v.type.TagPart()) {
					case nsXPTType::T_INTERFACE:
					case nsXPTType::T_INTERFACE_IS:
						if (ns_v.val.p) {
							MOZ_ASSERT(ns_v.DoesValNeedCleanup(),
									   "Non-null interfaces should need cleanup!");
						} else {
							MOZ_ASSERT(!ns_v.DoesValNeedCleanup(),
									   "Null interfaces should not need cleanup!");
						}
						break;
					case TD_ARRAY: {
						MOZ_ASSERT(val == Py_None || ns_v.val.p != nullptr,
								   "Non-empty arrays should be allocated!");
						// ns_v.DoesValNeedCleanup() checking is... harder
						break;
						}
					case nsXPTType::T_CHAR_STR:
						if (!td.IsOut() && PyString_Check(val)) {
							// Optimization in effect, this does not need cleanup
							MOZ_ASSERT(ns_v.val.p != nullptr,
									   "String should not be null");
							break;
						}
						// fall through
					default:
						MOZ_ASSERT(val == Py_None || ns_v.val.p != nullptr,
								   "Non-arithmetic params should allocate");
						MOZ_ASSERT(!ns_v.val.p || ns_v.DoesValNeedCleanup(),
								   "Allocated things should need cleanup!");
				}
			}
		}
	#endif
	Py_DECREF(val); // Can't be NULL!
	Py_XDECREF(val_use);
	return rc && !PyErr_Occurred();
}
#undef ASSIGN_INT

bool PyXPCOM_InterfaceVariantHelper::PrepareOutVariant(const PythonTypeDescriptor &td, int value_index)
{
	MOZ_ASSERT(PyGILState_GetThisThreadState());
	MOZ_ASSERT(td.IsDipper() == td.IsDipperType(), "inconsistent dipper usage");
	MOZ_ASSERT(td.IsOut() || td.IsDipper() || (td.IsAutoOut() && !td.IsAutoSet()),
	           "Shouldn't have gotten here");
	if (!(td.IsOut() || td.IsDipper() || (td.IsAutoOut() && !td.IsAutoSet()))) {
		// No need to do anything here
		return true;
	}

	nsXPTCVariant &ns_v = mDispatchParams[value_index];
	// Do the out param thang...
	MOZ_ASSERT(ns_v.ptr == nullptr, "already have a pointer!");
	// We can be out, inout, or in [dipper]; in all cases, we need to be indirect
	ns_v.SetIndirect();

	if (td.IsDipper()) {
		// Dippers must be empty
		MOZ_ASSERT(!ns_v.val.p);
	}

	#if DEBUG
	if (td.IsIn() && !nsXPTType(td.TypeTag()).IsArithmetic() && ns_v.val.p) {
		// 'inout' param; this will be freed by the callee
		MarkFree(ns_v.val.p);
	}
	#endif

	// Special flags based on the data type
	switch (ns_v.type.TagPart()) {
	  case nsXPTType::T_I8:
	  case nsXPTType::T_I16:
	  case nsXPTType::T_I32:
	  case nsXPTType::T_I64:
	  case nsXPTType::T_U8:
	  case nsXPTType::T_U16:
	  case nsXPTType::T_U32:
	  case nsXPTType::T_U64:
		if (!td.IsIn()) {
			ns_v.val.u64 = 0;
		}
		break;
	  case nsXPTType::T_FLOAT:
		if (!td.IsIn()) {
			ns_v.val.f = 0;
		}
		break;
	  case nsXPTType::T_DOUBLE:
		if (!td.IsIn()) {
			ns_v.val.d = 0;
		}
		break;
	  case nsXPTType::T_BOOL:
		if (!td.IsIn()) {
			ns_v.val.b = false;
		}
		break;
	  case nsXPTType::T_CHAR:
		if (!td.IsIn()) {
			ns_v.val.c = '\0';
		}
		break;
	  case nsXPTType::T_WCHAR:
		if (!td.IsIn()) {
			ns_v.val.wc = char16_t('\0');
		}
		break;
	  case nsXPTType::T_VOID:
		if (!td.IsIn()) {
			ns_v.val.p = nullptr; // Not really, but close enough
		}
		break;

	  case nsXPTType::T_INTERFACE:
	  case nsXPTType::T_INTERFACE_IS:
		if (!td.IsIn()) {
			MOZ_ASSERT(!ns_v.val.p, "Can't have an interface pointer!");
		}
		// Nothing is in there yet, no need to cleanup
		break;
	  case nsXPTType::T_ARRAY:
		if (!td.IsIn()) {
			MOZ_ASSERT(!ns_v.val.p, "Garbage in our pointer?");
			// Don't do anything; the callee will allocate
		} else {
			// We've already got space (i.e. inout)
			// Make sure that we _did_ allocate something; XPConnect
			// will expect some place to dump the result into
			if (!ns_v.DoesValNeedCleanup()) {
				if (!ns_v.val.p) {
					PRUint32 element_size = GetArrayElementSize(td.ArrayTypeTag());
					uint32_t size = GetSizeIs(value_index);
					ns_v.val.p = Alloc(element_size, size, __FILE__, __LINE__);
					if (!ns_v.val.p) {
						PyErr_NoMemory();
						return false;
					}
					memset(ns_v.val.p, 0, element_size * size);
					if (!static_cast<nsXPTType>(td.ArrayTypeTag()).IsArithmetic())
						ns_v.SetValNeedsCleanup();
					#if DEBUG
						// callee will free for us (length can change)
						MarkFree(ns_v.val.p);
					#endif
				}
			} else {
				// we have allocated space due to the |in| part
				MOZ_ASSERT(ns_v.val.p);
			}
		}
		break;
	  case nsXPTType::T_PWSTRING_SIZE_IS:
	  case nsXPTType::T_PSTRING_SIZE_IS:
	  case nsXPTType::T_WCHAR_STR:
	  case nsXPTType::T_CHAR_STR:
	  case nsXPTType::T_IID:
		if (!ns_v.DoesValNeedCleanup()) {
			MOZ_ASSERT(!td.IsIn(), "got to an allocating type, but is in?");
			MOZ_ASSERT(!ns_v.val.p, "Garbage in our pointer?");
			// Don't do anything; the callee will allocate
		} else {
			// We've already got space (i.e. inout)
			// Don't worry about it
			MOZ_ASSERT(ns_v.val.p, "NeedsCleanup set but nothing there!");
		}
		break;
	  case nsXPTType::T_DOMSTRING:
	  case nsXPTType::T_ASTRING: {
		MOZ_ASSERT(ns_v.val.p == nullptr,
				   "T_ASTRINGs can't be out and have a value (ie, no in/outs are allowed!");
		MOZ_ASSERT(ns_v.ptr == &ns_v.val); // from ns_v.SetIndirect()
		MOZ_ASSERT(td.IsDipper(),
				   "out AStrings must really be in dippers!");
		MOZ_ASSERT(!ns_v.DoesValNeedCleanup(),
				   "T_ASTRING shouldn't already need cleanup!");
		// Dippers are really treated like "in" params.
		nsString * str;
		if (!Alloc(str, 1, __FILE__, __LINE__)) {
			PyErr_NoMemory();
			return false;
		}
		// ns_v.ptr is the one that is read, but we free ns_v.val.p, so...
		ns_v.ptr = ns_v.val.p = str;
		ns_v.SetValNeedsCleanup();
		break;
		}
	  case nsXPTType::T_CSTRING:
	  case nsXPTType::T_UTF8STRING: {
		MOZ_ASSERT(!ns_v.val.p,
		           "T_CSTRINGs can't be out and have a value (ie, no in/outs are allowed!");
		MOZ_ASSERT(ns_v.ptr == &ns_v.val); // from ns_v.SetIndirect()
		MOZ_ASSERT(td.IsDipper(),
		           "out ACStrings must really be in dippers!");
		MOZ_ASSERT(!ns_v.DoesValNeedCleanup(),
		           "T_CSTRING shouldn't already need cleanup!");
		// Dippers are really treated like "in" params.
		nsCString * str;
		if (!Alloc(str, 1, __FILE__, __LINE__)) {
			PyErr_NoMemory();
			return false;
		}
		MOZ_ASSERT(str->IsEmpty());
		// ns_v.ptr is the one that is read, but we free ns_v.val.p, so...
		ns_v.ptr = ns_v.val.p = str;
		ns_v.SetValNeedsCleanup();
		break;
		}
	  case nsXPTType::T_JSVAL:
		PyErr_Format(PyExc_ValueError,
					 "Don't know how to set [out] jsval at position %i",
					 value_index);
		return false;
		break;
	  default:
		MOZ_CRASH("Unknown type - don't know how to prepare the output value");
		break; // Nothing to do!
	}
	return true;
}

PyObject *PyXPCOM_InterfaceVariantHelper::MakeSinglePythonResult(int index)
{
	nsXPTCVariant &ns_v = mDispatchParams[index];
	PyObject *ret = nullptr;
	MOZ_ASSERT(PyGILState_GetThisThreadState());
	MOZ_ASSERT(ns_v.IsPtrData(), "expecting a pointer if you want a result!");

	// Re-fetch the type descriptor.
	PythonTypeDescriptor &td = mPyTypeDesc[index];
	// Make sure the type tag of the variant hasnt changed on us.
	MOZ_ASSERT(ns_v.type == td.type_flags,
			   "variant type has changed under us!");

	// If the pointer is NULL, we can get out now!
	if (ns_v.ptr == nullptr) {
		Py_INCREF(Py_None);
		return Py_None;
	}

	switch (td.TypeTag()) {
	  case nsXPTType::T_I8:
		ret = PyInt_FromLong( *((PRInt8 *)ns_v.ptr) );
		break;
	  case nsXPTType::T_I16:
		ret = PyInt_FromLong( *((PRInt16 *)ns_v.ptr) );
		break;
	  case nsXPTType::T_I32:
		ret = PyInt_FromLong( *((PRInt32 *)ns_v.ptr) );
		break;
	  case nsXPTType::T_I64:
		ret = PyLong_FromLongLong( *((PRInt64 *)ns_v.ptr) );
		break;
	  case nsXPTType::T_U8:
		ret = PyInt_FromLong( *((PRUint8 *)ns_v.ptr) );
		break;
	  case nsXPTType::T_U16:
		ret = PyInt_FromLong( *((PRUint16 *)ns_v.ptr) );
		break;
	  case nsXPTType::T_U32:
		if (*((long *)ns_v.ptr) >= 0) {
			ret = PyInt_FromLong( *((PRUint32 *)ns_v.ptr) );
		} else {
			// Doesn't fit in an int, use a long
			ret = PyLong_FromUnsignedLong( *((PRUint32 *)ns_v.ptr) );
		}
		break;
	  case nsXPTType::T_U64:
		ret = PyLong_FromUnsignedLongLong( *((PRUint64 *)ns_v.ptr) );
		break;
	  case nsXPTType::T_FLOAT:
		ret = PyFloat_FromDouble( *((float *)ns_v.ptr) );
		break;
	  case nsXPTType::T_DOUBLE:
		ret = PyFloat_FromDouble( *((double *)ns_v.ptr) );
		break;
	  case nsXPTType::T_BOOL:
		ret = *((bool *)ns_v.ptr) ? Py_True : Py_False;
		Py_INCREF(ret);
		break;
	  case nsXPTType::T_CHAR:
		ret = PyString_FromStringAndSize( ((char *)ns_v.ptr), 1 );
		break;

	  case nsXPTType::T_WCHAR:
		ret = PyUnicode_Fromchar16_t( ((char16_t *)ns_v.ptr), 1 );
		break;
	  case nsXPTType::T_VOID:
		// we really can't do anything useful with this; just pass it to
		// Python as an integer and hope it's close enough
		ret = PyLong_FromVoidPtr( *((void **)ns_v.ptr));
		break;
	  case nsXPTType::T_IID: {
		// guard against null IIDs
		nsIID* iid = *reinterpret_cast<nsIID**>(ns_v.ptr);
		if (iid == NULL) {
			ret = Py_None;
			Py_INCREF(Py_None);
		} else {
			ret = Py_nsIID::PyObjectFromIID(*iid);
		}
		break;
	    }
	  case nsXPTType::T_ASTRING:
	  case nsXPTType::T_DOMSTRING: {
		nsAString *rs = reinterpret_cast<nsAString*>(ns_v.ptr);
		ret = PyObject_FromNSString(*rs);
		break;
		}
	  case nsXPTType::T_UTF8STRING: {
		nsCString *rs = reinterpret_cast<nsCString*>(ns_v.ptr);
		ret = PyObject_FromNSString(*rs, true);
		break;
		}
	  case nsXPTType::T_CSTRING: {
		nsCString *rs = reinterpret_cast<nsCString*>(ns_v.ptr);
		ret = PyString_FromNSString(*rs);
		break;
		}

	  case nsXPTType::T_CHAR_STR: {
		char* str = *reinterpret_cast<char**>(ns_v.ptr);
		if (str == nullptr) {
			ret = Py_None;
			Py_INCREF(Py_None);
		} else
			ret = PyString_FromString(str);
		break;
	    }

	  case nsXPTType::T_WCHAR_STR: {
		char16_t *us = *reinterpret_cast<char16_t**>(ns_v.ptr);
		if (us == nullptr) {
			ret = Py_None;
			Py_INCREF(Py_None);
		} else {
			ret = PyUnicode_Fromchar16_t(us, NS_strlen(us));
		}
		break;
		}
	  case nsXPTType::T_INTERFACE: {
		nsISupports *iret = *reinterpret_cast<nsISupports **>(ns_v.ptr);
		MOZ_ASSERT(ns_v.ptr == &ns_v.val.p);
		// Our cleanup code manages iret reference ownership, and our
		// new object takes its own.
		if (td.iid.Equals(NS_GET_IID(nsIVariant)))
			ret = PyObject_FromVariant(m_parent, (nsIVariant *)iret);
		else
			ret = m_parent->MakeInterfaceResult(iret, td.iid);
		NS_IF_RELEASE(iret);
		ns_v.val.p = nullptr;
		break;
		}
	  case nsXPTType::T_INTERFACE_IS: {
		nsIID iid;
		MOZ_ASSERT(td.iid_is < mDispatchParams.Length(),
				   "Looking for an IID that doesn't exist!");
		nsXPTCVariant &ns_viid = mDispatchParams[td.iid_is];
		MOZ_ASSERT(ns_viid.type.TagPart() == nsXPTType::T_IID,
		           "The INTERFACE_IS iid describer isn't an IID!");
		if (ns_viid.type.TagPart() == nsXPTType::T_IID) {
			nsIID *piid = reinterpret_cast<nsIID*>(ns_viid.val.p);
			if (piid == nullptr) {
				// Also serious, but like below, not our fault!
				iid = NS_GET_IID(nsISupports);
			} else {
				iid = *piid;
			}
		} else {
			// This is a pretty serious problem, but not Python's fault!
			// Just return an nsISupports and hope the caller does whatever
			// QI they need before using it.
			// (Note that the assert above means this shouldn't happen in debug)
			NS_ERROR("Failed to get the IID for T_INTERFACE_IS!");
			iid = NS_GET_IID(nsISupports);
		}
		MOZ_ASSERT(ns_v.ptr == &ns_v.val.p);
		nsISupports *iret = *reinterpret_cast<nsISupports **>(ns_v.ptr);
		if (iid.Equals(NS_GET_IID(nsIVariant))) {
			ret = PyObject_FromVariant(m_parent, reinterpret_cast<nsIVariant *>(iret));
		} else {
			ret = m_parent->MakeInterfaceResult(iret, iid);
		}
		NS_IF_RELEASE(iret);
		ns_v.val.p = nullptr;
		break;
		}
	  case nsXPTType::T_ARRAY: {
		if (*reinterpret_cast<void **>(ns_v.ptr) == nullptr) {
			ret = Py_None;
			Py_INCREF(Py_None);
		} else {
			XPTTypeDescriptorTags array_type = td.ArrayTypeTag();
			uint32_t seq_size = GetLengthIs(index);
			nsIID *iid;
			switch (array_type) {
				case nsXPTType::T_INTERFACE_IS:
				case nsXPTType::T_INTERFACE:
					iid = &td.iid;
					break;
				default:
					iid = nullptr;
			}
			ret = UnpackSingleArray(m_parent,
			                        *reinterpret_cast<void **>(ns_v.ptr),
			                        seq_size, array_type, iid);
		}
		break;
		}

	  case nsXPTType::T_PSTRING_SIZE_IS: {
		char *str = *reinterpret_cast<char**>(ns_v.ptr);
		if (str == nullptr) {
			ret = Py_None;
			Py_INCREF(Py_None);
		} else {
			uint32_t string_size = GetSizeIs(index);
			ret = PyString_FromStringAndSize( str, string_size );
		}
		break;
	    }

	  case nsXPTType::T_PWSTRING_SIZE_IS: {
		char16_t *str = *reinterpret_cast<char16_t**>(ns_v.ptr);
		if (str == NULL) {
			ret = Py_None;
			Py_INCREF(Py_None);
		} else {
			uint32_t string_size = GetSizeIs(index);
			ret = PyUnicode_Fromchar16_t( str, string_size );
		}
		break;
		}
	  default:
		PyErr_Format(PyExc_ValueError, "Unknown XPCOM type code (0x%x)", ns_v.type.TagPart());
		/* ret remains nullptr */
		break;
	}
	return ret;
}


PyObject *PyXPCOM_InterfaceVariantHelper::MakePythonResult()
{
	// First we count the results.
	int i = 0;
	int n_results = 0;
	PyObject *ret = NULL;
	bool have_retval = false;
	MOZ_ASSERT(PyGILState_GetThisThreadState());
	for (i = 0; i < mPyTypeDesc.Length(); ++i) {
		PythonTypeDescriptor &td = mPyTypeDesc[i];
		if (!td.IsAutoOut()) {
			if (td.IsOut() || td.IsDipper())
				n_results++;
			if (td.IsRetval()) {
				MOZ_ASSERT(i == mPyTypeDesc.Length() - 1,
						   "retval should be the last argument");
				MOZ_ASSERT(!have_retval,
						   "should not have more than one [retval]");
				have_retval = true;
			}
		}
	}
	if (n_results == 0) {
		ret = Py_None;
		Py_INCREF(ret);
	} else {
		if (n_results > 1) {
			ret = PyTuple_New(n_results);
			if (ret == NULL)
				return NULL;
		}
		int ret_index = 0;
		int max_index = mPyTypeDesc.Length();
		// Stick the retval at the front if we have have
		if (have_retval && n_results > 1) {
			PyObject *val = MakeSinglePythonResult(mPyTypeDesc.Length() - 1);
			if (val == NULL) {
				Py_DECREF(ret);
				return NULL;
			}
			PyTuple_SET_ITEM(ret, 0, val);
			max_index--;
			ret_index++;
		}

		for (i = 0; ret_index < n_results && i < max_index; i++) {
			if (!mPyTypeDesc[i].IsAutoOut()) {
				if (mPyTypeDesc[i].IsOut() || mPyTypeDesc[i].IsDipper()) {
					PyObject *val = MakeSinglePythonResult(i);
					if (!val) {
						Py_XDECREF(ret);
						return nullptr;
					}
					if (n_results > 1) {
						PyTuple_SET_ITEM(ret, ret_index, val);
						ret_index++;
					} else {
						MOZ_ASSERT(!ret, "shouldn't already have a ret!");
						ret = val;
					}
				}
			}
		}

	}
	return ret;
}

void PyXPCOM_InterfaceVariantHelper::CleanupParam(void* p, nsXPTType& type)
{
	if (!p) {
		return; // nothing to clean up
	}
	switch (static_cast<XPTTypeDescriptorTags>(type.TagPart())) {
        case TD_INTERFACE_TYPE:
        case TD_INTERFACE_IS_TYPE:
			// MUST release thread-lock, incase a Python COM object that re-acquires.
			Py_BEGIN_ALLOW_THREADS;
			reinterpret_cast<nsISupports*>(p)->Release();
			Py_END_ALLOW_THREADS;
			MarkFree(p);
			break;
        case TD_ASTRING:
        case TD_DOMSTRING:
			delete reinterpret_cast<nsString*>(p);
			MarkFree(p);
			break;
        case TD_CSTRING:
        case TD_UTF8STRING:
			delete reinterpret_cast<nsCString*>(p);
			MarkFree(p);
			break;
        case TD_PNSIID:
			Free(p);
			break;
        case TD_ARRAY:
			MOZ_CRASH("CleanupParam doesn't support arrays");
			break;
        case TD_JSVAL:
			MOZ_ASSERT(false, "PyXPCOM shouldn't be playing with jsvals");
			break;
        case TD_PSTRING:
        case TD_PWSTRING:
        case TD_PSTRING_SIZE_IS:
        case TD_PWSTRING_SIZE_IS:
			Free(p);
			break;
        case TD_INT8:
        case TD_INT16:
        case TD_INT32:
        case TD_INT64:
        case TD_UINT8:
        case TD_UINT16:
        case TD_UINT32:
        case TD_UINT64:
        case TD_FLOAT:
        case TD_DOUBLE:
        case TD_BOOL:
        case TD_CHAR:
        case TD_WCHAR:
        case TD_VOID:
			// These don't need to be freed
			break;
		default:
			MOZ_CRASH("Unkown tag");
			break;
	}
}

/*************************************************************************
**************************************************************************

 Helpers when IMPLEMENTING interfaces.

**************************************************************************
*************************************************************************/

PyXPCOM_GatewayVariantHelper::PyXPCOM_GatewayVariantHelper(PyG_Base *gw,
                                                           int method_index,
                                                           const XPTMethodDescriptor *info,
                                                           nsXPTCMiniVariant* params)
{
	m_params = params;
	m_info = info;
	// no references added - this class is only alive for
	// a single gateway invocation
	m_gateway = gw; 
	m_method_index = method_index;
}

PyXPCOM_GatewayVariantHelper::~PyXPCOM_GatewayVariantHelper()
{
}

PyObject *PyXPCOM_GatewayVariantHelper::MakePyArgs()
{
#ifdef __cplusplus
	static_assert(sizeof(XPTParamDescriptor) == sizeof(nsXPTParamInfo),
	              "We depend on nsXPTParamInfo being a wrapper over the XPTParamDescriptor struct");
#else
	MOZ_STATIC_ASSERT(sizeof(XPTParamDescriptor) == sizeof(nsXPTParamInfo),
	                  "We depend on nsXPTParamInfo being a wrapper over the XPTParamDescriptor struct");
#endif

	// Setup our array of Python typedescs, and determine the number of objects we
	// pass to Python.
	mPyTypeDesc.SetLength(m_info->num_args);

	// First loop to count the number of objects
	// we pass to Python
	int i;
	for (i = 0; i < m_info->num_args; i++) {
		XPTParamDescriptor &pi = m_info->params[i];
		PythonTypeDescriptor &td = mPyTypeDesc[i];
		td.param_flags = pi.flags;
		td.type_flags = pi.type.prefix.flags;
		td.argnum = pi.type.argnum;
		td.argnum2 = pi.type.argnum2;
	}
	int min_num_params;
	int max_num_params;
	ProcessPythonTypeDescriptors(mPyTypeDesc.Elements(), mPyTypeDesc.Length(),
								 &min_num_params, &max_num_params);
	PyObject *ret = PyTuple_New(max_num_params);
	if (!ret)
		return nullptr;
	int this_arg = 0;
	for (i = 0; i < mPyTypeDesc.Length(); i++) {
		PythonTypeDescriptor &td = mPyTypeDesc[i];
		if (td.IsIn() && !td.IsAutoIn() && !td.IsDipper()) {
			PyObject *sub = MakeSingleParam(i, td);
			if (!sub) {
				Py_DECREF(ret);
				return nullptr;
			}
			MOZ_ASSERT(this_arg >= 0 && this_arg < max_num_params,
					   "We are going off the end of the array!");
			PyTuple_SET_ITEM(ret, this_arg, sub);
			this_arg++;
		}
	}
	MOZ_ASSERT(this_arg >= min_num_params,
	           "We should have gotten at least the minimum number of params!");
	if (this_arg < max_num_params && this_arg >= min_num_params) {
		// There are optional parameters - resize the tuple.
		_PyTuple_Resize(&ret, this_arg);
	}
	return ret;
}

bool PyXPCOM_GatewayVariantHelper::CanSetSizeOrLengthIs(int var_index, bool is_size)
{
	MOZ_ASSERT(var_index >= 0);
	MOZ_ASSERT(var_index < mPyTypeDesc.Length(), "var_index param is invalid");
	uint8_t argnum = is_size ?
		mPyTypeDesc[var_index].size_is :
		mPyTypeDesc[var_index].length_is;
	MOZ_ASSERT(argnum < mPyTypeDesc.Length(), "size_is param is invalid");
	return mPyTypeDesc[argnum].IsOut();
}

bool PyXPCOM_GatewayVariantHelper::SetSizeOrLengthIs(int var_index, bool is_size, uint32_t new_size)
{
	MOZ_ASSERT(var_index >= 0);
	MOZ_ASSERT(var_index < mPyTypeDesc.Length(), "var_index param is invalid");
	PRUint8 argnum = is_size ?
		mPyTypeDesc[var_index].size_is :
		mPyTypeDesc[var_index].length_is;
	MOZ_ASSERT(argnum < mPyTypeDesc.Length(), "size_is param is invalid");
	PythonTypeDescriptor &td_size = mPyTypeDesc[argnum];
	MOZ_ASSERT(td_size.IsOut(),
	           "size param must be out if we want to set it!");
	MOZ_ASSERT(td_size.IsAutoOut(),
	           "Setting size_is, but param is not marked as auto!");

	nsXPTCMiniVariant &ns_v = m_params[argnum];
	MOZ_ASSERT(td_size.TypeTag() == nsXPTType::T_U32,
	           "size param must be Uint32");
	MOZ_ASSERT(ns_v.val.p, "NULL pointer for size_is value!");
	if (!ns_v.val.p) {
		PyErr_Format(PyExc_ValueError,
		             "Invalid size_is value at position %d", var_index);
		return false;
	}
	if (!td_size.IsAutoSet()) {
		*reinterpret_cast<uint32_t*>(ns_v.val.p) = new_size;
		td_size.have_set_auto = true;
	} else {
		if (*reinterpret_cast<uint32_t*>(ns_v.val.p) != new_size) {
			PyErr_Format(PyExc_ValueError,
			             "Array lengths inconsistent; array size previously set to %d, "
			                 "but second array is of size %d",
			             ns_v.val.u32, new_size);
			return false;
		}
	}
	return true;
}

uint32_t PyXPCOM_GatewayVariantHelper::GetSizeOrLengthIs( int var_index, bool is_size)
{
	MOZ_ASSERT(var_index < mPyTypeDesc.Length(), "var_index param is invalid");
	PRUint8 argnum = is_size ?
		mPyTypeDesc[var_index].size_is :
		mPyTypeDesc[var_index].length_is ;
	MOZ_ASSERT(argnum < mPyTypeDesc.Length(), "size_is param is invalid");
	if (argnum >= mPyTypeDesc.Length()) {
		PyErr_SetString(PyExc_ValueError,
		                "don't have a valid size_is indicator for this param");
		return static_cast<uint32_t>(-1);
	}
	PythonTypeDescriptor &ptd = mPyTypeDesc[argnum];
	nsXPTCMiniVariant &ns_v = m_params[argnum];
	MOZ_ASSERT(ptd.TypeTag() == nsXPTType::T_U32, "size param must be Uint32");
	// for some reason, outparams are not pointers here...
	MOZ_ASSERT(!ptd.IsPointer(), "size_is is a pointer");
	return ptd.IsOut() ? *reinterpret_cast<uint32_t*>(ns_v.val.p) : ns_v.val.u32;
}

#undef DEREF_IN_OR_OUT
#define DEREF_IN_OR_OUT( element, ret_type ) \
	(is_out ? *reinterpret_cast<ret_type*>(ns_v.val.p) : static_cast<ret_type>(element))

PyObject *PyXPCOM_GatewayVariantHelper::MakeSingleParam(int index, PythonTypeDescriptor &td)
{
	NS_PRECONDITION(XPT_PD_IS_IN(td.param_flags), "Must be an [in] param!");
	nsXPTCMiniVariant &ns_v = m_params[index];
	PyObject *ret = NULL;
	bool is_out = td.IsOut();

	switch (td.TypeTag()) {
	  case nsXPTType::T_I8:
		ret = PyInt_FromLong( DEREF_IN_OR_OUT(ns_v.val.i8, PRInt8 ) );
		break;
	  case nsXPTType::T_I16:
		ret = PyInt_FromLong( DEREF_IN_OR_OUT(ns_v.val.i16, PRInt16) );
		break;
	  case nsXPTType::T_I32:
		ret = PyInt_FromLong( DEREF_IN_OR_OUT(ns_v.val.i32, PRInt32) );
		break;
	  case nsXPTType::T_I64:
		ret = PyLong_FromLongLong( DEREF_IN_OR_OUT(ns_v.val.i64, PRInt64) );
		break;
	  case nsXPTType::T_U8:
		ret = PyInt_FromLong( DEREF_IN_OR_OUT(ns_v.val.u8, PRUint8) );
		break;
	  case nsXPTType::T_U16:
		ret = PyInt_FromLong( DEREF_IN_OR_OUT(ns_v.val.u16, PRUint16) );
		break;
	  case nsXPTType::T_U32:
		if (DEREF_IN_OR_OUT(ns_v.val.u32, long) >= 0) {
			ret = PyInt_FromLong( DEREF_IN_OR_OUT(ns_v.val.u32, PRUint32) );
		} else {
			ret = PyLong_FromUnsignedLong( DEREF_IN_OR_OUT(ns_v.val.u32, PRUint32) );
		}
		break;
	  case nsXPTType::T_U64:
		ret = PyLong_FromUnsignedLongLong( DEREF_IN_OR_OUT(ns_v.val.u64, PRUint64) );
		break;
	  case nsXPTType::T_FLOAT:
		ret = PyFloat_FromDouble(  DEREF_IN_OR_OUT(ns_v.val.f, float) );
		break;
	  case nsXPTType::T_DOUBLE:
		ret = PyFloat_FromDouble(  DEREF_IN_OR_OUT(ns_v.val.d, double) );
		break;
	  case nsXPTType::T_BOOL: {
		bool temp = DEREF_IN_OR_OUT(ns_v.val.b, bool);
		ret = temp ? Py_True : Py_False;
		Py_INCREF(ret);
		break;
		}
	  case nsXPTType::T_CHAR: {
		char temp = DEREF_IN_OR_OUT(ns_v.val.c, char);
		ret = PyString_FromStringAndSize(&temp, 1);
		break;
		}
	  case nsXPTType::T_WCHAR: {
		char16_t temp = (char16_t)DEREF_IN_OR_OUT(ns_v.val.wc, char16_t);
		ret = PyUnicode_Fromchar16_t(&temp, 1);
		break;
		}
//	  case nsXPTType::T_VOID:
	  case nsXPTType::T_IID: {
		  ret = Py_nsIID::PyObjectFromIID( * DEREF_IN_OR_OUT(ns_v.val.p, const nsIID *) );
		  break;
		}
	  case nsXPTType::T_ASTRING:
	  case nsXPTType::T_DOMSTRING: {
		NS_ABORT_IF_FALSE(is_out || !XPT_PD_IS_DIPPER(td.param_flags), "DOMStrings can't be inout");
		const nsAString *rs = (const nsAString *)ns_v.val.p;
		ret = PyObject_FromNSString(*rs);
		break;
		}
	  case nsXPTType::T_CSTRING: {
		// CStrings get converted to str()
		NS_ABORT_IF_FALSE(is_out || !XPT_PD_IS_DIPPER(td.param_flags), "ACStrings can't be inout");
		const nsCString *rs = (const nsCString *)ns_v.val.p;
		ret = PyString_FromNSString(*rs);
		break;
		}
	  case nsXPTType::T_UTF8STRING: {
		// UTF8 strings get converted to unicode()
		NS_ABORT_IF_FALSE(is_out || !XPT_PD_IS_DIPPER(td.param_flags), "AUTF8Strings can't be inout");
		const nsCString *rs = (const nsCString *)ns_v.val.p;
		ret = PyObject_FromNSString(*rs, true);
		break;
		}
	  case nsXPTType::T_CHAR_STR: {
		char *t = DEREF_IN_OR_OUT(ns_v.val.p, char *);
		if (t==NULL) {
			ret = Py_None;
			Py_INCREF(Py_None);
		} else
			ret = PyString_FromString(t);
		break;
		}

	  case nsXPTType::T_WCHAR_STR: {
		char16_t *us = DEREF_IN_OR_OUT(ns_v.val.p, char16_t *);
		if (us==NULL) {
			ret = Py_None;
			Py_INCREF(Py_None);
		} else {
			ret = PyUnicode_Fromchar16_t( us, NS_strlen(us));
		}
		break;
		}
	  case nsXPTType::T_INTERFACE_IS: // our Python code does it :-)
	  case nsXPTType::T_INTERFACE: {
		nsISupports *iret = DEREF_IN_OR_OUT(ns_v.val.p, nsISupports *);
		nsXPTParamInfo *pi = (nsXPTParamInfo *)m_info->params+index;
		ret = m_gateway->MakeInterfaceParam(iret, NULL, m_method_index, pi, index);
		break;
		}
/***
		nsISupports *iret = DEREF_IN_OR_OUT(ns_v.val.p, nsISupports *);
		nsXPTParamInfo *pi = (nsXPTParamInfo *)m_info->params+index;
		nsXPTCMiniVariant &ns_viid = m_params[td.argnum];
		MOZ_ASSERT(m_python_type_desc_array[td.argnum].TypeTag() == nsXPTType::T_IID,
				   "The INTERFACE_IS iid describer isn't an IID!");
		const nsIID * iid = NULL;
		if (XPT_PD_IS_IN(m_python_type_desc_array[td.argnum].param_flags))
			// may still be inout!
			iid = DEREF_IN_OR_OUT(ns_v.val.p, const nsIID *);

		ret = m_gateway->MakeInterfaceParam(iret, iid, m_method_index, pi, index);
		break;
		}
****/
	  case nsXPTType::T_ARRAY: {
		void *t = DEREF_IN_OR_OUT(ns_v.val.p, void *);
		if (t==NULL) {
			// JS may send us a NULL here occasionally - as the
			// type is array, we silently convert this to a zero
			// length list, a-la JS.
			ret = PyList_New(0);
		} else {
			XPTTypeDescriptorTags array_type;
			nsIID piid;
			nsresult ns = GetArrayType(index, &array_type, &piid);
			if (NS_FAILED(ns)) {
				PyXPCOM_BuildPyException(ns);
				break;
			}
			PRUint32 seq_size = GetLengthIs(index);
			ret = UnpackSingleArray(NULL, t, seq_size, array_type, &piid);
		}
		break;
		}
	  case nsXPTType::T_PSTRING_SIZE_IS: {
		char *t = DEREF_IN_OR_OUT(ns_v.val.p, char *);
		uint32_t string_size = GetSizeIs(index);
		if (t==NULL) {
			ret = Py_None;
			Py_INCREF(Py_None);
		} else
			ret = PyString_FromStringAndSize(t, string_size);
		break;
		}
	  case nsXPTType::T_PWSTRING_SIZE_IS: {
		char16_t *t = DEREF_IN_OR_OUT(ns_v.val.p, char16_t *);
		uint32_t string_size = GetSizeIs(index);
		if (t==NULL) {
			ret = Py_None;
			Py_INCREF(Py_None);
		} else {
			ret = PyUnicode_Fromchar16_t(t, string_size);
		}
		break;
		}
	  default:
		// As this is called by external components,
		// we return _something_ rather than failing before any user code has run!
		{
		char buf[128];
		sprintf(buf, "Unknown XPCOM type flags (0x%x)", td.type_flags);
		PyXPCOM_LogWarning("%s - returning a string object with this message!\n", buf);
		ret = PyString_FromString(buf);
		break;
		}
	}
	return ret;
}

// NOTE: Caller must free iid when no longer needed.
nsresult PyXPCOM_GatewayVariantHelper::GetArrayType(PRUint8 index,
						    XPTTypeDescriptorTags *ret,
						    nsIID *iid)
{
	nsCOMPtr<nsIInterfaceInfoManager> iim(do_GetService(
	                     NS_INTERFACEINFOMANAGER_SERVICE_CONTRACTID));
	MOZ_ASSERT(iim != nullptr, "Cant get interface from IIM!");
	if (!iim)
		return NS_ERROR_FAILURE;

	nsCOMPtr<nsIInterfaceInfo> ii;
	nsresult rc = iim->GetInfoForIID( &m_gateway->m_iid, getter_AddRefs(ii));
	if (NS_FAILED(rc))
		return rc;
	nsXPTType datumType;
	const nsXPTParamInfo& param_info = m_info->params[index];
	rc = ii->GetTypeForParam(m_method_index, &param_info, 1, &datumType);
	if (NS_FAILED(rc))
		return rc;
	if (iid) {
		if (XPT_TDP_TAG(datumType)==nsXPTType::T_INTERFACE ||
		    XPT_TDP_TAG(datumType)==nsXPTType::T_INTERFACE_IS ||
		    XPT_TDP_TAG(datumType)==nsXPTType::T_ARRAY)
		{
			rc = ii->GetIIDForParamNoAlloc(m_method_index, &param_info, iid);
			if (NS_FAILED(rc))
				return rc;
		} else {
			*iid = NS_GET_IID(nsISupports);
		}
	}
	*ret = static_cast<XPTTypeDescriptorTags>(datumType.TagPart());
	MOZ_ASSERT(0 == (*ret & ~XPT_TDP_TAGMASK), "Invalid type descriptor");
	return NS_OK;
}

bool PyXPCOM_GatewayVariantHelper::GetIIDForINTERFACE_ID(int index, const nsIID **ppret)
{
	// Not sure if the IID pointed at by by this is allows to be
	// in or out, so we will allow it.
	nsXPTParamInfo *pi = (nsXPTParamInfo *)m_info->params+index;
	nsXPTType typ = pi->GetType();
	NS_ASSERTION(XPT_TDP_TAG(typ) == nsXPTType::T_IID, "INTERFACE_IS IID param isn't an IID!");
	if (XPT_TDP_TAG(typ) != nsXPTType::T_IID)
		*ppret = &NS_GET_IID(nsISupports);
	else {
		nsXPTCMiniVariant &ns_v = m_params[index];
		if (pi->IsOut()) {
			nsIID **pp = (nsIID **)ns_v.val.p;
			if (pp && *pp)
				*ppret = *pp;
			else
				*ppret = &NS_GET_IID(nsISupports);
		} else if (pi->IsIn()) {
			nsIID *p = (nsIID *)ns_v.val.p;
			if (p)
				*ppret = p;
			else
				*ppret = &NS_GET_IID(nsISupports);
		} else {
			NS_ERROR("Param is not in or out!");
			*ppret = &NS_GET_IID(nsISupports);
		}
	}
	return true;
}

nsIInterfaceInfo *PyXPCOM_GatewayVariantHelper::GetInterfaceInfo()
{
	if (!m_interface_info) {
		nsCOMPtr<nsIInterfaceInfoManager> iim(do_GetService(
		                NS_INTERFACEINFOMANAGER_SERVICE_CONTRACTID));
		if (iim)
			iim->GetInfoForIID(&m_gateway->m_iid, getter_AddRefs(m_interface_info));
	}
	return m_interface_info;
}

#undef FILL_SIMPLE_POINTER
#define FILL_SIMPLE_POINTER( type, ob ) *((type *)ns_v.val.p) = (type)(ob)

nsresult PyXPCOM_GatewayVariantHelper::BackFillVariant( PyObject *val, int index)
{
	const nsXPTParamInfo& pi = m_info->params[index];
	MOZ_ASSERT(pi.IsOut() || pi.IsDipper(),
	           "The value must be marked as [out] (or a dipper) to be back-filled!");
	MOZ_ASSERT(!pi.IsShared(),
	           "Don't know how to back-fill a shared out param");
	nsXPTCMiniVariant &ns_v = m_params[index];

	nsXPTType type = pi.GetType();
	PyObject* val_use = NULL;

	// Ignore out params backed by a NULL pointer. The caller isn't
	// interested in them, see:
	// https://bugzilla.mozilla.org/show_bug.cgi?id=495441
	if (pi.IsOut() && !ns_v.val.p) return NS_OK;

	MOZ_ASSERT(pi.IsDipper() || ns_v.val.p, "No space for result!");
	if (!pi.IsDipper() && !ns_v.val.p) return NS_ERROR_INVALID_POINTER;

	bool rc = true;
	switch (XPT_TDP_TAG(type)) {
	  case nsXPTType::T_I8:
		if ((val_use=PyNumber_Int(val))==NULL) BREAK_FALSE;
		FILL_SIMPLE_POINTER( PRInt8, PyInt_AsLong(val_use) );
		break;
	  case nsXPTType::T_I16:
		if ((val_use=PyNumber_Int(val))==NULL) BREAK_FALSE;
		FILL_SIMPLE_POINTER( PRInt16, PyInt_AsLong(val_use) );
		break;
	  case nsXPTType::T_I32:
		if ((val_use=PyNumber_Int(val))==NULL) BREAK_FALSE;
		FILL_SIMPLE_POINTER( PRInt32, PyInt_AsLong(val_use) );
		break;
	  case nsXPTType::T_I64:
		if ((val_use=PyNumber_Long(val))==NULL) BREAK_FALSE;
		FILL_SIMPLE_POINTER( PRInt64, PyLong_AsLongLong(val_use) );
		break;
	  case nsXPTType::T_U8:
		if ((val_use=PyNumber_Int(val))==NULL) BREAK_FALSE;
		FILL_SIMPLE_POINTER( PRUint8, PyInt_AsLong(val_use) );
		break;
	  case nsXPTType::T_U16:
		if ((val_use=PyNumber_Int(val))==NULL) BREAK_FALSE;
		FILL_SIMPLE_POINTER( PRUint16, PyInt_AsLong(val_use) );
		break;
	  case nsXPTType::T_U32:
		if ((val_use=PyNumber_Int(val))==NULL) BREAK_FALSE;
		if (sizeof(long) <= sizeof(PRUint32) && PyLong_Check(val_use)) {
			// Can't fit in a long
			*((PRUint32 *)ns_v.val.p) = (PRUint32)(PyLong_AsUnsignedLong(val_use));
		} else {
			*((PRUint32 *)ns_v.val.p) = (PRUint32)(PyInt_AsLong(val_use));
		}
		if (PyErr_Occurred()) {
			BREAK_FALSE
		}
		break;
	  case nsXPTType::T_U64:
		if ((val_use=PyNumber_Long(val))==NULL) BREAK_FALSE;
		FILL_SIMPLE_POINTER( PRUint64, PyLong_AsUnsignedLongLong(val_use) );
		break;
	  case nsXPTType::T_FLOAT:
		if ((val_use=PyNumber_Float(val))==NULL) BREAK_FALSE
		FILL_SIMPLE_POINTER( float, PyFloat_AsDouble(val_use) );
		break;
	  case nsXPTType::T_DOUBLE:
		if ((val_use=PyNumber_Float(val))==NULL) BREAK_FALSE
		FILL_SIMPLE_POINTER( double, PyFloat_AsDouble(val_use) );
		break;
	  case nsXPTType::T_BOOL:
		if ((val_use=PyNumber_Int(val))==NULL) BREAK_FALSE
		FILL_SIMPLE_POINTER( bool, PyInt_AsLong(val_use) );
		break;
	  case nsXPTType::T_CHAR:
		if (!PyString_Check(val) && !PyUnicode_Check(val)) {
			PyErr_SetString(PyExc_TypeError, "This parameter must be a string or Unicode object");
			BREAK_FALSE;
		}
		if ((val_use = PyObject_Str(val))==NULL)
			BREAK_FALSE;
		// Sanity check should PyObject_Str() ever loosen its semantics wrt Unicode!
		NS_ABORT_IF_FALSE(PyString_Check(val_use), "PyObject_Str didn't return a string object!");
		FILL_SIMPLE_POINTER( char, *PyString_AS_STRING(val_use) );
		break;

	  case nsXPTType::T_WCHAR:
		if (!PyString_Check(val) && !PyUnicode_Check(val)) {
			PyErr_SetString(PyExc_TypeError, "This parameter must be a string or Unicode object");
			BREAK_FALSE;
		}
		if ((val_use = PyUnicode_FromObject(val))==NULL)
			BREAK_FALSE;
		NS_ABORT_IF_FALSE(PyUnicode_Check(val_use), "PyUnicode_FromObject didnt return a Unicode object!");
		// Lossy!
		FILL_SIMPLE_POINTER( char16_t, *PyUnicode_AS_UNICODE(val_use) );
		break;

//	  case nsXPTType::T_VOID:
	  case nsXPTType::T_IID: {
		nsIID iid;
		if (!Py_nsIID::IIDFromPyObject(val, &iid))
			BREAK_FALSE;
		nsIID **pp = (nsIID **)ns_v.val.p;
		// If there is an existing [in] IID, free it.
		if (*pp && pi.IsIn())
			nsMemory::Free(*pp);
		*pp = (nsIID *)nsMemory::Alloc(sizeof(nsIID));
		if (*pp==NULL) {
			PyErr_NoMemory();
			BREAK_FALSE;
		}
		memcpy(*pp, &iid, sizeof(iid));
		break;
		}

	  case nsXPTType::T_ASTRING:
	  case nsXPTType::T_DOMSTRING: {
		nsAString *ws = (nsAString *)ns_v.val.p;
		NS_ABORT_IF_FALSE(ws->Length() == 0, "Why does this writable string already have chars??");
		if (!PyObject_AsNSString(val, *ws))
			BREAK_FALSE;
		break;
		}
	  case nsXPTType::T_CSTRING: {
		nsCString *ws = (nsCString *)ns_v.val.p;
		NS_ABORT_IF_FALSE(ws->Length() == 0, "Why does this writable string already have chars??");
		if (val == Py_None) {
			ws->SetIsVoid(true);
		} else {
			if (!PyString_Check(val) && !PyUnicode_Check(val)) {
				PyErr_SetString(PyExc_TypeError, "This parameter must be a string or Unicode object");
				BREAK_FALSE;
			}
			val_use = PyObject_Str(val);
			NS_ABORT_IF_FALSE(PyString_Check(val_use), "PyObject_Str didn't return a string object!");
			const char *sz = PyString_AS_STRING(val_use);
			ws->Assign(sz, PyString_Size(val_use));
		}
		break;
		}
	  case nsXPTType::T_UTF8STRING: {
		nsCString *ws = (nsCString *)ns_v.val.p;
		NS_ABORT_IF_FALSE(ws->Length() == 0, "Why does this writable string already have chars??");
		if (val == Py_None) {
			ws->SetIsVoid(true);
		} else {
			if (PyString_Check(val)) {
				val_use = val;
				Py_INCREF(val);
			} else if (PyUnicode_Check(val)) {
				val_use = PyUnicode_AsUTF8String(val);
			} else {
				PyErr_SetString(PyExc_TypeError, "UTF8 parameters must be string or Unicode objects");
				BREAK_FALSE;
			}
			NS_ABORT_IF_FALSE(PyString_Check(val_use), "must have a string object!");
			const char *sz = PyString_AS_STRING(val_use);
			ws->Assign(sz, PyString_Size(val_use));
		}
		break;
		}

	  case nsXPTType::T_CHAR_STR: {
		// If it is an existing string, free it.
		char **pp = (char **)ns_v.val.p;
		if (*pp && pi.IsIn())
			nsMemory::Free(*pp);
		*pp = nullptr;

		if (val == Py_None)
			break; // Remains NULL.
		if (!PyString_Check(val) && !PyUnicode_Check(val)) {
			PyErr_SetString(PyExc_TypeError, "This parameter must be a string or Unicode object");
			BREAK_FALSE;
		}
		if ((val_use = PyObject_Str(val))==NULL)
			BREAK_FALSE;
		// Sanity check should PyObject_Str() ever loosen its semantics wrt Unicode!
		NS_ABORT_IF_FALSE(PyString_Check(val_use), "PyObject_Str didn't return a string object!");

		const char *sz = PyString_AS_STRING(val_use);
		int nch = PyString_GET_SIZE(val_use);

		*pp = (char *)nsMemory::Alloc(nch+1);
		if (*pp==NULL) {
			PyErr_NoMemory();
			BREAK_FALSE;
		}
		strncpy(*pp, sz, nch+1);
		break;
		}
	  case nsXPTType::T_WCHAR_STR: {
		// If it is an existing string, free it.
		char16_t **pp = (char16_t **)ns_v.val.p;
		if (*pp && pi.IsIn())
			nsMemory::Free(*pp);
		*pp = nullptr;
		if (val == Py_None)
			break; // Remains NULL.
		if (!PyString_Check(val) && !PyUnicode_Check(val)) {
			PyErr_SetString(PyExc_TypeError, "This parameter must be a string or Unicode object");
			BREAK_FALSE;
		}
		val_use = PyUnicode_FromObject(val);
		NS_ABORT_IF_FALSE(PyUnicode_Check(val_use), "PyUnicode_FromObject didnt return a Unicode object!");
		if (PyUnicode_Aschar16_t(val_use, pp, NULL) < 0)
			BREAK_FALSE;
		break;
		}
	  case nsXPTType::T_INTERFACE:  {
		nsISupports *pnew = nullptr;
		// Find out what IID we are declared to use.
		nsIID iid;
		nsIInterfaceInfo *ii = GetInterfaceInfo();
		if (ii) {
			nsresult nr = ii->GetIIDForParamNoAlloc(m_method_index, &pi, &iid);
			if (!NS_SUCCEEDED(nr)) {
				char *iface_name;
				ii->GetName(&iface_name);
				const nsXPTMethodInfo *method_info;
				ii->GetMethodInfo(m_method_index, &method_info);
				if (method_info) {
					const char *method_name;
					method_name = method_info->GetName();
					PyErr_Format(PyExc_TypeError, "Unable to get IID for iface: %s, method: %s", iface_name, method_name);
				} else {
					PyErr_Format(PyExc_TypeError, "Unable to get IID for a method in iface: %s", iface_name);
				}
				BREAK_FALSE;
			}
		} else {
			iid = NS_GET_IID(nsISupports);
		}

		// Get it the "standard" way.
		// We do allow NULL here, even tho doing so will no-doubt crash some objects.
		// (but there will certainly be objects out there that will allow NULL :-(
		bool ok = Py_nsISupports::InterfaceFromPyObject(val, iid, &pnew, true);
		if (!ok)
			BREAK_FALSE;
		nsISupports **pp = (nsISupports **)ns_v.val.p;
		if (*pp && pi.IsIn()) {
			Py_BEGIN_ALLOW_THREADS; // MUST release thread-lock, incase a Python COM object that re-acquires.
			(*pp)->Release();
			Py_END_ALLOW_THREADS;
		}

		*pp = pnew; // ref-count added by InterfaceFromPyObject
		break;
		}
	  case nsXPTType::T_INTERFACE_IS: {
		const nsIID *piid;
		if (!GetIIDForINTERFACE_ID(pi.type.argnum, &piid))
			BREAK_FALSE;

		nsISupports *pnew = nullptr;
		// Get it the "standard" way.
		// We do allow NULL here, even tho doing so will no-doubt crash some objects.
		// (but there will certainly be objects out there that will allow NULL :-(
		if (!Py_nsISupports::InterfaceFromPyObject(val, *piid, &pnew, true))
			BREAK_FALSE;
		nsISupports **pp = (nsISupports **)ns_v.val.p;
		if (*pp && pi.IsIn()) {
			Py_BEGIN_ALLOW_THREADS; // MUST release thread-lock, incase a Python COM object that re-acquires.
			(*pp)->Release();
			Py_END_ALLOW_THREADS;
		}

		*pp = pnew; // ref-count added by InterfaceFromPyObject
		break;
		}

	  case nsXPTType::T_PSTRING_SIZE_IS: {
		const char *sz = nullptr;
		uint32_t nch = 0;
		if (val != Py_None) {
			if (!PyString_Check(val) && !PyUnicode_Check(val)) {
				PyErr_SetString(PyExc_TypeError, "This parameter must be a string or Unicode object");
				BREAK_FALSE;
			}
			if ((val_use = PyObject_Str(val))==NULL)
				BREAK_FALSE;
			// Sanity check should PyObject_Str() ever loosen its semantics wrt Unicode!
			NS_ABORT_IF_FALSE(PyString_Check(val_use), "PyObject_Str didn't return a string object!");

			sz = PyString_AS_STRING(val_use);
			nch = PyString_GET_SIZE(val_use);
		}
		bool bBackFill = false;
		bool bCanSetSizeIs = CanSetSizeIs(index);
		// If we can not change the size, check our sequence is correct.
		if (!bCanSetSizeIs) {
			uint32_t existing_size = GetSizeIs(index);
			if (nch != existing_size) {
				PyErr_Format(PyExc_ValueError, "This function is expecting a string of exactly length %d - %d characters were passed", existing_size, nch);
				BREAK_FALSE;
			}
			// It we have an "inout" param, but an "in" count, then
			// it is probably a buffer the caller expects us to 
			// fill in-place!
			bBackFill = pi.IsIn();
		}
		if (bBackFill) {
			memcpy(*(char **)ns_v.val.p, sz, nch);
		} else {
			// If we have an existing string, free it!
			char **pp = (char **)ns_v.val.p;
			if (*pp && pi.IsIn())
				nsMemory::Free(*pp);
			*pp = nullptr;
			if (sz==nullptr) // None specified.
				break; // Remains NULL.
			*pp = (char *)nsMemory::Alloc(nch);
			if (*pp==NULL) {
				PyErr_NoMemory();
				BREAK_FALSE;
			}
			memcpy(*pp, sz, nch);
			if (bCanSetSizeIs)
				rc = SetSizeIs(index, nch);
			else {
				MOZ_ASSERT(GetSizeIs(index) == nch,
				           "Can't set sizeis, but string isn't correct size");
			}
		}
		break;
		}

	  case nsXPTType::T_PWSTRING_SIZE_IS: {
		char16_t *sz = nullptr;
		uint32_t nch = 0;
		size_t nbytes = 0;

		if (val != Py_None) {
			if (!PyString_Check(val) && !PyUnicode_Check(val)) {
				PyErr_SetString(PyExc_TypeError, "This parameter must be a string or Unicode object");
				BREAK_FALSE;
			}
			val_use = PyUnicode_FromObject(val);
			NS_ABORT_IF_FALSE(PyUnicode_Check(val_use), "PyUnicode_FromObject didnt return a Unicode object!");
			if (PyUnicode_Aschar16_t(val_use, &sz, &nch) < 0)
				BREAK_FALSE;
			nbytes = sizeof(char16_t) * nch;
		}
		bool bBackFill = false;
		bool bCanSetSizeIs = CanSetSizeIs(index);
		// If we can not change the size, check our sequence is correct.
		if (!bCanSetSizeIs) {
			// It is a buffer the caller prolly wants us to fill in-place!
			uint32_t existing_size = GetSizeIs(index);
			if (nch != existing_size) {
				PyErr_Format(PyExc_ValueError, "This function is expecting a string of exactly length %d - %d characters were passed", existing_size, nch);
				BREAK_FALSE;
			}
			// It we have an "inout" param, but an "in" count, then
			// it is probably a buffer the caller expects us to 
			// fill in-place!
			bBackFill = pi.IsIn();
		}
		if (bBackFill) {
			memcpy(*(char16_t **)ns_v.val.p, sz, nbytes);
		} else {
			// If it is an existing string, free it.
			char16_t **pp = (char16_t **)ns_v.val.p;
			if (*pp && pi.IsIn())
				nsMemory::Free(*pp);
			*pp = sz;
			sz = nullptr;
			if (bCanSetSizeIs)
				rc = SetSizeIs(index, nch);
			else {
				MOZ_ASSERT(GetSizeIs(index) == nch,
				           "Can't set sizeis, but string isn't correct size");
			}
		}
		if (sz)
			nsMemory::Free(sz);
		break;
		}
	  case nsXPTType::T_ARRAY: {
		// If it is an existing array of the correct size, keep it.
		PRUint32 sequence_size = 0;
		XPTTypeDescriptorTags array_type;
		nsIID iid;
		nsresult ns = GetArrayType(index, &array_type, &iid);
		if (NS_FAILED(ns))
			return ns;
		PRUint32 element_size = GetArrayElementSize(array_type);
		if (val != Py_None) {
			if (!PySequence_Check(val)) {
				PyErr_Format(PyExc_TypeError,
							 "Object for xpcom array must be a sequence, not type '%s'",
							 val->ob_type->tp_name);
				BREAK_FALSE;
			}
			sequence_size = PySequence_Length(val);
		}
		uint32_t existing_size = GetLengthIs(index);
		bool bBackFill = false;
		bool bCanSetLengthIs = CanSetLengthIs(index);
		// If we can not change the size, check our sequence is correct.
		if (!bCanSetLengthIs) {
			// It is a buffer the caller prolly wants us to fill in-place!
			if (sequence_size != existing_size) {
				PyErr_Format(PyExc_ValueError,
							 "This function is expecting a sequence of exactly length %d - %d items were passed",
							 existing_size, sequence_size);
				BREAK_FALSE;
			}
			// It we have an "inout" param, but an "in" count, then
			// it is probably a buffer the caller expects us to 
			// fill in-place!
			bBackFill = pi.IsIn();
		}
		if (bBackFill)
			rc = FillSingleArray(*(void **)ns_v.val.p, val,
			                     sequence_size, element_size,
			                     array_type, iid);
		else {
			// If it is an existing array, free it.
			void **pp = (void **)ns_v.val.p;
			if (*pp && pi.IsIn()) {
				FreeSingleArray(*pp, existing_size, array_type);
				nsMemory::Free(*pp);
			}
			*pp = nullptr;
			if (val == Py_None)
				break; // Remains NULL.
			size_t nbytes = sequence_size * element_size;
			if (nbytes==0) nbytes = 1; // avoid assertion about 0 bytes
			*pp = (void *)nsMemory::Alloc(nbytes);
			memset(*pp, 0, nbytes);
			rc = FillSingleArray(*pp, val, sequence_size,
			                     element_size,
			                     array_type, iid);
			if (!rc) break;
			if (bCanSetLengthIs)
				rc = SetLengthIs(index, sequence_size);
			else {
				MOZ_ASSERT(GetLengthIs(index) == sequence_size,
				           "Can't set sizeis, but string isn't correct size");
			}
		}
		break;
		}
	  default:
		// try and limp along in this case.
		// leave rc TRUE
		PyXPCOM_LogWarning("Converting Python object for an [out] param - The object type (0x%x) is unknown - leaving param alone!\n", type.TagPart());
		break;
	}
	Py_XDECREF(val_use);
	if (!rc)
		return NS_ERROR_FAILURE;
	return NS_OK;
}

nsresult PyXPCOM_GatewayVariantHelper::ProcessPythonResult(PyObject *ret_ob)
{
	// NOTE - although we return an nresult, if we leave a Python
	// exception set, then our caller may take additional action
	// (ie, translating our nsresult to a more appropriate nsresult
	// for the Python exception.)
	NS_PRECONDITION(!PyErr_Occurred(),
	                "Expecting no Python exception to be pending when processing the return result");

	nsresult rc = NS_OK;
	// If we don't get a tuple back, then the result is only
	// an int nresult for the underlying function.
	// (ie, the policy is expected to return (NS_OK, user_retval),
	// but can also return (say), NS_ERROR_FAILURE
	if (PyInt_Check(ret_ob))
		return (nsresult) PyInt_AsLong(ret_ob);
	// Now it must be the tuple.
	if (!PyTuple_Check(ret_ob) ||
	    PyTuple_Size(ret_ob)!=2 ||
	    !PyInt_Check(PyTuple_GET_ITEM(ret_ob, 0))) {
		PyErr_SetString(PyExc_TypeError, "The Python result must be a single integer or a tuple of length==2 and first item an int.");
		return NS_ERROR_FAILURE;
	}
	PyObject *user_result = PyTuple_GET_ITEM(ret_ob, 1);
	// Count up how many results our function needs.
	int i;
	int num_results = 0;
	int last_result = -1; // optimization if we only have one - this is it!
	int index_retval = -1;
	for (i = 0; i < mPyTypeDesc.Length(); ++i) {
		nsXPTParamInfo *pi = (nsXPTParamInfo *)m_info->params+i;
		if (!mPyTypeDesc[i].IsAutoOut()) {
			if (pi->IsOut() || pi->IsDipper()) {
				num_results++;
				last_result = i;
			}
			if (pi->IsRetval())
				index_retval = i;
		}
	}

	if (num_results==0) {
		; // do nothing
	} else if (num_results==1) {
		// May or may not be the nominated retval - who cares!
		MOZ_ASSERT(last_result >=0 && last_result < mPyTypeDesc.Length(),
		           "Have one result, but don't know its index!");
		rc = BackFillVariant( user_result, last_result );
	} else {
		// Loop over each one, filling as we go.
		// We allow arbitary sequences here, but _not_ strings
		// or Unicode!
		// NOTE - We ALWAYS do the nominated retval first.
		// The Python pattern is always:
		// return retval [, byref1 [, byref2 ...] ]
		// But the retval is often the last param described in the info.
		if (!PySequence_Check(user_result) ||
		     PyString_Check(user_result) ||
		     PyUnicode_Check(user_result)) {
			PyErr_SetString(PyExc_TypeError, "This function has multiple results, but a sequence was not given to fill them");
			return NS_ERROR_FAILURE;
		}
		int num_user_results = PySequence_Length(user_result);
		// If they havent given enough, we don't really care.
		// although a warning is probably appropriate.
		if (num_user_results != num_results) {
			const char *method_name = m_info->name;
			PyXPCOM_LogWarning("The method '%s' has %d out params, but %d were supplied by the Python code\n",
				method_name,
				num_results,
				num_user_results);
		}
		int this_py_index = 0;
		if (index_retval != -1) {
			// We always return the nominated result first!
			PyObject *sub = PySequence_GetItem(user_result, 0);
			if (sub==NULL)
				return NS_ERROR_FAILURE;
			rc = BackFillVariant(sub, index_retval);
			Py_DECREF(sub);
			this_py_index = 1;
		}
		for (i=0;NS_SUCCEEDED(rc) && i<m_info->num_args;i++) {
			// If we've already done it, or don't need to do it!
			if (i == index_retval || mPyTypeDesc[i].IsAutoOut())
				continue;
			XPTParamDescriptor *pi = m_info->params+i;
			if (XPT_PD_IS_OUT(pi->flags)) {
				PyObject *sub = PySequence_GetItem(user_result, this_py_index);
				if (sub==NULL)
					return NS_ERROR_FAILURE;
				rc = BackFillVariant(sub, i);
				Py_DECREF(sub);
				this_py_index++;
			}
		}
	}
	return rc;
}
