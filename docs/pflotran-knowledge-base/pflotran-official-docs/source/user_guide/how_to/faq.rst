.. _faq:

#. `How do I get help?`_
#. `How can I contribute to or update the online documentation?`_
#. `How do I resolve installation issues?`_
#. `How do I make any sense of the screen output, in particular Newton iteration convergence?`_
#. `How do I create datasets and are there examples?`_
#. `Why does PFLOTRAN crash when printing provenance information to HDF5 formatted output?`_
#. `Does PFLOTRAN run on a machine with GPUs?`_
#. `What is the difference between MAPPED, GLOBAL, CELL_INDEXED, GRIDDED and ASCII datasets?`_
#. `How can I troubleshoot multi-phase flow problems in GENERAL mode?`_

--------------------

.. _How do I get help?:

How do I get help?
==================

The PFLOTRAN developers and community can provide limited volunteer support for 
PFLOTRAN. Please send an email to the appropriate PFLOTRAN mailing lists.

Questions regarding PFLOTRAN installation (i.e. not answered by documentation 
below), bug reports: **pflotran-dev at googlegroups dot com**

Questions regarding running PFLOTRAN: **pflotran-users at googlegroups dot com**

Just saying "PFLOTRAN doesn't work" doesn't give us enough information to 
actually help you and often requires a lot of additional back and forth that 
delays the process. 

**Please provide the following information**:

#. Which Git revision of PFLOTRAN you are using:

    .. sourcecode:: bash

        git log -1

#. Whether you have modified PFLOTRAN:

    .. sourcecode:: bash

        git status


#. If you have modified PFLOTRAN? How? Is your version public for us to see?

#. Which version of PETSc you are using:

    .. sourcecode:: bash

        cd ${PETSC_DIR}
        git log -1 HEAD

#. Do the regression tests pass? If not, attach the test log.

    .. sourcecode:: bash

        cd ${PFLOTRAN_DIR}/src/pflotran
        make test

#. Attach the input file you are trying to run.

#. Attach the screen output or output files showing the error message and context:

    .. sourcecode:: bash

        ./pflotran -input_prefix my-problem &> my-problem.stdout.txt
        
--------------------

.. _How can I contribute to or update the online documentation?:

How can I contribute to or update the online documentation?
===========================================================

Fork Option (Beginner)
----------------------

#. Create a fork of the documentation repository on Bitbucket.

#. Clone the forked repository to your local machine.

#. Make additions and changes in existing or new .rst files. (*Note that Google is your best friend for learning reStructuredText.*)

#. Commit the changes.

#. Push the changes to the forked repository.

#. Submit a pull request to the main PFLOTRAN repository.

Branch Option (Advanced)
------------------------

*Note: This option requires push privileges for the main PFLOTRAN repository on Bitbucket. If you do not know what that means, use the Fork Option.*

#. Clone the documentation repository.


#. Create a development branch in which the changes will be made. (*Please follow the instuctions below.*)

#. Make additions and changes in existing or new .rst files. Google is your best friend for learning reStructuredText.

#. Test the changes using Sphinx on your local machine.

#. Commit the changes to the development branch.

#. Push the changes to the main PFLOTRAN repository.

#. Submit a pull request.

Common Bitbucket and Git Questions
----------------------------------

How to fork a repository?

  `Google "How do I fork a repository on Bitbucket? <https://lmgtfy.com/?q=How+do+I+fork+a+repository+on+Bitbucket%3F>`_

How to clone a repository?

  ``git clone git@bitbucket.org:pflotran/pflotran-documentation.git``

How to create a development branch?

  ``git checkout -b username/brief-description``

  e.g. ``git checkout -b glenn/added-faq-on-contributing-documentation``

How to test using Sphinx?

  a. Navigate to the repository.
  b. Compile the documentation.

    ``make html``

  c. Open *_build/html/index.html* and inspect the changes.

How to commit changes?

  ``git commit -i <filename> -m 'a short message describing the changes'``

  e.g. ``git commit -i faq.rst -m 'added an FAQ on adding/modifying PFLOTRAN documentation'``

How to push the modified branch back to the original repository?

  ``git push``

How to submit a pull request?

  `Google "How do I submit a pull request on Bitbucket? <https://lmgtfy.com/?q=How+do+I+submit+a+pull+request+on+Bitbucket%3F>`_

--------------------

.. _How do I resolve installation issues?:

How do I resolve installation issues?
=====================================

PETSc fails to compile when I type ``make all``
-----------------------------------------------

Oftentimes this can be fixed by deleting the PETSC_ARCH and reconfiguring or starting from a clean installation of PETSc. If you are upgrading your PETSc build, you may get an error message similar to below:

