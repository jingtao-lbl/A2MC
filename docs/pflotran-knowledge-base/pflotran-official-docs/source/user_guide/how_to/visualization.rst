Visualization
=============

Visualization of the results produced by PFLOTRAN can be achieved using
several different utilities including commercial and open source
software. Plotting 2D or 3D output files can be done using the
commercial package **Tecplot**, or the opensource packages
`ParaView <http://www.paraview.org/>`__ and
`VisIt <https://wci.llnl.gov/codes/visit/>`__.
Both **Paraview** and **VisIt** are capable of remote visualization 
on parallel architectures.

Several potentially useful hints on using these packages are provided
below.

Tecplot
-------

-  In order to change the default file format in **TecPlot** so that it
   recognizes ``.tec`` files, place the following in the ``tecplot.cfg``
   file:

``$!FileConfig FNameFilter {InputDataFile = "*.tec"}``

VisIt
-----

-  Inactive cells can be omitted by going to Controls -> Subset and
   unchecking Material\_ID[0].

-  In 3D to scale the size of one of the coordinate axes go to Controls
   -> View and check box Scale 3D Axes and set desired scaling factor in
   box to right.

-  To make 2D plots use Operators -> Slicing -> Slice.

-  For 3D plots Operators -> Slicing -> ThreeSlice is useful.

-  Instructions to set up geomechanical and flow data simultaneously in
   **VisIt**:

   1.  Open VisIt.

   2.  Select the :math:`1\times 2` layout button on Window 1 to open a
       new window (Window 2).

   3.  Now make Window 1 active by checking the first button on Window
       1.

   4.  Click on Open and select \*-geomech-\*.xmf database.

   5.  Click on Add –> Pseudocolor –> rel\_disp\_z and click Draw (Set
       Auto apply to avoid clicking Draw repeatedly).

   6.  Select the domain and rotate it to a preferred angle.

   7.  Select Window 2 and make it active.

   8.  Click Open and select pflotran.h5 or pflotran-\*.h5 (This file
       contains all the subsurface flow data).

   9.  Click on e.g. Add –> Pseudocolor –> Gas Saturation (or other
       desired variable).

   10. Click on Lock view and Lock time on both windows (This will sync
       views and times on both windows).

   11. After a window pops up, select Yes.

   12. With Window 2 active select: Operators –> Slicing –> ThreeSlice.

   13. Double click on three slice and change x and y to appropriate
       values.

   14. Select Window 1.

   15. Select Controls –> Expressions.

   16. Click New and add a name (e.g., disp\_vector). Select Vector Mesh
       Variable.

   17. Under Definition, add <rel\_disp\_x \_lb\_m\_rb\_>,<rel\_disp\_y
       \_lb\_m\_rb\_>,<rel\_disp\_z \_lb\_m\_rb\_>, Apply and Dismiss.

   18. Click Add –> Vector –> disp\_vector.

   19. Double click Vector under pflotran-geomech-\*.xmf
       database:disp\_vector.

   20. Select Form and set Scale to e.g. 0.5. Then select Rendering and
       change magnitude color from Default to difference (select a color
       scheme of your choice).

   21. Apply and Dismiss.

   22. Double click Pseudocolor –> rel\_disp\_z. Select e.g.
       hot\_desaturated for color table. Set opacity to 50%. Apply and
       Dismiss.

   23. Next, for mesh movement click: Operators –> Transforms –>
       Displace. After a window pops up, dismiss it.

   24. Double click Displace, change Displacement multiplier to e.g.,
       :math:`10000`. Click on Displacement Variable –> Vectors –>
       disp\_vectors. Dismiss the window saying no data etc. Apply and
       Dismiss.

   25. Finally, click the play button to watch movie. Rotate the domain
       to a convenient angle before doing so.

Gnuplot, MatPlotLib
-------------------

-  For 1D problems or for plotting PFLOTRAN observation, integral flux
   and mass balance output, the opensource software packages
   `gnuplot <http://www.gnuplot.info/>`__ and
   `matplotlib <http://matplotlib.org/>`__ are recommended.

-  With **gnuplot** and **matplotlib** it is possible to plot data from
   several files in the same plot. To do this with **gnuplot** it is
   necessary that the files have the same number of rows, e.g. time
   history points. The files can be merged during input by using the
   ``paste`` command as a pipe: e.g.

   ::

       plot '< paste file1.dat file2.dat' using 1:($n1*$n2)

   plots the product of variable in file 1 in column ``n1`` times the
   variable in file 2 in column ``n2`` of the merged file.

-  When using **gnuplot** it is possible to number the output file
   columns with ``PRINT_COLUMN_IDS`` added to the ``OUTPUT`` keyword.
   This is only useful, however, with ``FORMAT TECPLOT POINT`` output
   option.

- **Gnuplot** also provides for real-time plots by simply adding the following
  lines after the usual plot directives

  ::

        ...
        plot ...
        pause n
        reread

  where n denotes the pause time between plot points in seconds.
