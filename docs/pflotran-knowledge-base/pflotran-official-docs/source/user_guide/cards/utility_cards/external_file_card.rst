Back to :ref:`card-index`

.. _external-file-card:

EXTERNAL_FILE
=============
This card allows the user to break up an input file into separate files with 
unlimited flexibility on how one desires to break up the ASCII input.  External 
files can be nested up to 9 files deep (8 files beyond the main input file).  
One can cut-and-paste any portion of the original input file into the external 
file(s), even breaking up blocks of input (see example below).

Required Cards:
---------------
EXTERNAL_FILE <string>
 Specifies the name of the external file. 

Examples
--------

See also ``PFLOTRAN_DIR/regression_tests/default/input_format/external_files.in`` 
for an example of nesting EXTERNAL_FILE cards.

::

  EXTERNAL_FILE flow_conditions.txt
  
where the contents of flow_conditions.txt reads:

::
  
  FLOW_CONDITION initial
    TYPE
      TEMPERATURE DIRICHLET
      GAS_SATURATION DIRICHLET
      GAS_PRESSURE DIRICHLET
    /
    TEMPERATURE 25.d0 C
    GAS_SATURATION 1.0
    GAS_PRESSURE 1.5d5 Pa
  END

  FLOW_CONDITION left_end
    TYPE
      TEMPERATURE DIRICHLET
      GAS_SATURATION DIRICHLET
      GAS_PRESSURE DIRICHLET
    /
    TEMPERATURE 25.d0 C
    GAS_SATURATION 1.0
    GAS_PRESSURE 2.0d5 Pa
  END

  FLOW_CONDITION right_end
    TYPE
      TEMPERATURE DIRICHLET
      GAS_SATURATION DIRICHLET
      GAS_PRESSURE DIRICHLET
    /
    TEMPERATURE 25.d0 C
    GAS_SATURATION 1.0
    GAS_PRESSURE 1.0d5 Pa
  END
  
The section of the input file that would have specified all those 
FLOW_CONDITIONs can now be replaced by ``EXTERNAL_FILE flow_conditions.txt``.

Another example shows a proof of concept. The contents of an input file before 
removing part of coordinate block is show below:

::

  REGION top_boundary
    FACE TOP
    COORDINATE
      0.d0 0.d0 30.d0
      20.d0 15.d0 30.d0
    /
  END

Contents of input file after removing part of coordinate block:  
*Note that the first two lines of the COORDINATE block above have been placed* 
*in a separate text file.  This make no logical sense; just a proof of concept.*

::

  REGION top_boundary
    FACE TOP
    EXTERNAL_FILE part_of_coordinate_block.txt
      20.d0 15.d0 30.d0
    /
  END

Contents of ``part_of_coordinate_block.txt``

::

  COORDINATE
    0.d0 0.d0 30.d0