::

    Error: Unexpected data declaration statement in INTERFACE block at (1)
    /home/username/petsc/include/../src/ksp/f90-mod/ftn-auto-interfaces/petscpc.h90:1522:10:

    1522 |        end subroutine PCASMCreateSubdomains2D
         |          1
    Error: Expecting END INTERFACE statement at (1)
    gmake[3]: *** [gmakefile:225: gnu-c-debug/obj/src/ksp/f90-mod/petscpcmod.o] Error 1
    gmake[2]: *** [/home/username/petsc/lib/petsc/conf/rules.doc:28: libs] Error 2
    **************************ERROR*************************************
    Error during compile, check gnu-c-debug/lib/petsc/conf/make.log
    Send it and gnu-c-debug/lib/petsc/conf/configure.log to petsc-maint@mcs.anl.gov
    ********************************************************************
    gmake[1]: *** [makefile:45: all] Error 1
    make: *** [GNUmakefile:9: all] Error 2

This can be fixed by running the following commands:

.. code-block :: bash

    cd $PETSC_DIR
    make deletefortranstubs
    make allfortranstubs
    make all 


No such file /conf/variables
----------------------------

Problem: When I run "make pflotran" I get the message:

::

    $ make pflotran
    "makefile:150: /conf/variables: No such file or directory"
    "makefile:151: /conf/rules: No such file or directory"
    "make: *** No rule to make target `/conf/rules'. Stop"

Solution: You have not set your PETSC_DIR and PETSC_ARCH environment variables.

In tcsh:

.. sourcecode:: csh

    setenv PETSC_DIR /path/to/petsc
    setenv PETSC_ARCH whatever_arch_was_installed

In bash:

.. sourcecode:: bash

    export PETSC_DIR=/path/to/petsc
    export PETSC_ARCH=whatever_arch_was_installed

To avoid having to type these commands in every shell, they should be added to 
your .cshrc (tcsh) or .bashrc (bash) files.

PFLOTRAN doesn't compile when I type ``make pflotran``.
-------------------------------------------------------

Many times when PFLOTRAN doesn't compile correctly (e.g. ``make pflotran``
does not complete due to errors), it is due to incorrect PETSc configuration,
assuming the source code has not been modified. PFLOTRAN uses a snapshot of
the PETSc 'maint' (release) branch, obtained by specifically checking out a
changeset-id after cloning PETSc. The  changeset-id that PFLOTRAN uses
changes occasionally. If PFLOTRAN does not compile, try reconfiguring PETSc,
making sure you check out the correct changeset-id. Details are provided on
the installation pages: 
:ref:`installation`. An example is shown below. **The changeset-id shown below**
**may not be the most current. Please use the changeset-id provided on the** 
**installation pages:** :ref:`installation`.

.. code-block:: bash

    git clone https://gitlab.com/petsc/petsc petsc
    cd petsc
    git checkout 987thisisnotthecorrectchangesetid1234567

-------------------- 

.. _How do I make any sense of the screen output, in particular Newton iteration convergence?:

How do I make any sense of the screen output, in particular Newton iteration convergence?
=========================================================================================

Standard Flow
-------------


::

 == GENERAL FLOW ================================================================
   1 2r: 4.13E-13 2x: 1.30E+08 2u: 4.47E-01 ir: 4.42E-14 iu: 2.44E-02 rsn:   0
   2 2r: 6.06E-13 2x: 1.30E+08 2u: 5.63E-01 ir: 5.65E-14 iu: 5.23E-02 rsn:   0
   3 2r: 2.21E-13 2x: 1.30E+08 2u: 3.67E-01 ir: 1.90E-14 iu: 3.05E-02 rsn:   0
   4 2r: 2.45E-13 2x: 1.30E+08 2u: 3.33E-01 ir: 2.20E-14 iu: 2.42E-02 rsn: itol_post_check

  Step   5498 Time=  9.89040E+03 Dt=  1.04142E+01 [y] snes_conv_reason:   12
   newton =   4 [   31891] linear =    75 [    645652] cuts =  0 [ 915]
   --> SNES Linear/Non-Linear Iterations =           75  /            4
   --> SNES Residual:   2.452466E-13  2.335682E-16  2.200252E-14
   --> max chng: dpl=   2.7064E-03 dpg=   1.1357E-01 dpa=   1.1357E-01
                 dxa=   1.3283E-11  dt=   0.0000E+00 dsg=   2.9327E-08

* 2r: 2-norm of residual
* 2x: 2-norm of current solution
* 2u: 2-norm of update
* ir: inf-norm of residual
* iu: inf-norm of update
* rsn: converged reason (corresponding integer in brackets)

 + 0: iterating (not converged)
 + atol[2]: 2r < ATOL
 + rtol[3]: 2r < RTOL * 2r_initial
 + stol[4]: 2u < STOL * 2x
 + itol_res[10]: ir < ITOL_RES
 + itol_upd[11]: iu < ITOL_UPDATE
 + itol_post_check[12]: mode-specific convergence criteria defined in XXXCheckUpdatePost()

