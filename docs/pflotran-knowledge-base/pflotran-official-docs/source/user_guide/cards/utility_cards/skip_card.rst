Back to :ref:`card-index`

.. _skip-card:

SKIP
====
Defines a block that skips lines of the input file.  Any number of these 
SKIP/NOSKIP cards may be nested.

Required Cards:
---------------
SKIP 
 Opens the block of skipped lines.

NOSKIP
 Closes the block of skipped lines.

Examples
--------
The entire REGION block will be ignored:
 ::

  SKIP
  REGION top
    FACE TOP
    COORDINATES
      0.d0 0.d0 30.d0
      20.d0 15.d0 30.d0
    /
  END
  NOSKIP

Example of nested SKIP/NOSKIP, where only the COORDINATES block within the REGION
block will be ignored:

 ::

  REGION top
    FACE TOP
    COORDINATE 10.d0 7.5d0 15.d0
    SKIP
    COORDINATES
      0.d0 0.d0 30.d0
      20.d0 15.d0 30.d0
    /
    NOSKIP
  END
