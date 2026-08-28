.. _running-pflotran:

Running PFLOTRAN
================

The following instructions show you how to run PFLOTRAN using a standard 
terminal.

STEP 0:

  Verify that PFLOTRAN has been installed correctly by running the regression
  test check. Detailed instructions on how to run the regression tests can be 
  found here: :ref:`regression-test-manager`.
  
  If you don't already have ``$PFLOTRAN_DIR`` set as an environment
  variable, do so now by replacing ``/home/jmfrede/software/pflotran`` with the
  path to your PFLOTRAN directory below,

  ::

    $ export PFLOTRAN_DIR=/home/jmfrede/software/pflotran
    $ cd $PFLOTRAN_DIR/regression_tests
    $ make check
    
  If PFLOTRAN has been installed correctly, you should see something like this 
  after running ``make check``:

  ::

    /usr/bin/python regression_tests.py -e ../src/pflotran/pflotran  --mpiexec /home/jmfrede/software/petsc/gnu-c-debug/bin/mpiexec \
		  --suite standard standard_parallel \
		  --config-files ascem/1d/1d-calcite/1d-calcite.cfg

    Test log file : pflotran-tests-2021-12-21_10-32-33.testlog

    Running pflotran regression tests :

      Legend

        . - success
        F - failed regression test (results are outside error tolerances)
        M - failed regression test (results are FAR outside error tolerances)
        G - general error
        U - user error
        V - simulator failure (e.g. failure to converge)
        X - simulator crash
        T - time out error
        C - configuration file [.cfg] error
        I - missing information (e.g. missing files)
        B - pre-processing error (e.g. error in simulation setup scripts
        A - post-processing error (e.g. error in solution comparison)
        S - test skipped
        W - warning
        ? - unknown

    ..

    --------------------------------------------------------------------------------
    Regression test summary:
        Total run time: 1.81472 [s]
        Total tests : 2
        Tests run : 2
        All tests passed.

  If you do not see this, go back and try installing PFLOTRAN again: 
  :ref:`installation`.

  
STEP 1:

  Create an input deck file (also called more simply as 'input file'). 
  An input file has the file extension ``.in`` and is most commonly named 
  ``pflotran.in``, although you can give it any name. It is an ASCII file 
  that contains all of the information necessary to set up your simulation. 
  Detailed instructions on how to create an input deck file are here: 
  :ref:`creating-an-input-deck-file`. Additionally, you can browse the input
  deck files located within the regression test directory 
  ``$PFLOTRAN_DIR/regression_tests``.
  
STEP 2:

  Place your input file within a directory where you want to run your 
  simulation. For example, in ``~/mytest``.
  
  ::

    $ cd ~/mytest
    $ ls
    
    pflotran.in        myinputfile.in
    
  In this example, two input files are inside ``~/mytest``. The first file is
  given the default name ``pflotran.in`` while the second input file is given
  a custom name ``myinputfile.in``. 
    
STEP 3:

  To run the simulation that is defined by the input file called 
  ``pflotran.in`` in serial, enter the following command,
  
  ::
  
    $ mpirun -n 1 $PFLOTRAN_DIR/src/pflotran/pflotran
    
  where ``$PFLOTRAN_DIR/src/pflotran/pflotran`` is the path to your PFLOTRAN 
  executable. For parallel runs, you simply replace ``1`` with the number of 
  processors desired.
  
  To run the simulation that is defined by the input file called 
  ``myinputfile.in`` (or any custom name), type the following command,
  
  ::
  
    $ mpirun -n 1 $PFLOTRAN_DIR/src/pflotran/pflotran -input_prefix myinputfile
    
  or alternatively,
  
  ::
  
    $ mpirun -n 1 $PFLOTRAN_DIR/src/pflotran/pflotran -pflotranin myinputfile.in
    
  Note that when the default input file name is used (``pflotran.in``), you
  do not need to specify the arguments ``-input_prefix`` or ``-pflotranin``.
  
STEP 4:

  If PFLOTRAN is running, you will see scrolling screen output that looks 
  something like what is displayed below: 
  
  ::
    
    ...
    ...

    == GENERAL FLOW ================================================================
      0 2r: 1.87E-04 2x: 0.00E+00 2u: 0.00E+00 ir: 7.72E-05 iu: 0.00E+00 rsn:   0
      1 2r: 9.69E-07 2x: 7.11E+06 2u: 3.83E-03 ir: 9.69E-07 iu: 1.57E-03 rsn: stol

    Step     52 Time=  9.77040E+00 Dt=  2.50000E-01 [day] snes_conv_reason:    4
      newton =   1 [      70] linear =     1 [        70] cuts =  0 [   0]
      --> SNES Linear/Non-Linear Iterations =            1  /            1
      --> SNES Residual:   9.689780E-07  4.844890E-08  9.686628E-07
      --> max chng: dpl=   0.0000E+00 dpg=   0.0000E+00 dpa=   0.0000E+00
		    dxa=   2.1661E-12  dt=   1.5734E-03 dsg=   0.0000E+00
    

    == GENERAL FLOW ================================================================
      0 2r: 1.84E-04 2x: 0.00E+00 2u: 0.00E+00 ir: 7.59E-05 iu: 0.00E+00 rsn:   0
      1 2r: 8.99E-07 2x: 7.11E+06 2u: 3.46E-03 ir: 8.99E-07 iu: 1.42E-03 rsn: stol

    Step     53 Time=  1.00000E+01 Dt=  2.29597E-01 [day] snes_conv_reason:    4
      newton =   1 [      71] linear =     1 [        71] cuts =  0 [   0]
      --> SNES Linear/Non-Linear Iterations =            1  /            1
      --> SNES Residual:   8.994285E-07  4.497143E-08  8.985523E-07
      --> max chng: dpl=   0.0000E+00 dpg=   0.0000E+00 dpa=   0.0000E+00
		    dxa=   1.9650E-12  dt=   1.4230E-03 dsg=   0.0000E+00
    ...
    ...
    
  If the simulation has finished, you should see summary information, including
  timing information, like so:
  
  ::
  
    FLOW TS BE steps =     53 newton =       71 linear =         71 cuts =      0
    FLOW TS BE Wasted Linear Iterations = 0
    FLOW TS BE SNES time = 0.1 seconds

    Wall Clock Time:  1.2695E-01 [sec]   2.1158E-03 [min]   3.5263E-05 [hr]

  
  If you made a mistake in your input file, then you will see an error message
  that informs you of the mistake. An error message about your input file looks
  something like this:
  
  ::
  
   =================
     PFLOTRAN v4.0
   =================

    "grid_structured_type" set to default value.
    pflotran card:: NUMERICAL_METHODS
    pflotran card:: REGRESSION
    pflotran card:: GRID
    pflotran card:: MATERIAL_PROPERTY
      Name :: soil1
 
    ------------------------------------------------------------------------------

     Helpful information for debugging the input deck:

         Filename : pflotran.in
      Line Number : 43
          Keyword : SUBSURFACE,MATERIAL_PROPERTY,POROSITY
 
    ------------------------------------------------------------------------------

    ERROR: While reading "porosity" under keyword: MATERIAL_PROPERTY.

    Stopping!

  In this example, the error message indicates that something is wrong with
  how the porosity was defined in the material property named ``soil1`` 
  at line 43 of input file ``pflotran.in``.

STEP 5:
  
  As the simulation is running, output files will be generated. By default, they
  will be located in the same location as your input file. As an example,
  
  ::
  
    $ cd ~/mytest
    $ ls
    
    pflotran.in       pflotran.out      pflotran-001.tec  pflotran-002.tec  pflotran-003.tec
    pflotran-004.tec  pflotran-005.tec  pflotran-006.tec  pflotran-007.tec

  A ``.out`` file will always be generated. Additional output files (like the
  ``.tec`` files in this example) will be generated according to what has been
  specified in the input file, under :ref:`output-card`. 
  By default, these output files will start with the same prefix as the input 
  file was given.
  
   
  