* Time: current simulation time
* Dt: time step size
* snes_conv_reason: integer value for 'rsn'
* newton: number of Newton iterations for time step [simulation total in brackets]
* linear: number of linear iterations for time step [simulation total in brackets]
* cuts: number of time step cuts for time step [simulation total in brackets]
* SNES Linear/Non-Linear Iterations: self explanatory
* SNES Residual: 2r 2r/#cell ir 
* max chng: maximum change in a primary dependent variable

 + dpl: liquid pressure [Pa]
 + dpg: gas pressure [Pa]
 + dpa: air pressure [Pa]
 + dxa: air mole fraction in liquid phase [-]
 + dt: temperature [C]
 + dsg: gas saturation [-]
 

GENERAL mode compiled with debug_gen=2
--------------------------------------

 
The following information is printed for every Newton iteration when PFLOTRAN 
is run with the GENERAL flow mode and the code is compiled with 'debug_gen=2' 
on the command line.

::

  2 2r: 1.78E-13 2x: 1.80E+07 2u: 6.26E+01 ir: 1.20E-13 iu: 3.13E+01 rsn:   0
    -+  dpl:  2.9148E+00  dxa:  9.5553E-10  dt:  1.8149E-10
    -+  dpg:  0.0000E+00  dpa:  0.0000E+00  dt:  0.0000E+00
    -+  dpg:  4.2500E+00  dsg:  8.4871E-07  dt:  1.8331E-10
    -+ rupl:  5.6408E-07 ruxa:  5.3914E-02 rut:  6.7219E-12
    -+ rupg:  0.0000E+00 rupa:  0.0000E+00 rut:  0.0000E+00
    -+ rupg:  7.0889E-07 rusg:  9.1508E-06 rut:  6.7894E-12
    -+  srl:  4.8899E-06  srg:  6.5988E-10 sre:  2.0326E-07
    -+  srl:  0.0000E+00  srg:  0.0000E+00 sre:  0.0000E+00
    -+  srl:  4.9007E-06  srg:  1.6427E-07 sre:  1.7585E-07
    -+ ru1 icell:      6  st:  3  X:  5.995E+06  dX: -4.250E+00  R: -5.672E-14
    -+ ru2 icell:      7  st:  1  X:  1.772E-08  dX: -9.555E-10  R: -7.638E-18
    -+ ru3 icell:      1  st:  3  X:  2.700E+01  dX:  1.833E-10  R: -9.295E-16
    -+ sr1 icell:      6  st:  3  X:  5.995E+06  dX: -4.250E+00  R: -5.672E-14
    -+ sr2 icell:      6  st:  3  X:  9.275E-02  dX: -8.487E-07  R:  1.901E-15
    -+ sr3 icell:      7  st:  1  X:  2.700E+01  dX:  1.788E-10  R:  1.200E-13

Data is organized in rows of three corresonding to either the states of the 
system (1-single phase liquid, 2-single phase gas, 3-two phase) or the governing 
equation (1-liquid component [water] mass, 2-gas component [air] mass, 3-energy).

The first set of three (i.e. three rows) prints the maximum change of each of 
the three primary dependent variables (column) for each state (row: 1-liquid, 
2-gas, 3-two-phase). Only cells possessing a primary dependent variable for a 
given state considered in each calculation:

::

    -+  dpl:  2.9148E+00  dxa:  9.5553E-10  dt:  1.8149E-10
    -+  dpg:  0.0000E+00  dpa:  0.0000E+00  dt:  0.0000E+00
    -+  dpg:  4.2500E+00  dsg:  8.4871E-07  dt:  1.8331E-10

* d: - delta [X_(p+1) - X_p]

* dpl: liquid pressure
* dxa: air mole fraction in liquid phase
* dt: temperature
* dpg: gas pressure
* dpa: air pressure
* dsg: gas saturation

Rows 4-6 print the infinity norm of the relative update (dX/X) for each of the 
three primary dependent variables for each state:

::

    -+ rupl:  5.6408E-07 ruxa:  5.3914E-02 rut:  6.7219E-12
    -+ rupg:  0.0000E+00 rupa:  0.0000E+00 rut:  0.0000E+00
    -+ rupg:  7.0889E-07 rusg:  9.1508E-06 rut:  6.7894E-12

* ru - relative update of X [dX/X]

* rupl: liquid perssure
* ruxa: air mole fraction in liquid phase
* rut: temperature
* rupg: gas pressure
* rupa: air pressure
* rusg: gas saturation

Rows 7-9 print the infinity norm of the scaled residual (R / A) for each of the 
three governing equations for each state.  Here A is the fixed portion of the 
accumulation time (portion of time derivative at time t as opposed to t + dt):

