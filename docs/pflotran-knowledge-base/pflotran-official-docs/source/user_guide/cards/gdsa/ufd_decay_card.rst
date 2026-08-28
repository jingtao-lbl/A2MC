Back to :ref:`card-index`

.. _ufd-decay-card:

UFD_DECAY
=========
The UFD Decay Process Model is :ref:`formally documented here <pm_ufd_decay>`.

Specifies the isotope decay, ingrowth, and phase partitioning model.

Required Cards:
---------------
ELEMENT <string>

 Opens the block for defining elements, where <string> is the name of the element.

  SOLUBILITY <float>
   
   Specifies the solubility of the element in units of [M].

  KD <float>

   Opens a block where linear Kds are entered for each material property (see example below). It is assumed that all elemental isotopes sorb at the same rate, in units of [kg-water/m3-bulk].
   
   (Optional) If the Kd of a material within an element is defined by a dataset file, the `DATASET` keyword can be used followed by the name of the file and the name of the material.

::

 MATERIAL_PROPERTY clay
 ...
 MATERIAL_PROPERTY sand
 ...
 MATERIAL_PROPERTY loam
 ...
 ELEMENT Am
   SOLUBILITY 3.39d-7 ! [M]
   KD
     clay 6.d6
     sand 6.d4
     DATASET Kd_Am_loam.txt loam # Kd of loam defined by dataset file
   /
 /

ISOTOPE <string>

 Specifies each isotope, where <string> is the isotope name. The following required blocks:

  ELEMENT <string>

   Specifies the name of the element (group) to which the isotope belongs.

  DECAY_RATE <float>

   Specifies the first-order decay rate in units [1/sec].

  DAUGHTER <string> <float>

   Gives the name of the daughter isotope and the unitless stoichiometry of contribution to that daughter isotope.

::

 ISOTOPE Am241
   ELEMENT Am
   DECAY_RATE 5.08d-11 ! [1/sec]
   DAUGHTER Np237 1.d0
 /


Optional Cards:
---------------

IMPLICIT_SOLUTION

 Applies an implicit solution approach for the decay of isotopes.

How to set up an input file:
----------------------------

1. Add necessary ``PRIMARY_SPECIES`` and kinetic ``MINERALS`` to the input deck. The name of each mineral must be the same as the name of the primary species with ``(s)`` appended (e.g. ``I129`` and ``I129(s)``). Blocks for ``MINERAL_KINETICS`` must be included with a rate constant of ``0.d0``. See example:

::

 PRIMARY_SPECIES
   I127
   I129
   Am241
   ...
   Th232
 /

 MINERALS
   I127(s)
   I129(s)
   Am241(s)
   ...
   Th232(s)
 /
 
 MINERAL_KINETICS
   I127(s)
     RATE_CONSTANT 0.d0
   /
   I129(s)
     RATE_CONSTANT 0.d0
   /
   Am241(s)
     RATE_CONSTANT 0.d0
   /
   ...
   Th232(s)
     RATE_CONSTANT 0.d0
   /
 /

2. Within the ``CONSTRAINTS``, ensure that species concentrations are specified for all primary species (and minerals if the constraint is used in an initial condition). See example:

::

 CONSTRAINT initial
   CONCENTRATIONS
     I127    1.d-20 F
     I129    1.d-20 F
     Am241   1.d-20 F
     ...
     Th232   1.d-20 F
   /
   MINERALS
     I127(s)   1.d-4 1.d0
     I129(s)   0.d0  1.d0
     Am241(s)  1.d-4 1.d0
     ...
     Th232(s)  0.d0  1.d0
   /
 /

3. Outside the ``SUBSURFACE/END_SUBSURFACE`` blocks, add a ``UFD_DECAY`` block that lists all elements and isotopes. Each element has a name (the root of the isotope; e.g. I for I127, Th for Th232), solubility, and Kd. Each isotope has a name, element, decay rate, daughter name and daughter stoichiometry (assuming a decay daughter product exists). See example:

::

 UFD_DECAY
   ELEMENT I
     SOLUBILITY 1.d4
     KD
       sand 0.d0 ! kg water/m^3 bulk
     /
   /
   ELEMENT Am
     SOLUBILITY 3.39d-7
     KD
       sand 6.d6
     /
   /
   ...
   ELEMENT Th
     SOLUBILITY 7.94d-11
     KD
       sand 2.5d6
     /
   /
   ISOTOPE I127
     ELEMENT I
     DECAY_RATE 0.
   /
   ISOTOPE I129
     ELEMENT I
     DECAY_RATE 1.29d-15
   /
   ISOTOPE Am241
     ELEMENT Am
     DECAY_RATE 5.08d-11
     DAUGHTER Np237 1.d0
   /
   ...
   ISOTOPE Th232
     ELEMENT Th
     DECAY_RATE 1.56d-18
   /
 END

4. Include ``UFD_DECAY`` as a process model in the ``SIMULATION`` block. See example:

::
 
 SIMULATION
   SIMULATION_TYPE SUBSURFACE
   PROCESS_MODELS
     SUBSURFACE_FLOW flow
       MODE TH
       OPTIONS
         MAX_PRESSURE_CHANGE 1.d8 #Pa
         MAX_TEMPERATURE_CHANGE 1.d0 #deg. C
       /
     /
     SUBSURFACE_TRANSPORT transport
       MODE GIRT
     /
     UFD_DECAY ufd_decay
     /
     WASTE_FORM wf_general
       TYPE GENERAL
     /
     UFD_BIOSPHERE bio
     /
   /
 END









