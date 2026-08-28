Back to :ref:`card-index`

Back to :ref:`region-card`

.. _polygonal-region-card:

POLYGON
=======

Define a region by intersecting two polygons defined in separate XY, 
XZ or YZ planes.

Required Cards:
---------------

POLYGON
  Opens the POLYGON blocks within a REGION block

Within the POLYGON block, two of the following:

 XY
  Specifies a list of coordinates defining a polygon in the XY plane.
  Two points define a rectangle. N > 2 points define a polygon and 
  must be listed in clockwise or counter-clockwise order.
  
   ::

    XY
      x0 y0 z0
      x1 y1 z1
      x2 y2 z2
      ...
      xN yN zN
    /

 XZ
  Same as XY, but in the XZ plane.

 YZ
  Same as XY, but in the YZ plane.

Optional Cards:
---------------

TYPE <string>
 Defines whether the region is mapped to all BOUNDARY_FACES_IN_VOLUME or 
 all CELL_CENTERS_IN_VOLUME (BOUNDARY_FACES_IN_VOLUME is only supported 
 for implicit unstructgured grids). Default = CELL_CENTERS_IN_VOLUME

Examples
--------
 ::

  REGION polyvol_xy
    POLYGON
      XY
        1. 1. 0.
        1. 2. 0.
        2. 2. 0.
        2. 4. 0.
        3. 4. 0.
        3. 2. 0.
        4. 2. 0.
        4. 1. 0.
      /
      XZ
        0. 0. 3.
        5. 5. 4.
      /
    /
  END


  REGION pond
    POLYGON
      TYPE BOUNDARY_FACES_IN_VOLUME
      XY
        1081.09 512.609 0.
        1008.38 536.404 0.
        957.98 554.706 0.
        904.05 562.406 0.
        817.357 580.904 0.
        734.512 585.373 0.
        683.75 579.356 0.
        605.18 536.218 0.
        585.15 490. 0.
        638.527 440.49 0.
        704.511 387.615 0.
        775.457 384.037 0.
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

