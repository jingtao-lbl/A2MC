.. _linux-vm:

Linux Virtual Machine Installation Instructions
===============================================

An Ubuntu 22.04 virtual machine (VM) with PFLOTRAN and supporting software 
(i.e. GNU compilers, python [h5py, matplotlib], ParaView) can be downloaded 
from Google Drive. This virtual machine is small (4 cores, 8 GB memory, 100 GB hard drive) and designed for use in PFLOTRAN short courses; so please bear in mind that it is not ideal for large simulations or parallel computing, and the regression tests will not pass due to the 4-core limitation.

Installation Instructions
-------------------------

1. Download and install the appropriate version of VirtualBox_ for your machine
   (Windows, OS X, Linux).

2. Download the `PFLOTRAN VM`_ named with the following convention: 
   "pflotran-ubuntuXX-mon-year.zip", and unzip in a local directory.

3. Start VirtualBox.

4. From the menu, select *Machine -> Add*.

5. Navigate to the directory where the zipfile was unzipped and load the file:
   *pflotran-ubuntuXX-mon-year.vbox*. Note: only .vbox files will be 
   displayed.

6. Click on the newly loaded virtual machine (with the same name) and click on 
   *Start*.

The virtual machine will load.  The username and password for this VM are *user* and *pflotran*, respectively, should the machine become locked. The PFLOTRAN repository is located in the directory named *pflotran* while the PFLOTRAN executable is at *pflotran/src/pflotran/pflotran*.  

*Note:* Should any of the instructions above be out-of-date, please email pflotran-dev at googlegroups dot com.

.. _PFLOTRAN VM: https://drive.google.com/drive/folders/1G8c-lfREJVOrCVH5edy1w8fy6wld5tOd?usp=sharing
.. _VirtualBox: https://www.virtualbox.org/wiki/Downloads

