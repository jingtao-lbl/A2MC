.. _software-productivity-and-sustainability-plan:

Software Productivity and Sustainability Plan - Required by DOE Office of Science
=================================================================================

Overall Software Development Process
------------------------------------

*How are software requirements determined and transformed into implemented code, tested and deployed (the software lifecycle)?*

  New capability is implemented in PFLOTRAN based on the following categorization:
    
  New **scientific process models** are documented with governing equations, associated constitutive relations, and underlying assumptions clearly defined.  A prototype of the process model is coded in a feature branch (or fork) of the repository, where new development is isolated from the repository's master branch.  All development (prototype to full implementation) will continue in this branch until the implementation is deemed successful.  At that point, the new capability enters an alpha stage where testing is performed to verify the correctness of the implementation (e.g. verification or validation).  Once tested, unit and/or regression tests are implemented.  A pull request is then submitted to the master branch where Senior Developers review the proposed changes and unit/regression tests, ensure that the tests pass.  Once accepted, the changes are merged with the master branch, and the code is deployed to the public in beta form through the development version of the code.
    
  New **code infrastructure** (e.g. code refactoring to improve performance and/or usability, update updating third-party library interfaces, adding error messaging, etc.) does not require the level of detailed documentation associated with process models.  However, the stages of implementation and acceptance remain the same.  All unit and regression tests must pass before changes may be merged with the master branch.

*How are new and revised capabilities integrated into the existing software while preserving existing capabilities (regression testing)?*

  Unit and/or regression tests are implemented to ensure that code modifications do not alter results generated from existing code.  Code coverage studies are performed periodically to improve test coverage.  New unit and/or regression tests are implemented when bugs are found in uncovered portions of the code.

*How will users learn about utilizing the code in their scientific efforts (documentation and training)?*

  A user manual and theory guide are publicly available online at `documentation.pflotran.org <http://documentation.pflotran.org>`_.  Workshops are offered periodically and upon request.  Users may contact pflotran-users@googlegroups.com with user questions and pflotran-dev@googlegroups.com to report bugs or request functionality.

Tools and Processes
-------------------

*How will source code be developed and managed (source management tools and processes)?*

  The main code repository is hosted at `bitbucket.org/pflotran/pflotran <https://bitbucket.org/pflotran/pflotran>`_.  This repository is open to the public with push privileges limited to a group of experienced developers.  Anyone may submit proposed modifications to the code by forking the main repository on Bitbucket, pushing proposed modifications to the fork, and submitting a pull request after all unit and regression tests pass.  These proposed changes are reviewed by Senior Developers with push privileges.  The person submitting the pull request iterates with the Senior Developers until code modifications are suitable for acceptance, and an automated message is sent upon the successful merge.  Version control is maintained through the Git software configuration management system. 

*How will feature requests and software faults or "bugs" be recorded and managed (issue tracking tools and processes)?*

  Users may report bugs and request functionality through a public issue tracker or an email submission to pflotran-dev@googlegroups.com.  Issue tracking is managed within the main repository through Bitbucket.

*How are unit and regression tests invoked (unit and regression testing tools and processes)?*

  Regression tests are implemented in Python with an approach that is native to PFLOTRAN.  These test are executed through the makefile with the 'make test' or 'make rtest' commands.  In short, simulations results are analyzed with maximum, minimum, mean and sampled values for specific variables compared to a gold standard stored in .regression.gold files.  The maximum, miniumum and mean values are calculated globally, while sampled values are specific to individual grid cells.   The user can specify sampling through a list of grid cell ids and by specifying a number of equally spaced samples per process.  Python scripting compares newly generated .regression files with their .regression.gold counterparts and results falling outside absolute or relative tolerances are reported as failures.  There is great flexibility in setting tolerances (i.e. per variable, test, suite or global), with the default tolerance being tight (1.e-12 absolute).

*How will users and collaborators access software products (software distribution tools and processes)?*

  All software distribution is handled through Bitbucket where the user may clone the main repository or download a snapshot of the repository (e.g. in .tar.gz or .zip form).
  
Training
--------

*How will new software developers be trained?*

  A Developer Guide is publicly available online at `documentation.pflotran.org <http://documentation.pflotran.org>`_ where new developers may learn about many topics (e.g. Fortran coding standards, unit testing, major refactors, etc.).  

*How will credit for the work of departing developers be retained?*

  Developer contributions are automatically documented in all commit messages for the entirety of the project.  In addition, each subroutine has a comment section at the top which includes the author name and date of the contribution.  Any developer may add their name to the list of authors.  Metrics on developer contribution to the code base are available through `www.openhub.net/p/pflotran <https://www.openhub.net/p/pflotran>`_.

Improvement Strategies
----------------------

*How will software productivity and sustainability be improved over the life of the project?*

  Best practices observed in other projects will be adopted.  As more effective tools become available, they also will be adopted.

*How will efforts to improve software sustainability and productivity be rewarded?*

  Developers who practice better productivity and sustainability will naturally be given greater weight in prioritizing future directions for the code.  Their names will be more publicly recognized through association.




