.. _machine-specific-petsc-configs:

Machine-Specific PETSc Configurations
=====================================

NERSC - Cori
--------------

Date: 04/16/2020

Modules Instructions
~~~~~~~~~~~~~~~~~~~~
 
::
 
 module unload PrgEnv-pgi
 module load PrgEnv-intel
 module swap cray-mpich cray-mpich # to ensure that mpich is properly loaded under Intel
 module unload hdf5-parallel
 module load cray-hdf5-parallel
 module load cmake
 module load python
 module unload darshan

Configure
~~~~~~~~~

::

 ./config/configure.py PETSC_ARCH=cori_intel_O --with-language=c --with-cc=cc --with-cxx=CC --with-fc=ftn COPTFLAGS="-g -O3 -fp-model fast" CXXOPTFLAGS="-g -O3 -fp-model fast" FOPTFLAGS="-g -O3 -fp-model fast" --download-hypre=1 --download-metis=1 --download-parmetis=1 --download-mumps=1 --download-scalapack=1 --with-hdf5=1 --with-debugging=0 --with-shared-libraries=0

NERSC - Edison
--------------

Date: 10/26/2015

Modules Instructions
~~~~~~~~~~~~~~~~~~~~
 
::
 
 module unload PrgEnv-pgi
 module load PrgEnv-intel
 module swap cray-mpich cray-mpich # to ensure that mpich is properly loaded under Intel
 module unload hdf5-parallel
 module load cray-hdf5-parallel
 module load cmake
 module load valgrind
 module load python

Configure
~~~~~~~~~

::

 ./config/configure.py --with-cc=cc --with-cxx=CC --with-fc=ftn --with-shared-libraries=0 --with-debugging=0 --with-clanguage=c --PETSC_ARCH=edison_intel_O --with-x=0 --download-parmetis=1 --download-metis=1 --with-hdf5=1 --with-hdf5-dir=$HDF5_DIR --with-c2html=0