::

    -+  srl:  4.8899E-06  srg:  6.5988E-10 sre:  2.0326E-07
    -+  srl:  0.0000E+00  srg:  0.0000E+00 sre:  0.0000E+00
    -+  srl:  4.9007E-06  srg:  1.6427E-07 sre:  1.7585E-07

* sr - scaled residual [R/A]   

* srl: liquid (water) equation
* srg: gas (air) equation
* sre: energy equation

Rows 10-12 print the cell id, state (st), value (X), update (dX), and residual 
(R) for primary dependent variable with the largest relative update (dX/X) for 
each governing equation:

::

    -+ ru1 icell:      6  st:  3  X:  5.995E+06  dX: -4.250E+00  R: -5.672E-14
    -+ ru2 icell:      7  st:  1  X:  1.772E-08  dX: -9.555E-10  R: -7.638E-18
    -+ ru3 icell:      1  st:  3  X:  2.700E+01  dX:  1.833E-10  R: -9.295E-16

* ru - relative update

* ru1: liquid equation
* ru2: gas equation
* ru3: energy equation

Rows 13-15 print the cell id, state (st), value (X), update (dX), and residual 
(R) for primary dependent variable with the largest scaled residual (R/A) for 
each governing equation:

::

    -+ sr1 icell:      6  st:  3  X:  5.995E+06  dX: -4.250E+00  R: -5.672E-14
    -+ sr2 icell:      6  st:  3  X:  9.275E-02  dX: -8.487E-07  R:  1.901E-15
    -+ sr3 icell:      7  st:  1  X:  2.700E+01  dX:  1.788E-10  R:  1.200E-13

* sr - scaled residual

* sr1: liquid equation
* sr2: gas equation
* sr3: energy equation

.. _How do I create datasets and are there examples?:

How do I create datasets and are there examples?
================================================

**It is highly recommended that you download and install HDFView, which greatly 
facilitates understanding/managing HDF5 files with PFLOTRAN.**

Permeability and/or Porosity
----------------------------

Permeability and porosity datasets are cell-indexed HDF5 datasets, but they 
differ slightly from all other datasets in that they are not placed in a group 
and they must be named "Permeability" and "Porosity".  This will change in the 
future, but for now, they must use those names.  See the :ref:`dataset-card` 
card.

Useful python scripts: 

PFLOTRAN_DIR/src/python/conceptual_model/DataLoader.py

Useful examples:

PFLOTRAN_DIR/regression_tests/default/543/543_hanford_srfcplx_param.in
PFLOTRAN_DIR/regression_tests/default/infiltrometer/16m.in
PFLOTRAN_DIR/regression_tests/shortcourse/regional_doublet/stochastic_regional_doublet_small.in

Material IDs
------------

Material IDs must be defined for all grid cells in a single HDF5 file under an 
HDF5 Group named "Materials".  The STRATA_ card provides an example of how to 
set up a Material ID dataset.

Useful python scripts:

PFLOTRAN_DIR/src/python/conceptual_model/material_and_region_loader.py

Useful examples:

PFLOTRAN_DIR/regression_tests/default/543/543_flow.in

Regions
-------

Regions are located in an HDF5 file under an HDF5 Group named "Regions".  Within 
the Regions group, one creates Groups whose names match the regions in the 
PFLOTRAN input file.  Each of these groups provides a list of "Cell Ids" and 
"Face Ids".  Face ids are not required for regions not associated with boundary 
conditions.

Useful python scripts:

PFLOTRAN_DIR/src/python/conceptual_model/material_and_region_loader.py

Useful examples:

PFLOTRAN_DIR/regression_tests/default/543/543_flow.in

Other Cell-Indexed Datasets
---------------------------

Other cell-indexed HDF5 datasets can have arbitrary names.  These datasets are 
used to define pressure, temperature, concentration, mineral volume fractions, 
etc. over all grid cells in the domain.

Useful python scripts:

PFLOTRAN_DIR/src/python/cell_indexed_dataset_loader.py

Useful examples:

PFLOTRAN_DIR/regression_tests/default/543/543_hanford_srfcplx_param.in
PFLOTRAN_DIR/regression_tests/default/543/543_flow.in (initializing pressure field from a file)

Gridded Datasets
----------------

Gridded HDF5 datasets are defined on a uniform Cartesian grid and interpolated 
to the PFLOTRAN structured or unstructured grid internally.  These grids are 
particularly useful for setting up nonlinear boundary or initial conditions.

Useful python scripts:

PFLOTRAN_DIR/src/python/gridded_dataset_loader.py

Useful examples:

PFLOTRAN_DIR/regression_tests/default/condition/datum_dataset.in
PFLOTRAN_DIR/regression_tests/default/condition/543_datum_dataset.in

