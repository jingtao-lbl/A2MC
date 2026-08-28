Back to :ref:`card-index`

.. _proc-card:

PROC
====
Specifies processor decomposition.

Required Cards:
---------------
PROC <int int int>
 The number of processor to be employed in each direction x, y, z 
 (structured grids only).  The product of the integers must equal the number of 
 processor employed.

Examples
--------
2x2x2 decomposition
::

 PROC 2 2 2

Force decomposition in z direction only.  E.g. 1x1x8 decomposition.
::

 PROC 1 1 8
