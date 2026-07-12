# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
Generate nsError.py via clang/gcc

Since landing of bug 780618, most error codes are now in nsError.h and we can
generate the Python mapping from there.  This does that.

This runs nsError.h through clang or GCC, and have that dump the defines (so
that we don't have to parse the full C syntax).  It then sorts the output into a
few groups, and outputs them in order:
    - simple numbers
    - module definitions (mostly for sorting)
    - expressions that don't involve calls
    - functions (i.e. things that take arguments)
    - expressions that involve calls
    - anything else (due to dependencies on previously defined things)
"""

from pprint import pprint
import re, subprocess, sys

if len(sys.argv) < 3:
    print "Usage: %s nsError.h nsError.py" % (sys.argv[0])
    sys.exit(1)

for compiler in "clang", "gcc":
    try:
        subprocess.check_call("which %s >/dev/null 2>/dev/null" % (compiler,),
                              shell=True)
    except subprocess.CalledProcessError:
        pass
    else:
        break # found a good compiler

undefs = ("nscore_h___", "nsError_h__", "__STDC_HOSTED__", "__STDC_VERSION__", "__STDC__")
cmd = [compiler, "-undef", "-dM", "-E", "-Dnscore_h___", sys.argv[1]]
output = subprocess.check_output(cmd)

functions = []
simples = {} # simple things, e.g. constant numbers
expressions = {} # involving operators
calls = {} # involving function calls
modules = {}

prologue = """
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# This file is generated from %s
#
# Please use pyxpcom/xpcom/tools/nsError_generate.py to re-generate this file.

""" % (sys.argv[1])

out = open(sys.argv[2], "w")
out.write(prologue)

for line in output.splitlines():
    prefix, name, value = line.split(" ", 2)
    if prefix != "#define":
        continue # huh?
    if name in undefs:
        continue # ignore these
    if not "(" in name:
        if name.startswith("NS_ERROR_MODULE_"):
            modules[name] = value
        elif "(" in value:
            calls[name] = value
        elif set("+-*/ ").intersection(value) or not set("0123456789").intersection(value[0]):
            expressions[name] = value
        else:
            simples[name] = value
    else:
        functions.append((name, value.replace("!", " not ")))

env = {}

# print out simple values first
for literals in simples, modules, expressions:
    for name, value in sorted(literals.items()):
        stmt = "%s = %s\n" % (name, value)
        try:
            exec stmt in env
        except Exception, ex:
            pass # we might depend on things not there yet
        else:
            out.write(stmt)
            del literals[name]

# print out some unforunately hard-coded functions
hardcoded = ["def NS_LIKELY(x): return bool(x)\n",
             "def NS_UNLIKELY(x): return bool(x)\n"]
for stmt in hardcoded:
    exec stmt in env
    out.write(stmt)

# next, print out functions
cast_re = re.compile("\(([^( )]+)\)")
for name, value in functions:
    args = name.split("(", 2)[-1].strip(")").split(",")
    for match in reversed(list(cast_re.finditer(value))):
        if match.group(1) in args:
            continue
        value = value[:match.start()] + value[match.end():]
    stmt = "def %s: return %s\n" % (name, value)
    try:
        exec stmt in env
    except Exception, ex:
        sys.stderr.write("Failed: %s: %s\n" % (stmt, ex))
    else:
        out.write(stmt)

for literals in calls, modules, simples, expressions:
    for name, value in sorted(literals.items()):
        stmt = "%s = %s\n" % (name, value)
        try:
            exec stmt in env
        except Exception, ex:
            sys.stderr.write("Failed: %s: %s\n" % (stmt, ex))
        else:
            out.write(stmt)
            del literals[name]
