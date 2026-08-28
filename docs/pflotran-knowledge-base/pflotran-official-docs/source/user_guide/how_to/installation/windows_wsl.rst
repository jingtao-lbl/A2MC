.. _windows-subsystem-for-linux-install:

Windows Installation Instructions with Windows Subsystem for Linux
==================================================================

Required Software
-----------------

* Windows 10
* Windows Subsystem for Linux

Installation Instructions 
-------------------------

1. Install Windows Subsystem for Linux. You can follow the instruction from 
   Microsoft `here <https://docs.microsoft.com/en-us/windows/wsl/install-win10>`_.
   If you don't know which Linux distribution to choose, Ubuntu should be your 
   default choice as these instructions were writted for Ubuntu 22.04 LTS.

2. Prepare the new Ubuntu distribution to install PFLOTRAN. Run in the command line:

    .. code-block :: bash

        sudo apt update --fix-missing
        sudo apt install gcc gfortran make cmake python libtool autoconf build-essential pkg-config automake tcsh mpich

3. Follow the PFLOTRAN `Linux instructions 
   <https://www.pflotran.org/documentation/user_guide/how_to/installation/linux.html>`_. 

4. PFLOTRAN is now installed in your Windows Subsystem for Linux. 
   You can now run PFLOTRAN from any folder by opening a Linux interpretor 
   (Maj + right click). See `Running PFLOTRAN 
   <https://www.pflotran.org/documentation/user_guide/how_to/running.html>`_.   

