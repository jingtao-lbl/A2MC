User's Guide
============

PFLOTRAN: Getting Started
^^^^^^^^^^^^^^^^^^^^^^^^^

.. toctree::
   :maxdepth: 2

   /user_guide/how_to/introduction.rst
   /user_guide/how_to/linux_primer.rst
   /user_guide/how_to/installation/installation.rst
   /user_guide/how_to/running.rst
   /user_guide/how_to/creating_an_input_file.rst
   /user_guide/how_to/regression.rst
   /user_guide/how_to/visualization.rst
   /user_guide/how_to/benchmark.rst

.. The following are the hidden pages that are linked in the User's Guide:
.. toctree::
   :hidden:

   /user_guide/how_to/installation/linux.rst
   /user_guide/how_to/installation/windows_visual_studio.rst
   /user_guide/how_to/installation/windows_wsl.rst
   /user_guide/how_to/installation/machine_specific.rst
   /user_guide/how_to/installation/vm.rst
   /user_guide/how_to/installation/previous_petsc_releases.rst
   /user_guide/how_to/simple_flow_problem.rst
   /user_guide/how_to/running_fmdm.rst

.. _card-index:

Input Deck Cards
^^^^^^^^^^^^^^^^

SIMULATION Block Cards
----------------------

.. toctree::
   :maxdepth: 1
   :glob:

   /user_guide/cards/simulation/simulation_card.rst
   /user_guide/cards/simulation/subsurface_flow_card.rst
   /user_guide/cards/simulation/subsurface_transport_card.rst
   /user_guide/cards/simulation/subsurface_geophysics_card.rst
   /user_guide/cards/simulation/checkpoint_card.rst
   /user_guide/cards/simulation/restart_card.rst
   /user_guide/cards/simulation/well_model.rst

.. toctree::
   :hidden:

   /user_guide/cards/simulation/input_record_file_card.rst
   /user_guide/cards/simulation/subsurface_flow_mode_card.rst
   /user_guide/cards/simulation/subsurface_transport_mode_card.rst
   /user_guide/cards/simulation/subsurface_geophysics_mode_card.rst

*SUBSURFACE_FLOW Mode Cards*

.. toctree::
   :maxdepth: 1
   :glob:

   /user_guide/cards/simulation/subsurface_flow_modes/*

*SUBSURFACE_TRANSPORT Mode Cards*

.. toctree::
   :maxdepth: 1
   :glob:

   /user_guide/cards/simulation/subsurface_transport_modes/*

*SUBSURFACE_GEOPHYSICS Mode Cards*

.. toctree::
   :maxdepth: 1
   :glob:

   /user_guide/cards/simulation/subsurface_geophysics_modes/*

.. _card-index-subsurface:

SUBSURFACE Block Cards
----------------------

.. toctree::
   :maxdepth: 1
   :glob:

   /user_guide/cards/subsurface/*

CHEMISTRY Block Cards
---------------------

.. toctree::
   :maxdepth: 1
   :glob:

   /user_guide/cards/subsurface/chemistry/*
   /user_guide/cards/subsurface/chemistry/reaction_sandbox/*

Geomechanics Cards
------------------

.. toctree::
   :maxdepth: 1
   :glob:

   /user_guide/cards/geomechanics/*

Geophysics Cards
------------------

.. toctree::
   :maxdepth: 1
   :glob:

   /user_guide/cards/geophysics/*

Utility Cards
-------------

.. toctree::
   :maxdepth: 1
   :glob:

   /user_guide/cards/utility_cards/*

GDSA Cards
----------

.. toctree::
   :maxdepth: 1
   :glob:

   /user_guide/cards/gdsa/*

.. The following are hidden pages that are linked in the Input Deck Cards:
.. toctree::
   :hidden:
   :glob:

   /user_guide/cards/pages/*
   /user_guide/cards/subsurface/grids/*
   /user_guide/cards/subsurface/region/*
   /user_guide/cards/subsurface/material_property/*
   /user_guide/cards/subsurface/source_sink_sandbox/*
   /user_guide/cards/gdsa/waste_form/*
   /user_guide/cards/wipp/*

