.. _index:
.. highlight:: python
.. module:: ufo2fdk

ufo2fdk
=======

ufo2fdk is a package that handles the creation of OpenType-CFF fonts from UFO source files with the aid of the `Adobe Font Development Kit for OpenType (AFDKO aka FDK) <http://www.adobe.com/devnet/opentype/afdko/>`_. This package does not embedd the FDK, rather it :mod:`bridges <ufo2fdk.fdkBridge>` to it on the user's system with the expectation that the user has installed the FDK in the normal way.

The fonts created by the package should be considered only for beta usage and should be used with care.

Basic Usage
===========

Two main things are exposed for public use: *haveFDK* and *OTFCompiler*.

haveFDK
^^^^^^^

This function tests the availability of the FDK and returns a boolean indicating what was found. Example::

  from ufo2fdk import haveFDK

  if haveFDK():
    print "I found the FDK!"
  else:
    print "I'm sorry, I could not find the FDK."

OTFCompiler
^^^^^^^^^^^

.. autoclass:: OTFCompiler
   :members:

Example::

  from ufo2FDK import OTFCompiler

  compiler = OTFCompiler()
  reports = compiler.compile(font, "/MyDirectory/MyFont.otf", checkOutlines=True, autohint=True)
  print reports["checkOutlines"]
  print reports["autohint"]
  print reports["makeotf"]

That's all there is to it.

Internals
^^^^^^^^^

If you want to know how the bridging works, what information is needed in the source UFO, how to modify the internal behavior to fit your needs, etc. read on:

.. toctree::
   :maxdepth: 1

   autodoc/fdkBridge
   autodoc/makeotfParts
   autodoc/outlineOTF
   autodoc/fontInfoData

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