ASCII Datasets
--------------

ASCII dataset are used to define scalar or vector quantities over time (e.g. a 
datum, gradient, or pressure associated with a FLOW_CONDITION that varies over 
time).

Useful python scripts:

Currently don't have a script.

Useful examples:

PFLOTRAN_DIR/regression_tests/default/condition/543_timeseries.in
PFLOTRAN_DIR/regression_tests/shortcourse/regional_doublet/regional_doublet_small.in (see "river" FLOW_CONDITION)

.. _DATASET: QuickGuide/DatasetNew
.. _STRATA: QuickGuide/Strata

.. _Why does PFLOTRAN crash when printing provenance information to HDF5 formatted output?:

Why does PFLOTRAN crash when printing provenance information to HDF5 formatted output?
======================================================================================

Ensure that there is a carriage return character on the last line of your input 
file.  This should resolve the issue.

.. _Does PFLOTRAN run on a machine with GPUs?:

Does PFLOTRAN run on a machine with GPUs?
=========================================

PFLOTRAN will run on a machine with GPUs, but it will not leverage any GPU (or 
any other accelerator) capability.  The code is not currently written to utilize 
the GPUs on such machines, but only the CPU.

Note: Before you make a significant investment in codes that claim to use GPUs, 
research the codes' scalability on GPUs (or perform your own scalability study) 
to ensure that your investment is worthwhile. Codes that solve implicit systems 
of equations (as does PFLOTRAN) have demonstrated only minimal speedup on GPUs 
(e.g. 4x). At this point in time, I (Glenn) consider a large investment in GPU 
capability to be ineffective since one can employ 4 times as many cores to get 
the same speedup.

.. _What is the difference between MAPPED, GLOBAL, CELL_INDEXED, GRIDDED and ASCII datasets?:

What is the difference between MAPPED, GLOBAL, CELL_INDEXED, GRIDDED and ASCII datasets?
========================================================================================

ASCII: Text-based datasets entered in the input file are stored internally 
within PFLOTRAN in ASCII datasets.

CELL_INDEXED:  A dataset that prescribes a value for each grid cell in a list 
of cells. The user must define a list of cells IDs aligned with the values. 
Theoretically, the user could provide a list of cells that is a subset of the 
global domain, but this has not been tested. The list of cells is usually 
aligned with the global grid, and thus, this dataset is usually aligned with 
the GLOBAL dataset.  

GLOBAL: A dataset that prescribes a value for each grid cell in the (global) 
domain.

GRIDDED: A 1D, 2D, or 3D uniformly-spaced grid of values from which values can 
be interpolated given a point in space.

MAPPED: A dataset that maps few distinct data values on multiple grid cells. 
e.g. A simulation for a 3D domain (NX x NY x NZ) in which a vertical profile 
(NZ) of transpiration sink is applied homogeneously for each horizontal layer. 
At a z-th level, all grid cells in x- and y-direction are prescribed z-th 
transpiration dataset.

.. _How can I troubleshoot multi-phase flow problems in GENERAL mode?:

How can I troubleshoot multi-phase flow problems in GENERAL mode?
========================================================================================

**Example**: Simulation is failing to converge

::

  -> Cut time step: snes= -3 icut= 16[372] t=  6.88420E+00 dt=  6.64673E-06
  Newton solver reason: SNES_DIVERGED_LINEAR_SOLVE
  Linear solver reason: KSP_DIVERGED_PCSETUP_FAILED
    0 2r: 3.15E-06 2x: 0.00E+00 2u: 0.00E+00 ir: 2.05E-06 iu: 0.00E+00 rsn:   0
    Stopping: Time step cut criteria exceeded.
       icut = 17, max_time_step_cuts= 16
  --> write tecplot output file: flow_cut_to_failure.tec
        0.02 Seconds to write to Tecplot file(s)

  FLOW TS BE steps =   1601 newton =     5774 linear =       5774 cuts =    356
  FLOW TS BE Wasted Linear Iterations = 2848
  FLOW TS BE SNES time = 12.9 seconds

   Wall Clock Time:  1.3692E+01 [sec]   2.2821E-01 [min]   3.8034E-03 [hr]


**Try**: Adding USE_INFINITY_NORM_CONVERGENCE to the NEWTON_SOLVER block.
**This will**: Impose infinity norm convergence criteria to declare simulation convergence instead of the default Euclidean norm convergence criteria. 

**Fixed Example**:

