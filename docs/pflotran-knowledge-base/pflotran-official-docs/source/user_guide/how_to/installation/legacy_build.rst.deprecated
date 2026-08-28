.. _legacy-build-install:

Legacy Build Installation Instructions
======================================

**Note: The legacy (non-process model) version of PFLOTRAN was deprecated on** 
**February 28, 2014.  To revert back to the legacy version, do the following:**

1. Revert PETSc back to Git SHA-1 hash: 
   06283fd4323cef45a7147b2226c8e0c084e2a1d2, configure and build PETSc:
   * cd $PETSC_DIR
   * git checkout 06283fd4323cef45a7147b2226c8e0c084e2a1d2
   * ./config/configure.py (and whatever else you do to compiler your petsc-dev)
   * make all

2. Revert pflotran-dev back to last supported legacy changeset (i.e. tag = 
   'pflotran-legacy-deprecated'):
   * cd $PFLOTRAN_DIR/src/pflotran
   * hg update -C pflotran-legacy-deprecated
   * make -f makefile_legacy clean
   * make -f makefile_legacy pflotran
   * make -f makefile_legacy test

**Please contact the pflotran-dev mailing list if:**

* Functionality is missing from the current version of PFLOTRAN and its not 
  listed on the `Lost Capabilities <https://bitbucket.org/pflotran/pflotran/wiki/Developers/CodeDevelopment/CapabilityLost>`_ 
  page on the PFLOTRAN Bitbucket wiki.

* The current version of PFLOTRAN does not produce similar results for your 
  problem.

