.. _contributing-to-pflotran:

Contributing to the PFLOTRAN Project
====================================

*I have modified PFLOTRAN source code (e.g. added capability, fixed a bug, etc.). How do I contribute new code to the PFLOTRAN source code repository?*

  Source code contributions by anyone are welcome. However, code modifications must undergo peer review before being merged to the *master* branch of the PFLOTRAN repository. Please adhere to the following steps when making modifications to the code. *Note: Exact steps are not detailed due to frequent updates to the Bitbucket user interface.*

  1. Create a fork of the PFLOTRAN repository on Bitbucket (`bitbucket.org/pflotran/pflotran <https://bitbucket.org/pflotran/pflotran>`_).

  2. Clone the repository to a local machine

     git clone git\@bitbucket.org:username/repository-name.git

  3. Make modifications and commit these changes to the master (or a development) branch of the repository 

    git commit -i filename1 filename2 -m 'a short, descriptive message'

  4. Ensure that all unit and regression tests pass. 

    a. Execute *make test* in PFLOTRAN_DIR/src/pflotran directory. *Note: Unit and regressiont test gold files are generated with unoptimized GNU-compiled code. You will need to use a GNU compiler (-O0) to ensure that all tests pass.*

    b. If new capability was developed, create a new regresson test: :ref:`regression-test-manager-new-tests`

  5. Push these changes up to the forked repository on Bitbucket 

    git push

  6. Submit a Pull Request.

  7. A PFLOTRAN developer will review the changes and either, accept the request or provide feedback.

*I want to help document PFLOTRAN. How do I contribute to the PFLOTRAN documentation repository?*

  **Excellent!** Follow the steps above for source code, using the repository: `bitbucket.org/pflotran/pflotran-documentation <https://bitbucket.org/pflotran/pflotran-documentation>`_. Obviously, unit and regression testing is not required.


