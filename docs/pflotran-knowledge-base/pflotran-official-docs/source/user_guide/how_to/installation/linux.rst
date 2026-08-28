.. _linux-install:

Linux Installation Instructions
===============================

Required software packages:
---------------------------
* Fortran 2003/2008 compiler: gfortran >= 7.x, intel >= 19
* Git_ source control management tool
* Message Passing Interface (MPI):  E.g.  `MPICH2 <http://www.mcs.anl.gov/research/projects/mpich2>`_, `Open MPI <http://www.open-mpi.org>`_, etc.
* BLAS/LAPACK libraries 
* Hierarchical Data Format HDF5_
* `PETSc git repository <https://gitlab.com/petsc/petsc>`_
* `METIS/ParMETIS <http://glaros.dtc.umn.edu/gkhome/metis/parmetis/overview>`_ (for unstructured grids)
* Python3, including python3-h5py and python3-matplotlib (or pip3 install h5py matplotlib)

Installation Instructions
-------------------------

1. Install Git_. Git is 
   usually installed by default on most modern operating systems. It is 
   usually available through your package manager.
 
2. Install a Fortran compiler (see bullets above), MPI, BLAS/LAPACK and 
   HDF5_ libraries (Note that petsc can be 
   configured to download and install these libraries automatically.  
   E.g. -\\-download-mpich=yes or -\\-download-openmpi=yes, 
   -\\-download-hdf5=yes, -\\-download-f-blas-lapack=yes)

3. Install PETSc

    3.1. Clone petsc and check out the **supported** version:

    .. code-block:: bash

        git clone https://gitlab.com/petsc/petsc petsc
        cd petsc
        git checkout v3.24.5

    3.2. Configure PETSc (see `PETSc installation instructions`_).

    .. code-block:: bash
 
        ./configure --COPTFLAGS='-O3' --CXXOPTFLAGS='-O3' --FOPTFLAGS='-O3 -Wno-unused-function' --with-debugging=no --download-mpich=yes --download-hdf5=yes --download-hdf5-fortran-bindings=yes --download-fblaslapack=yes --download-metis=yes --download-parmetis=yes

    Note: To support HDF5 zlib compression, add ``--download-hdf5-configure-arguments="--with-zlib=yes"`` to the command line.

    3.3. Set the PETSC_DIR and PETSC_ARCH environment variables based on the PETSc_ installation location (PETSC_DIR) and architecture (PETSC_ARCH: hardware, compilers, etc.).  See `PETSc environment variables`_. 
         The environmental variables can be set in your ``~/.bashrc`` file by adding
         the following two lines somewhere in the file:
         
         .. code-block :: bash
         
            export PETSC_DIR=/home/username/path_to_top_level_petsc
            export PETSC_ARCH=gnu-c-debug
         
         Note: You can check what your ``PETSC_ARCH`` actually is (the above is just
         an example) by opening up the directory where PETSc is installed and
         looking in the ``configure.log`` file for ``--PETSC_ARCH=``. After you 
         update your ``.bashrc`` file, either close the terminal and open a new
         one, or type ``source ./.bashrc`` for the changes to take effect.

    3.4. Compile PETSc_

    .. code-block :: bash

        cd $PETSC_DIR
        make all 

    or even better follow the 'make' instructions printed at the end of configuration.  E.g.

    .. code-block :: bash

        xxx=========================================================================xxx
          Configure stage complete. Now build PETSc libraries with:
          make PETSC_DIR=/proj/geo002/petsc PETSC_ARCH=cray-xt4-pgi all
        xxx=========================================================================xxx

4. Download (clone) PFLOTRAN off `Bitbucket`_.

 ::

  git clone https://bitbucket.org/pflotran/pflotran

5. Compile PFLOTRAN (ensure that PETSC_DIR and PETSC_ARCH environment variables are properly defined, or PFLOTRAN will not compile)

 ::

  cd pflotran/src/pflotran
  make pflotran

Troubleshooting
---------------

Common issues with installing is found on the FAQ page:
:ref:`How do I resolve installation issues?`





.. _Git: http://git-scm.com/
.. _PETSc: https://gitlab.com/petsc/petsc
.. _PETSc installation instructions: https://petsc.org/release/installPETSC_HAVE_PARMETIS
.. _PETSc environment variables: https://petsc.org/release/install/multibuild/#environmental-variables-petsc-dir-and-petsc-arch
.. _HDF5: http://www.hdfgroup.org/HDF5
.. _Bitbucket: https://bitbucket.org/pflotran/pflotran/wiki/Home.