::

  == GENERAL MULTIPHASE FLOW =====================================================
  0 2r: 8.16E-07 2x: 0.00E+00 2u: 0.00E+00 ir: 4.37E-07 iu: 0.00E+00 rsn:   0
  1 2r: 1.75E-06 2x: 7.97E+06 2u: 5.65E+03 ir: 8.76E-07 iu: 1.05E+03 rsn:   0
  2 2r: 2.35E-09 2x: 7.97E+06 2u: 4.02E+03 ir: 1.13E-09 iu: 1.68E+03 rsn:   0
  3 2r: 3.24E-10 2x: 7.97E+06 2u: 2.52E+03 ir: 1.34E-10 iu: 1.68E+03 rsn:   0
  4 2r: 7.96E-10 2x: 7.97E+06 2u: 1.30E+01 ir: 4.53E-10 iu: 3.36E+00 rsn:   0
  5 2r: 1.35E-16 2x: 7.97E+06 2u: 3.92E-01 ir: 7.74E-17 iu: 2.70E-01 rsn: 999

  Step    650 Time=  5.00000E+01 Dt=  2.33233E-01 [y] snes_conv_reason:  999
  newton =   5 [    2637] linear =     5 [      2637] cuts =  0 [ 111]
  --> SNES Linear/Non-Linear Iterations =            5  /            5
  --> SNES Residual:   1.346474E-16  8.917046E-19  7.743109E-17
  --> max chng: dpl=   1.0783E+03 dpg=   1.0564E+03 dpa=   3.7402E+01
                dxa=   3.1919E-09  dt=   4.9887E-02 dsg=   2.1620E-02

  Dt limited by Unknown: Val=-9.990E+02, Gov=-9.990E+02, Scale=0.33

  --> write tecplot output file: gas_bubble-004.tec
       0.00 Seconds to write to Tecplot file(s)
  FLOW TS BE steps =    650 newton =     2637 linear =       2637 cuts =    111
  FLOW TS BE Wasted Linear Iterations = 888
  FLOW TS BE SNES time = 6.9 seconds

   Wall Clock Time:  7.3313E+00 [sec]   1.2219E-01 [min]   2.0365E-03 [hr]


**Example**: Simulation output indicates that the same grid cells are frequently changing state back and forth (e.g. from Liquid --> Two-Phase and then from Two-Phase --> Liquid) within Newton iterations

::

  == GENERAL MULTIPHASE FLOW =====================================================
   0 2r: 2.45E-05 2x: 0.00E+00 2u: 0.00E+00 ir: 2.44E-05 iu: 0.00E+00 rsn:   0
  (0): State Transition: Liquid -> 2 Phase at Cell       50
  (0): State Transition: Liquid -> 2 Phase at Cell       52
   1 2r: 1.53E-04 2x: 1.01E+07 2u: 2.22E+03 ir: 8.27E-05 iu: 3.80E+02 rsn:   0
  (0): State Transition: 2 Phase -> Liquid at Cell       50
  (0): State Transition: 2 Phase -> Liquid at Cell       52
   2 2r: 1.47E-04 2x: 1.01E+07 2u: 3.08E+03 ir: 7.72E-05 iu: 9.78E+02 rsn:   0
  (0): State Transition: Liquid -> 2 Phase at Cell       50
  (0): State Transition: Liquid -> 2 Phase at Cell       52
   3 2r: 1.53E-04 2x: 1.01E+07 2u: 3.02E+03 ir: 8.28E-05 iu: 9.92E+02 rsn:   0
  (0): State Transition: 2 Phase -> Liquid at Cell       50
  (0): State Transition: 2 Phase -> Liquid at Cell       52
   4 2r: 1.47E-04 2x: 1.01E+07 2u: 3.02E+03 ir: 7.72E-05 iu: 9.92E+02 rsn:   0
  (0): State Transition: Liquid -> 2 Phase at Cell       50
  (0): State Transition: Liquid -> 2 Phase at Cell       52
   5 2r: 1.53E-04 2x: 1.01E+07 2u: 3.02E+03 ir: 8.28E-05 iu: 9.92E+02 rsn:   0
  (0): State Transition: 2 Phase -> Liquid at Cell       50
  (0): State Transition: 2 Phase -> Liquid at Cell       52

**Try**: Adding RESTRICT_STATE_CHANGE to the GENERAL mode OPTIONS block
**This will**: Only allow grid cells to change state once during a Newton iteration. If convergence is not achieved, time step is cut.

**Fixed Example**:

