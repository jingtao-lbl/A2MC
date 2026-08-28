INSTRUCTIONS ON HOW TO GENERATE DOCUMENTATION:

You must install Sphinx. We use Sphinx to generate the documentation (html files and a pdf file). Read about installation here: http://www.sphinx-doc.org/en/stable/install.html Note: The conf.py file is the Sphinx configuration file. This should only be edited if you know what you are doing with documentation.

Once Sphinx is installed, change directories to repo-name/documentation.

To create html files, type the command:

> make html

To create a pdf, type the command:

> make latexpdf

Sometimes it is useful to clean out the _build directory. You can do this by typing the command:

> make clean

Both the html files and the pdf file will be generated in the repo-name/documentation/_build directory. Note: This directory is ignored in the .hgignore file.
