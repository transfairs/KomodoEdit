About
-----
This version of PyXPCOM is designed to work with Firefox/XULRunner 35.0.

You will find compatible PyXPCOM code for older versions of Mozilla at:
    http://hg.mozilla.org/pyxpcom/tags

PyXPCOM allows for communication between Python and XPCOM, such that a Python
application can access XPCOM objects, and XPCOM can access any Python class
that implements an XPCOM interface. With PyXPCOM, a developer can talk to
XPCOM or embed Gecko from a Python application.

Requirements
------------
* requires Python 2.x (most tested with Python 2.7)
* requires Mozilla XULRunner SDK (version 35.0)
* autoconf 2.13

Build Steps
-----------

$ autoconf2.13
$ mkdir obj
$ cd obj
$ ../configure --with-libxul-sdk=/path/to/xulrunner-sdk
$ make

Installation
------------
When successfully built, there will be a "obj/dist/bin" directory that contains
the necessary files.

* libpyxpcom.so  - the core PyXPCOM library
* components/pyxpcom.manifest  - to tell Firefox/XULRunner to load PyXPCOM
* components/libpyloader.dll  - loader library for setting up PyXPCOM
* python  - the pure Python files, this directory must be on the PYTHONPATH

You'll need to ensure that the pyxpcom.manifest is registered/loaded by
XULRunner/Firefox by adding this file to the manifest list.

Testing
-------
You can run/test PyXPCOM from the command line using these methods:

$ cd obj/dist/bin
$ export MOZILLA_FIVE_HOME=/path-to-firefox/dist/bin # Adjust this to your Firefox/XULrunner path
$ export LD_LIBRARY_PATH=$MOZILLA_FIVE_HOME:`pwd`/   # Note the `pwd` for the obj/dist/bin dir
$ export PYTHONPATH=`pwd`/python
$ python
>>> from xpcom import components
>>> print components.classes["@mozilla.org/file/local;1"]
