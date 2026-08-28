.. _linux-primer:

Linux Primer
============

Basic Linux commands
--------------------

**cd <path>** - change to directory *path*.
  
 cd /home/user/pflotran/src/pflotran

 cd .. *(move up a directory)*

 cd *(change to home directory)*

**cp <filename1> <filename2>** - copy *filename1* to *filename2*.

 cp abc.in xyz.in

 cp abc.in project/. *(copy abc.in into directory project)*

**ls** - list all files and directories in the current directory.

**mkdir <foldername>** - create a directory named *foldername*.

 mkdir project

**mv <filename1> <filepath>** - rename file *filename1* to *filepath* or move *filename* to directory/filename in *filepath*.

 mv abc.in xyz.in *(rename file)*

 mv abc.in project/. *(move abc.in into directory project)*

**pwd** - prints the path to the current directory or "print working directory".

**rm <filename>** - remove file *filename*.

 rm abc.in

Advanced Linux commands
-----------------------

**gedit <filename>** - open file *filename* in the gedit text editor.

 gedit pflotran.in

**grep "string" <filename>** - search for instances of "string" in the file *filename*.

 grep CHEMISTRY pflotran.in

**ls -ltr** -  list files by last time modified in reverse order and in long listing format.

  ls -ltr \*.py 

**man <command>** - display user manual for *command*.

  man cp

**rm -Rf <foldername>** - force (f) recursive (R) removal of the directory *folername* and all underlying files and directories. **Be careful!**
  
 rm -Rf project
   
  
