Back to :ref:`card-index`

Back to :ref:`grid-card`

.. _unstructured-explicit-grid-card:

UNSTRUCTURED_EXPLICIT
=====================

Defines an unstructured grid through a list of cells and connectivity. Cells are defined by an id, coordinate and volume while connections are composed of two cell ids, an area and a face-center coordinate.

ASCII File Format
-----------------

The first line specifies the number of cells, followed by one line per cell defining the cell ID, center coordinate and volume (in units of meters). The number of connections are then specified, followed by one line per connection defining the two cell ids on either side of the connection, the face center coordinate and the face area. *Note that the center coordinates for Voronoi cells and faces are not necessarily the centroid.*

CELLS <integer>: Number of cells in grid

CONNECTIONS <integer>: Number of connections in grid

 ::

  CELLS #
  1 X_coordinate Y_coordinate Z_coordinate VOLUME
  ...
  # X_coordinate Y_coordinate Z_coordinate VOLUME
  CONNECTIONS @
  CELL_a CELL_b X_coordinate Y_coordinate Z_coordinate AREA
  ...
  CELL_y CELL_z X_coordinate Y_coordinate Z_coordinate AREA

Example
.......

Example explict unstructured grid (see `mixed.uge`_)

.. _mixed.uge: https://bitbucket.org/pflotran/pflotran/src/master/regression_tests/default/discretization/mixed.uge

 ::

  CELLS 15
  1 4.0625 4.0625 4.0625 5.20833
  2 4.375 4.375 3.125 2.60417
  3 3.3333 3.3333 3.75 7.8125
  4 3.3333 1.6667 3.75 7.8125
  5 3.3333 1.6667 1.25 7.8125
  6 1.25 3.75 3.75 15.625
  7 2.1875 4.0625 0.9375 1.30208
  8 2.1875 3.4375 1.5625 1.30208
  9 1.25 3.75 2.1875 2.60417
  10 1.25 4.6875 1.25 2.60417
  11 1.25 1.25 3.75 15.625
  12 1.25 1.25 1.25 15.625
  13 1.25 2.8125 1.25 2.60417
  14 0.3125 3.75 1.25 2.60417
  15 1.25 3.75 0.3125 2.60417
  CONNECTIONS 24
  1 2 4.16667 4.16667 3.3333 6.25
  1 3 3.75 3.75 3.75 8.8388
  3 4 3.75 2.5 3.75 6.25
  3 6 2.5 3.75 3.75 6.25
  4 5 3.3333 1.6667 2.5 3.125
  4 11 2.5 1.25 3.75 6.25
  5 12 2.5 1.25 1.25 6.25
  6 9 1.25 3.75 2.5 6.25
  6 11 1.25 2.5 3.75 6.25
  7 8 2.08333 3.75 1.25 2.2097
  7 10 2.08333 4.5833 1.25 2.2097
  7 15 2.08333 3.75 0.41667 2.2097
  8 9 2.08333 3.75 2.08333 2.2097
  8 13 2.08333 2.91667 1.25 2.2097
  9 10 1.25 4.48333 2.08333 2.2097
  9 13 1.25 2.91667 2.08333 2.2097
  9 14 0.41667 3.75 2.08333 2.2097
  10 14 0.41667 4.48333 1.25 2.2097
  10 15 1.25 4.48333 0.41667 2.2097
  11 12 1.25 1.25 2.5 6.25
  12 13 1.25 2.5 1.25 6.25
  13 14 0.41667 2.91667 1.25 2.2097
  13 15 1.25 2.91667 0.41667 2.2097
  14 15 0.41667 3.75 0.41667 2.2097



HDF5 File Format
-----------------

Two HDF5 datasets (*Cells* and *Connections*) are placed within a group named *Domain* within the HDF5 file. *Cells* group defines the cell center and the cell's volume through two subgroud named *Centers* (a 2D group with center's XYZ coordinates per cells) and *Volumes*. Then the *Connections* group defines the connection (i.e. face) properties by specifying the connection area with a *Areas* subgroup, the two cell ids on either side of the connection with a *Cell ids* 2D subgroup, and the connection centers with *Centers* 2D subgroup. 