::

  == GENERAL MULTIPHASE FLOW =====================================================
  0 2r: 3.56E-05 2x: 0.00E+00 2u: 0.00E+00 ir: 3.55E-05 iu: 0.00E+00 rsn:   0
  1 2r: 7.62E-06 2x: 1.02E+07 2u: 7.08E+03 ir: 6.20E-06 iu: 1.21E+03 rsn:   0
  (0): State Transition: Liquid -> 2 Phase at Cell       50
  (0): State Transition: Liquid -> 2 Phase at Cell       52
  2 2r: 1.55E-04 2x: 1.01E+07 2u: 2.34E+04 ir: 8.37E-05 iu: 4.22E+03 rsn:   0
  3 2r: 1.24E-06 2x: 1.01E+07 2u: 5.40E+03 ir: 1.01E-06 iu: 2.23E+03 rsn:   0
  4 2r: 1.63E-04 2x: 1.01E+07 2u: 1.39E+03 ir: 8.89E-05 iu: 2.39E+02 rsn:   0
  5 2r: 1.02E-04 2x: 1.01E+07 2u: 9.52E+02 ir: 5.56E-05 iu: 4.34E+02 rsn:   0
  6 2r: 1.15E-04 2x: 1.01E+07 2u: 1.09E+03 ir: 6.20E-05 iu: 1.89E+02 rsn:   0
  7 2r: 1.21E-04 2x: 1.01E+07 2u: 5.93E+02 ir: 6.54E-05 iu: 1.54E+02 rsn:   0
  8 2r: 1.22E-04 2x: 1.01E+07 2u: 5.88E+01 ir: 6.59E-05 iu: 1.92E+01 rsn:   0
  9 2r: 1.22E-04 2x: 1.01E+07 2u: 8.76E-01 ir: 6.60E-05 iu: 5.17E-01 rsn:   0
  10 2r: 1.22E-04 2x: 1.01E+07 2u: 2.50E-02 ir: 6.60E-05 iu: 8.71E-03 rsn: stol

  Step     11 Time=  4.15114E-02 Dt=  1.92877E-02 [y] snes_conv_reason:    4
  newton =  10 [      38] linear =    10 [        38] cuts =  0 [   0]
  --> SNES Linear/Non-Linear Iterations =           10  /           10
  --> SNES Residual:   1.218560E-04  1.206495E-06  6.595118E-05
  --> max chng: dpl=   4.5172E+03 dpg=   4.1440E+03 dpa=   4.4460E+03
                dxa=   1.3069E-05  dt=   3.7803E-02 dsg=   1.0277E-01

**Example**: Simulation has trouble when grid cells dry out (cells transition from Two-Phase State --> Gas State), and Dt is limited by pressure

::

  == GENERAL MULTIPHASE FLOW =====================================================
  0 2r: 2.25E-07 2x: 0.00E+00 2u: 0.00E+00 ir: 1.58E-07 iu: 0.00E+00 rsn:   0
  1 2r: 9.16E-10 2x: 1.01E+07 2u: 6.27E-06 ir: 7.46E-10 iu: 5.08E-06 rsn: 999

  Step   1103 Time=  2.21028E+00 Dt=  7.56911E-10 [y] snes_conv_reason:  999
  newton =   1 [    1288] linear =     1 [      1288] cuts =  0 [  21]
  --> SNES Linear/Non-Linear Iterations =            1  /            1
  --> SNES Residual:   9.160734E-10  9.070034E-12  7.457545E-10
  --> max chng: dpl=   4.3140E+05 dpg=   5.0805E-06 dpa=   8.0816E-06
                dxa=   1.0919E-15  dt=   4.8880E-10 dsg=   2.3017E-11

  Dt limited by Pressure: Val=4.314E+05, Gov=5.000E+05, Scale=1.08 

**Try**: Adding CHECK_MAX_DPL_LIQ_STATE_ONLY to the GENERAL mode OPTIONS block.
**This will**: Only impose limits on liquid pressure changes when capillary pressure gets high, since small saturation changes at high gas saturation are associated with large capillary pressure changes.

**Fixed Example**:

::

  == GENERAL MULTIPHASE FLOW =====================================================
  0 2r: 3.43E-07 2x: 0.00E+00 2u: 0.00E+00 ir: 3.40E-07 iu: 0.00E+00 rsn:   0
  1 2r: 1.22E-10 2x: 1.01E+07 2u: 2.67E+00 ir: 1.00E-10 iu: 6.75E-01 rsn: 999

  Step     95 Time=  2.21183E+00 Dt=  7.66981E-03 [y] snes_conv_reason:  999
  newton =   1 [     377] linear =     1 [       377] cuts =  0 [  33]
  --> SNES Linear/Non-Linear Iterations =            1  /            1
  --> SNES Residual:   1.215836E-10  1.203798E-12  1.003631E-10
  --> max chng: dpl=   0.0000E+00 dpg=   6.7487E-01 dpa=   8.2037E+01
                dxa=   1.1083E-08  dt=   3.7412E-03 dsg=   4.7712E-04


**Example**: Simulation shows spurious spikes in output variables.

**Try**: With USE_INFINITY_NORM_CONVERGENCE in the NEWTON_SOLVER block, try tightening convergence tolerances by setting values for RESIDUAL_INF_TOL and REL_UPDATE_INF_TOL
**This will**: Force stricter convergence criteria on the simulation and potentially prevent nonlinearities from causing spurious solution behavior.


