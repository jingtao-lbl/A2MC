Back to :ref:`card-index`

.. _region-card:

REGION
======

Defines a region (e.g. point, surface, volume) within the problem domain.

Required Cards:
---------------

REGION <string>
 Opens the REGION block, where <string> is the name of the region.

Within the REGION block, one of:

 INFINITE
  Defines an infinite region that will capture all cells in the domain (spans -1.e20 to 1.e20 meters in each of the principal coordinates).

 COORDINATE <float float float>
  Defines the x, y, z location of a single point in space  (see note_ below)
   
   ::

    COORDINATE x y z

 COORDINATES
  Defines two coordinates which define a box (see note_ below)
  
   ::

    COORDINATES
      xmin ymin zmin
      xmax ymax zmax
    /

 BLOCK <int int int int int int> 
  Defines the i,j,k bounds of a region (structured grid only)

   ::

    BLOCK istart iend jstart jend kstart kend

 CARTESIAN_BOUNDARY <string>
  Maps a boundary region to a Cartesian domain (structured grid only).  
  The 'FACE' is implicit based on the *string*.

   ::

    CARTESIAN_BOUNDARY [WEST, EAST, SOUTH, NORTH, BOTTOM, TOP]

 LIST

  Non-boundary regions for all grid formats:
   Specify a list of cell IDs, one per line.

   ::

    LIST
      1
      2
      3
    /

  STRUCTURED Grid only:
   Specify boundary faces through a list of cell and face IDs, 
   one combo per line. 
   Face IDs are numbered as: 1=west, 2=east, 3=south, 4=north, 5=bottom, 6=top.

   ::

    LIST
      1 6
      2 6
      3 6
    /

  UNSTRUCTURED Grids: **not supported**

 FILE <string>

  Non-boundary regions for all grid formats:
   Specify a list of cell IDs in one of the following formats:

    * ASCII: one cell ID per line
    * HDF5 (.h5): cell IDs are in a 1D integer dataset named *Regions/<region name>/Cell Ids*.

  STRUCTURED Grid:
   Specify boundary faces through a list of cell and face IDs in one of the following formats:

    * ASCII: one cell and face ID per line
    * HDF5 (.h5): cell and face IDs are in two 1D integer datasets named *Regions/<region name>/Cell Ids* and *Regions/<region name>/Face Ids*, respectively. 

   Face IDs are numbered as: 1=west, 2=east, 3=south, 4=north, 5=bottom, 6=top.

  UNSTRUCTURED Grid (Implicit):
   Specify boundary faces through a list of vertex IDs in one of the following formats:
    * ASCII (.ss): each line specifies a face element type (T=triangle and Q=quadrilateral) and associated vertex IDs
    * HDF5 (.h5): 2D array of integers where the vertex IDs for each face are in the short dimension and the long dimension equals the number of faces.

  UNSTRUCTURED_EXPLICIT Grid:
   Specify boundary faces through a list of face connections in the following format:
    * ASCII (.ex): one connection per line (cell ID, face center coordinate and face area).

  Note that the suffixes *.ss*, *.ex*, and *.h5* are reserved for the file formats defined above.
  **See ASCII examples below or ASCII and HDF5 examples in PFLOTRAN_DIR/regression_tests/default/discretization.**

 :ref:`polygonal-region-card`
  Opens a block for defining a region by intersecting two polygons in separate XY, XZ or YZ planes.

Optional Card:
--------------

FACE <string>
 Required when defining a surface (structured grid only).

   ::

    FACE [WEST, EAST, SOUTH, NORTH, BOTTOM, TOP]


Examples
--------
 ::

  REGION source_zone
    FILE source_zone.h5
  /

  REGION all
    COORDINATES
      0.d0 0.d0 95.d0 
      120.d0 120.d0 110.d0
    /
  /

  REGION West
    COORDINATES
      0.d0 0.d0 95.d0 
      0.d0 120.d0 110.d0
    /
    FACE WEST
  /

  REGION East
    COORDINATES
      120.d0 0.d0 95.d0 
      120.d0 120.d0 110.d0
    /
    FACE EAST
  /

  REGION South
    COORDINATES
      0.d0 0.d0 95.d0 
      120.d0 0.d0 110.d0
    /
    FACE SOUTH
  /

  REGION South_Cartesian
    CARTESIAN_BOUNDARY SOUTH
  /

  REGION 2-9
    COORDINATE 60.07 88.75 102.5d0
  /

  REGION well
    LIST
      349
      459
      559
    /
  /

  REGION top !(structured grid only)
    LIST
      1   6
      2   6
      3   6
      ...
      500 6
    /
  /

  REGION zone1
    BLOCK 45 90 32 40 1 100
  /

  REGION pond
    POLYGON
      TYPE BOUNDARY_FACES_IN_VOLUME
      XY
        1081.09 512.609 0.
        1008.38 536.404 0.
        957.98 554.706 0.
        ...
        860.4 401.267 0.
        950.316 432.744 0.
        1015.65 472.986 0.
      /
      XZ
        0. 0. 1.
        1126. 0. -22.
      /
    /
  END

All Grids (non-boundary)
++++++++++++++++++++++++
ASCII *.txt* format or LIST
 ::

  1
  2
  ...
  N

STRUCTURED Grid
+++++++++++++++
Boundary faces in ASCII *.txt* format or LIST

 ::

  1 1   ! WEST face
  2 4   ! SOUTH face
  ...
  N 6   ! TOP face

UNSTRUCTURED Grid
+++++++++++++++++
Boundary faces in ASCII *.ss* format 
 ::

  4
  Q 4 1 10 13
  Q 7 4 13 16
  Q 13 10 19 22
  Q 16 13 22 25

EXPLICIT_UNSTRUCTURED Grid
++++++++++++++++++++++++++
Boundary faces in ASCII *.ex* format 
 ::

  CONNECTIONS 4
  1 0. 0.5 0.5 1.
  3 0. 1.5 0.5 1.
  5 0. 0.5 1.5 1.
  7 0. 1.5 1.5 1.

.. _note:

Note for COORDINATE/COORDINATES
-------------------------------
If a region (point, line, or plane) lies between cells within a structured grid (i.e. at a face or corner between cells), it will be assigned to the upwind cell (lower I,J,K index).  For instance, point X in

 ::

       |
    3  |  4
       |
  -----X-----
       |
    1  |  2
       |

is assigned to cell 1, in

 ::

       |
    3  X  4
       |
  -----|-----
       |
    1  |  2
       |

is assigned to cell 3, and in

 ::

       |
    3  |  4
       |
  --X--|-----
       |
    1  |  2
       |

is assigned to cell 1.

A line or a plane is similarly assigned to the adjacent upwind cells.  In the direction parallel to the line or plane, all cells INTERSECTED will be included (i.e. the region overlaps or crosses the boundary into the cell).  For instance, line X in

 ::

       |
    3  |  4
       X
  -----X-----
       X
    1  |  2
       |

will assign cells 1 and 3.

For 3D regions, the cells INTERSECTED by the volume will be included.  If the boundaries of the region coincide with cell boundaries, only the encompassed cells are included.  If there is ANY overlap of a 3D region with a cell (even femtometers into a cell), the cell is included. For instance, rectangle X in

 ::

       |
    3  |  4
     XXXX
  ---X-|X----
     XXXX
    1  |  2
       |

will assign cells 1, 2, 3 and 4, whereas

 ::

       |
    3  XXX4
       X X
  -----XXX---
       |
    1  |  2
       |

only assigns cell 4.