As an example, consider the ASCII example above with 15 cells and 24 connections.

Cells/Centers
.............

*Domain/Cells/Centers* is a 2D float dataset sized 15x3 (number of cell x 3) [e.g. numpy.zeros((15,3),dtype='f8')] with data:

 ::
 
  # X, Y, Z coordinate
  4.0625 4.0625 4.0625
  4.375 4.375 3.125
  3.3333 3.3333 3.75
  3.3333 1.6667 3.75
  3.3333 1.6667 1.25
  1.25 3.75 3.75
  2.1875 4.0625 0.9375
  2.1875 3.4375 1.5625
  1.25 3.75 2.1875
  1.25 4.6875 1.25
  1.25 1.25 3.75
  1.25 1.25 1.25
  1.25 2.8125 1.25
  0.3125 3.75 1.25
  1.25 3.75 0.3125


Cells/Volumes
.............

*Domain/Cells/Volumes* is a 1D float dataset of sized 15 (number of cell) [e.g. numpy.zeros(15,dtype='f8')] with data:

 ::
  
  5.20833
  2.60417
  7.8125
  7.8125
  7.8125
  15.625
  1.30208
  1.30208
  2.60417
  2.60417
  15.625
  15.625
  2.60417
  2.60417
  2.60417


Connection/Areas
................

*Domain/Connection/Areas* is a 1D float dataset of sized 24 (number of connections/faces) [e.g. numpy.zeros(24,dtype='f8')] with data:

 ::
 
  6.25
  8.8388
  6.25
  6.25
  3.125
  6.25
  6.25
  6.25
  6.25
  2.2097
  2.2097
  2.2097
  2.2097
  2.2097
  2.2097
  2.2097
  2.2097
  2.2097
  2.2097
  6.25
  6.25
  2.2097
  2.2097
  2.2097


Connection/Cell Ids
...................

*Domain/Connection/Cell Ids* is a 2D integer dataset of sized 24 (number of connections/faces x 2) [e.g. numpy.zeros((24,2),dtype='i8')] with data:

 ::
 
  1 2
  1 3
  3 4
  3 6
  4 5
  4 11
  5 12
  6 9
  6 11
  7 8
  7 10
  7 15
  8 9
  8 13
  9 10
  9 13
  9 14
  10 14
  10 15
  11 12
  12 13
  13 14
  13 15
  14 15


Connection/Centers
..................

*Domain/Connection/Centers* is a 3D float dataset of sized 24 (number of connections/faces x 3) [e.g. numpy.zeros((24,3),dtype='f8')] with data:

 ::

  4.16667 4.16667 3.3333
  3.75 3.75 3.75
  3.75 2.5 3.75
  2.5 3.75 3.75
  3.3333 1.6667 2.5
  2.5 1.25 3.75
  2.5 1.25 1.25
  1.25 3.75 2.5
  1.25 2.5 3.75
  2.08333 3.75 1.25
  2.08333 4.5833 1.25
  2.08333 3.75 0.41667
  2.08333 3.75 2.08333
  2.08333 2.91667 1.25
  1.25 4.48333 2.08333
  1.25 2.91667 2.08333
  0.41667 3.75 2.08333
  0.41667 4.48333 1.25
  1.25 4.48333 0.41667
  1.25 1.25 2.5
  1.25 2.5 1.25
  0.41667 2.91667 1.25
  1.25 2.91667 0.41667
  0.41667 3.75 0.41667


Example script which convert and explicit unstructured grid in ASCII format to HDF5 format is available in the python source repository (see `convert_explicit_ascii_to_h5.py`_).

.. _convert_explicit_ascii_to_h5.py: https://bitbucket.org/pflotran/pflotran/src/master/src/python/unstructured_grid/convert_explicit_ascii_to_h5.py
