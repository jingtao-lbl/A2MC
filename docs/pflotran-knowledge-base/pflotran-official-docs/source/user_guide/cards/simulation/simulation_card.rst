Back to :ref:`card-index`

.. _simulation-card:

SIMULATION
==========
Defines the simulation type.

Required Cards:
---------------

SIMULATION
 Opens the SIMULATION block.

SIMULATION_TYPE <string>
 Specifies the type of simulation. Options for <string> include: SUBSURFACE,
 GEOMECHANICS_SUBSURFACE.

PROCESS_MODELS
 Opens the PROCESS_MODELS block and lists the process models that are used in
 the simulation. PROCESS_MODEL options include:

 :ref:`subsurface-flow-card`

 :ref:`subsurface-transport-card`

 AUXILIARY

 GEOMECHANICS_SUBSURFACE

 UFD_BIOSPHERE

 UFD_DECAY

 WASTE_FORM

 WIPP_SOURCE_SINK

 :ref:`MATERIAL_TRANSFORM <material-transform-card>`

Optional Cards:
---------------

:ref:`checkpoint-card`
 Opens a block for specifying checkpointing options.
 
:ref:`restart-card`
 Opens a block for specifying restart options.
 
Examples
--------

::

  SIMULATION
    SIMULATION_TYPE SUBSURFACE
    PROCESS_MODELS
      SUBSURFACE_FLOW flow
	MODE GENERAL
      /
    /
  END

::
    
  SIMULATION
    SIMULATION_TYPE SUBSURFACE
    PROCESS_MODELS
      SUBSURFACE_TRANSPORT transport
        MODE GIRT
      /
    /
  END

::
  
  SIMULATION
    SIMULATION_TYPE SUBSURFACE
    PROCESS_MODELS
      SUBSURFACE_FLOW flow
	MODE GENERAL
      /
      SUBSURFACE_TRANSPORT transport
        MODE GIRT
      /
      AUXILIARY SALINITY
	SPECIES Tracer 58.442469d0
      /
    /
    CHECKPOINT
      PERIODIC TIMESTEP 10
    /
  END

::
  
  SIMULATION
    SIMULATION_TYPE SUBSURFACE
    PROCESS_MODELS
      SUBSURFACE_FLOW flow
	MODE TH
	OPTIONS
	  MAX_PRESSURE_CHANGE 1.e5
	  MAX_TEMPERATURE_CHANGE 5.
	/
      /
    /
  END

::

  SIMULATION
    SIMULATION_TYPE GEOMECHANICS_SUBSURFACE
    PROCESS_MODELS
      SUBSURFACE_FLOW flow
        MODE RICHARDS
      /
      GEOMECHANICS_SUBSURFACE geomech
    /
  END

::

  SIMULATION
    SIMULATION_TYPE SUBSURFACE
    PROCESS_MODELS
      SUBSURFACE_FLOW flow
        MODE WIPP_FLOW
        OPTIONS
          EXTERNAL_FILE ../../block_options.txt
        /
      /
      SUBSURFACE_TRANSPORT transport
        MODE NWT
      /
    /
  END
