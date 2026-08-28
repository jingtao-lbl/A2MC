# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
# import os
# import sys
# sys.path.insert(0, os.path.abspath('.'))

from datetime import date

# -- Project information -----------------------------------------------------

project = 'PFLOTRAN'
copyright = f'{date.today().year}, www.pflotran.org'
author = ','.join([
    'Benjamin Andre',
    'Gautam Bisht',
    'Nathan Collier',
    'Jennifer Frederick',
    'Glenn Hammond',
    'Piyoosh Jaysaval',
    'Satish Karra',
    'Jitu Kumar',
    'Rosie Leone',
    'Peter Lichter',
    'Chuan Lu',
    'Richard Mills',
    'Michael Nole',
    'Paolo Orsini',
    'Heeho Park',
    'Moise Rousseau',
])

# The full version, including alpha/beta/rc tags
release = 'v6.0'


# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    'sphinx.ext.intersphinx',
    'sphinx.ext.mathjax',
    'sphinx.ext.viewcode',
    'sphinx.ext.autodoc',
    'sphinx_math_dollar',
]

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = [
    '_build',
    'user_guide/cards/process_model_cards/wipp_source_sink*',
]

# output from 
#from pygments.styles import get_all_styles
#styles = list(get_all_styles())
#print(styles)
# ['default', 'emacs', 'friendly', 'friendly_grayscale', 'colorful', 'autumn', 'murphy', 'manni', 'material', 'monokai', 'perldoc', 'pastie', 'borland', 'trac', 'native', 'fruity', 'bw', 'vim', 'vs', 'tango', 'rrt', 'xcode', 'igor', 'paraiso-light', 'paraiso-dark', 'lovelace', 'algol', 'algol_nu', 'arduino', 'rainbow_dash', 'abap', 'solarized-dark', 'solarized-light', 'sas', 'stata', 'stata-light', 'stata-dark', 'inkpot', 'zenburn', 'gruvbox-dark', 'gruvbox-light', 'dracula', 'one-dark', 'lilypond']

pygments_style = 'sphinx'
#pygments_style = 'sas'
nitpicky = True

# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#html_theme = 'alabaster'
html_theme = 'nature'
html_theme_options = {
    'sidebarwidth' : '350',
}
html_logo = '_static/pflotran_logo.jpg' 

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']

# Custom sidebar templates, maps document names to template names.
html_sidebars = {'**': [
    'globaltoc.html',
    'localtoc.html',
    'relations.html',
    'searchbox.html'
]}

# -- Options for MathJax -----------------------------------------------------
mathjax3_config = {
  'tex': {
    'inlineMath': [[r'\(', r'\)']],
    'displayMath': [[r'\[', r'\]']],
    'macros': {
      # add latex macros (similar to \def, \newcommand) here and reference in
      # .rst as \porosity
      'porosity': r'\phi',
      'saturation': r's',
      'tortuosity': r'\tau',
      'density': r'\rho',
      'bulkelectricalconductivity': r'\sigma',
      'electricalpotential': r'\psi',
      # macros for variable units
      'sq': r'{^{2}}',
      'cub': r'{^{3}}',
      'inv': r'{^{-1}}',
      'invsq': r'{^{-2}}',
      'invcub': r'{^{-3}}',
      'invN': [r'{^{-#1}}',1],
      'strnull': r'{\text{-}}',
      'strtime': r'{\text{s}}',
      'strinvtime': r'{\strtime\inv}',
      'strlength': r'{\text{m}}',
      'strinvlength': r'{\text{m}\inv}',
      'strarea': r'{\strlength\sq}',
      'strinvarea': r'{\strlength}\invsq}',
      'strvolume': r'{\strlength\cub}',
      'strinvvolume': r'{\strlength\invcub}',
      'strmass': r'{\text{kg}}',
      'strmnrl': r'{\text{mnrl}}',
      'strmole': r'{\text{mole}}',
      'strpore': r'{\text{pore}}',
      'strbulk': r'{\text{bulk}}',
      'strinvmass': r'{\strmass\inv}',
      'strmol': r'{\text{kmol}}',
      'strinvmol': r'{\strmol\inv}',
      'strtemperature': r'{\text{C}}',
      'strinvtemperature': r'{\strtemperature\inv}',
      'strenergy': r'{\text{MJ}}',
      'strinvenergy': r'{\strenergy\inv}',
      'strpressure': r'{\text{Pa}}',
      'strinvpressure': r'{\strpressure\inv}',
      'strviscosity': r'{\strmass\,\strinvlength\,\strinvtime}',
      'strinvviscosity': r'{\strlength\,\strtime\,\strinvmass}',
      'strvolfrac': [r'{\strvolume\,\text{#1}\,\{\strvolume\,\text{#2}\}\inv}',2],
      'strporosity': r'{\strvolfrac{pore}{bulk}}',
      'strsaturation': [r'{\strvolfrac{#1}{pore}}',1],
      'strliquidsaturation': r'{\strsaturation{liquid}}',
      'strgassaturation': r'{\strsaturation{gas}}',
      'strmassdensity': r'{\strmass\,\strinvvolume}',
      'strmoldensity': r'{\strmol\,\strinvvolume}',
      'strenergydensity': r'{\strenergy\,\strinvvolume}',
      'streleccond': r'{\text{S}\,\strinvlength}',
      'strelecpotential': r'{\text{V}}',
      'strmolfraction': [r'{\strmol\,\text{#1}\,\{\strmol\,\text{#2}\}\inv}',2],
      'strmassfraction': [r'{\strmass\,\text{#1}\,\{\strmass\,\text{#2}\}\inv}',2],
      'units':      [r'{\left[{#1}\right]}',1],
      'unitless':   [r'{\units{\strnull}}'],
      'unitsfrac':  [r'{\left[#1\{#2\}\inv\right]}',2],
      'unitsfracN': [r'{\left[#1\{#2\}\invN{#3}\right]}',3],
      'unitsfracstr': [r'{\left[\text{#1}\{\text{#2}\}^{-1}\right]}',2],
      'invstr': [r'{\{#1\}^{-#2}}', 2], ## for those macros with arguments
    }
  }
}

