#!/usr/bin/env python2

# This is a script to figure out what interfaces are leaking
# Usage:
#   1. Build PyXPCOM with PYXPCOM_DEBUG_INTERFACE_COUNT or PYXPCOM_DEBUG_GATEWAY_COUNT
#           (see PyXPCOM_std.h)
#   2. Run something (most likely, one of the tests)
#   3. $0 < /tmp/pyxpcom.debug-count.log

import sys
from collections import defaultdict
from pprint import pprint

def makedict(count=0, default=None):
    def missing_end():
        if default is None:
            raise KeyError
        else:
            return default()
    if count > 0:
        return defaultdict(makedict(count - 1, default))
    else:
        return defaultdict(missing_end)

gateways = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
interfaces = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))

for line in sys.stdin:
    fields = line.rstrip().split()

    delta = {"++": 1, "--": -1}.get(fields[1])
    if delta is None:
        raise KeyError("action %s is invalid")

    bucket = None
    if line.startswith("G"):
        # gateway
        bucket = gateways
        _, action, iid, supports, pyobj, total = fields
    elif line.startswith("I"):
        # interface
        bucket = interfaces
        _, action, iid, supports, pyobj, total = fields
    else:
        continue

    if "/" in iid:
        iid, iid_name = iid.split("/", 1)
    else:
        iid_name = None

    if "/" in pyobj:
        pyobj, pyobj_name = pyobj.split("/", 1)
    else:
        pyobj_name = None

    t, supports = supports.split("=", 1)
    #assert t == "nsISupports", "Unexpected type %s" % (t,)
    #t, pyobj = pyobj.split("=", 1)
    #assert t == "PyObject", "Unexpected type %s" % (t,)
    iface = bucket[iid]
    if iid_name is not None:
        iface["name"] = iid_name
    obj = iface[pyobj]
    if pyobj_name is not None:
        obj["name"] = pyobj_name
    count = obj.get("count", 0) + delta
    if count == 0:
        del iface[pyobj]
    else:
        obj["count"] = count
        obj[t].add(supports)

for bucket in interfaces, gateways:
    for iid, iface in bucket.items():
        if "name" in iface:
            del bucket[iid]
            iid = iface["name"]
            bucket[iid] = iface
            del iface["name"]
        if not bucket[iid].keys():
            del bucket[iid] # no leaks
        for ptr, pyobj in iface.items():
            if isinstance(pyobj, dict) and "name" in pyobj:
                del iface[ptr]
                ptr = "%s=%s" % (pyobj["name"], ptr.split("=", 1)[-1])
                iface[ptr] = pyobj
                del pyobj["name"]

def cast(obj):
    if isinstance(obj, defaultdict):
        return dict((k, cast(v)) for k, v in obj.items())
    if isinstance(obj, set):
        return list(obj)
    return obj

if gateways:
    print "gateways:"
    pprint(cast(gateways))
else:
    print "No gateways leaked"

if interfaces:
    print "interfaces:"
    pprint(cast(interfaces))
else:
    print "No interfaces leaked"