**Advanced**: 

**Example**: Simulation is taking very small timesteps despite the fact that it is converging well.

::

  == GENERAL MULTIPHASE FLOW =====================================================
  0 2r: 2.23E-07 2x: 0.00E+00 2u: 0.00E+00 ir: 1.56E-07 iu: 0.00E+00 rsn:   0
  1 2r: 3.00E-11 2x: 1.01E+07 2u: 2.47E-03 ir: 2.44E-11 iu: 5.15E-04 rsn: 999

  Step   5734 Time=  1.97179E+00 Dt=  1.01105E-05 [y] snes_conv_reason:  999
  newton =   1 [   22032] linear =     1 [     22032] cuts =  0 [1936]
  --> SNES Linear/Non-Linear Iterations =            1  /            1
  --> SNES Residual:   2.995478E-11  2.965819E-13  2.439427E-11
  --> max chng: dpl=   0.0000E+00 dpg=   5.1500E-04 dpa=   1.1667E-01
                dxa=   1.5748E-11  dt=   5.3204E-06 dsg=   3.0582E-07


**Try**: Loosening individual tolerances. Tolerances can be set on: 
	1) <primary variable here>_ABS_UPDATE_INF_TOL : Absolute solution update within a Newton-Raphson search loop: one for each primary variable from the set {Pl, Pg, Xag,Sg,T}
	2) <primary variable here>_REL_UPDATE_INF_TOL : Relative solution update within a Newton-Raphson search loop: (xn-xn-1)/xn-1
	3) <conservation equation here>_RESIDUAL_ABS_INF_TOL : Absolute value of residuals for water mass, air mass, and energy
	4) <conservation equation here>_RESIDUAL_SCALED_INF_TOL : Scaled value of residuals (residual value divided by accumulation term) for water mass, air mass, and energy.

**This will**: Impose user-specified convergence criteria upon any of the metrics used to declare convergence. Any metrics that are not user-specified will revert to defaults.

**Fixed Example**:

::

  == GENERAL MULTIPHASE FLOW =====================================================
  0 2r: 4.29E-07 2x: 0.00E+00 2u: 0.00E+00 ir: 2.61E-07 iu: 0.00E+00 rsn:   0
  1 2r: 1.60E-06 2x: 1.01E+07 2u: 5.00E+01 ir: 1.30E-06 iu: 1.06E+01 rsn:   0
  2 2r: 5.10E-07 2x: 1.01E+07 2u: 5.11E+00 ir: 4.15E-07 iu: 8.40E-01 rsn:   0
  3 2r: 1.42E-05 2x: 1.01E+07 2u: 4.78E+00 ir: 1.15E-05 iu: 2.29E+00 rsn:   0
  4 2r: 4.31E-06 2x: 1.01E+07 2u: 2.88E+00 ir: 3.51E-06 iu: 1.67E+00 rsn:   0
  5 2r: 4.34E-07 2x: 1.01E+07 2u: 1.71E+00 ir: 3.53E-07 iu: 7.78E-01 rsn:   0
  6 2r: 1.42E-05 2x: 1.01E+07 2u: 4.06E+00 ir: 1.15E-05 iu: 1.91E+00 rsn:   0
  7 2r: 4.32E-06 2x: 1.01E+07 2u: 2.85E+00 ir: 3.52E-06 iu: 1.63E+00 rsn:   0
  8 2r: 4.34E-07 2x: 1.01E+07 2u: 1.71E+00 ir: 3.53E-07 iu: 7.79E-01 rsn: -88
  -> Cut time step: snes=-88 icut=  1[  8] t=  1.92038E+00 dt=  1.22717E-01
  Newton solver reason: Unknown(-88).
  0 2r: 4.29E-07 2x: 0.00E+00 2u: 0.00E+00 ir: 2.61E-07 iu: 0.00E+00 rsn:   0
  1 2r: 5.51E-06 2x: 1.01E+07 2u: 2.70E+01 ir: 4.48E-06 iu: 5.72E+00 rsn:   0
  2 2r: 2.04E-07 2x: 1.01E+07 2u: 2.71E+00 ir: 1.66E-07 iu: 4.59E-01 rsn: 999

  Step     35 Time=  2.04309E+00 Dt=  1.22717E-01 [y] snes_conv_reason:  999
  newton =  10 [     117] linear =    10 [       117] cuts =  1 [   8]
  --> SNES Linear/Non-Linear Iterations =            2  /            2
  --> SNES Residual:   2.041778E-07  2.021562E-09  1.662622E-07
  --> max chng: dpl=   0.0000E+00 dpg=   6.1632E+00 dpa=   1.3859E+03
                dxa=   1.8704E-07  dt=   6.3217E-02 dsg=   3.7129E-03


