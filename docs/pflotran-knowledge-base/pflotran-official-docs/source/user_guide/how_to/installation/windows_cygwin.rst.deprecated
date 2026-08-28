.. _windows-cygwin-gnu-install:

Windows Installation Instructions using Cygwin
==============================================

Author: Glenn Hammond
--------------------------------
These instructions are for building PFLOTRAN using Cygwin GNU compilers.  
This build takes many hours to complete, mainly due to the building of the 
third-party libraries.

Required Third-Party Libraries
--------------------------------------
* Cygwin_: a collection of tools which provide a Linux look and feel environment for Windows.  Use the 32-bit version.
* PETSc_

Installation Instructions
-----------------------------

1. Download and install the 32-bit version of Cygwin_.  The link to `setup-x86.exe <http://cygwin.com/setup-x86.exe>`_ will take you to the most recent version.  Step through the setup program.  I typically select the following options:

 * **Choose a Download Source Dialog:** Install from Internet
 * **Select Root Install Directory Dialog:** C:\\software\\cygwin and install for "All Users".
 * **Select Local Package Directory:** C:\\Temp.
 * **Select Your Internet Connection:** Direct Connection
 * **Choose A Download Site:** ftp://mirror.mcs.anl.gov has always worked well, but you may desire a closer site.
 * **Select Packages:** Ensure that at least the following are selected (we may have to iterate on this as I do not have a clean install of which to work in provding guidance).

  * All default packages (some of the below may be default)
  * bash (default) (for bash users)
  * cmake
  * diffutils
  * gcc-core
  * gcc-fortran
  * gcc-g++
  * git
  * gzip (default)
  * make
  * patch and patchutils
  * python
  * tar (default)
  * tcsh (for t-shell users)

 * **Create Icons:** Be sure to uncheck the annoying icons at the end.

2. Install PETSc_.  Follow instructions at `PETSc website`_. PETSc should be 
   installed using a cygwin terminal. Be sure to check out the Git hash defined 
   in :ref:`linux-install`. Remember to define ``PETSC_DIR`` and ``PETSC_ARCH`` 
   in the system environment variables (Start -> Control Panel -> System -> 
   Advanced System Settings -> Environment Variables). I use the following 
   settings for configure:  

  ./config/configure.py --with-cc=gcc --with-fc=gfortran --with-cxx=g++ --with-clanguage=c --with-petsc-arch=gnu-c-debug --with-debugging=yes --with-shared-libraries=no --download-mpich=yes --download-hdf5=yes --download-metis=yes --download-parmetis=yes --download-fblaslapack=yes --with-c2html=no

  **For optimized production runs, set --with-debugging=no.**

3. At this point, follow the :ref:`linux-install`, starting with step 4.

.. _PETSc website: http://www.mcs.anl.gov/petsc/developers/index.html
.. _PETSc: http://gitlab.com/petsc/petsc
.. _Cygwin: http://www.cygwin.com
