.. _creating-an-input-deck-file:

Creating an Input File
======================

Units
-----

Unless otherwise specified, the default units for parameters given in the 
input deck are assumed to be:

* Pressure: Pascal [Pa] (absolute)
* Temperature: Celcius [C]
* Distance: meter [m]
* Volume: meter\ :sup:`3` \ [m\ :sup:`3`\ ]
* Time: second [s]
* Velocity: meters/second [m/s]
* Concentration: molarity [M] or molality [m] if MOLAL keyword used in 
  :ref:`chemistry-card`
* Enthalpy: kilojoules/mole [KJ/mol]
* Mass: kilograms [kg]
* Rate: mass/time [kg/s] or volume/time [m\ :sup:`3`\ /s]
* Rock density: kilograms/meter\ :sup:`3` \ [kg/m\ :sup:`3`\ ]


Input Deck Specification
------------------------

PFLOTRAN input files are divided into blocks and sub-blocks based on the process 
models employed. All input files must have the :ref:`simulation-card` block. 
Within the :ref:`simulation-card` block, the simulation type and the process
models employed are specified, as well as other essential capabilities
that are desired (like checkpointing, restarting, etc). Following the
:ref:`simulation-card` block, additional blocks required for the simulation 
type and process models are defined. For convenience, the :ref:`simulation-card` 
block is typically located at the top, but this is not required. 


Example Input Decks
-------------------

:ref:`simple-flow-problem`: An input file that runs a simple, vertical 1D 
variably-saturated flow problem.

Additionally, you can browse the input deck files located within the regression 
test directory ``$PFLOTRAN_DIR/regression_tests``. 

The following shows an input file "skeleton:"

::

 SIMULATION
   SIMULATION_TYPE SUBSURFACE
   PROCESS_MODELS
     SUBSURFACE_FLOW flow
       ...
     /
     SUBSURFACE_TRANSPORT transport
       ...
     /
   /
   CHECKPOINT
     PERIODIC TIMESTEP 10
     TIMES y 10. 30. 45.
     FORMAT HDF5
   /
   RESTART restart.chk
 END      
  
 SUBSURFACE
 ...
 END_SUBSURFACE
