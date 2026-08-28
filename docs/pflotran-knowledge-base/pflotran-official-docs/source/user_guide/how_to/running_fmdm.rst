.. _running-pflotran-fmdm:

Running PFLOTRAN linked to FMDM
===============================

STEP 1:

  It is recommended that you clone a fresh PFLOTRAN repository, for example,
  calling it ``~/software/pflotran-fmdm``. Build PFLOTRAN-FMDM using the 
  following commands (the upper level directories are an example only):
  
  ::
  
   > cd ~/software/pflotran-fmdm/src/pflotran  
   > make clean     
   > make libpflotran.a fmdm=1
   
STEP 2:

  Clone the Fuel Matrix Degradation Model (FMDM) repository:
  
  ::
  
   > cd ~/software
   > hg clone https://bitbucket.org/pflotran_snl/fmdm
   
STEP 3:

  Move into the FMDM respository directory v2.3 and compile ``pflotran_fmdm`` using
  the same ``PETSC_DIR`` and ``PETSC_ARCH`` evironmental settings as the 
  PFLOTRAN-FMDM repository which contains the ``libpflotran.a`` file (e.g. see STEP 
  1 above).
  
  ::
  
   > cd ~/software/fmdm/v2.3
   > make pflotran_fmdm PFLOTRANFMDM_DIR=~/software/pflotran-fmdm
   
STEP 4:

  Use the ``pflotran_fmdm`` executable to run simulations where the FMDM is 
  linked, not the executable in your PFLOTRAN-FMDM repository. For example,
  
  ::
  
   > mpirun -np 1 ~/software/fmdm/v2.3/pflotran_fmdm -input_prefix my_fmdm_simulation
