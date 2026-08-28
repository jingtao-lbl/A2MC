Back to :ref:`card-index`

.. _saturation-function-card:

SATURATION_FUNCTION
===================
Specifies the permeability function, saturation function, and parameters to be 
associated with a material property. This card is only for TH(ice) or MPHASE/FLASH2 modes.
In GENERAL, RICHARDS TH, and WIPP_FLOW modes, use the :ref:`characteristic-curves-card` card.

Required Cards:
---------------
SATURATION_FUNCTION <string>
  Opens the SATURATION_FUNCTION block, where <string> indicates the name by 
  which this saturation function may be identified and/or linked.

SATURATION_FUNCTION_TYPE <string>
 Indicates which saturation function is used. The options include: 
 VAN_GENUCTHEN, BROOKS_COREY, or THOMEER_COREY.
 
 Required cards specific to each SATURATION_FUNCTION_TYPE:
  * VAN_GENUCHTEN:
     + ALPHA <float>
        The van Genuchten \alpha parameter [Pa\ :sup:`-1`\].
     + LAMBDA <float>
        The van Genuchten m parameter, as in (m = 1-1/n) [-].
     + [Documented in Theory Guide under :ref:`VG-saturation-function-richards`]
  * BROOKS_COREY:
     + ALPHA <float>
        The Brooks-Corey \alpha parameter [Pa\ :sup:`-1`\].
     + LAMBDA <float>
        The Brooks-Corey \lambda parameter [-].
     + [Documented in Theory Guide under :ref:`BC-saturation-function-richards`]
  * THOMEER_COREY
     + ALPHA <float>
        The Thomeer-Corey \alpha parameter [Pa\ :sup:`-1`\].
     + LAMBDA <float>
        The Thomer-Corey m parameter [-].


PERMEABILITY_FUNCTION_TYPE <string>
 Indicates which permeability function is used. Options include: BURDINE, or 
 MUALEM. The :ref:`relative-permeability-functions-richards` section in the 
 Theory Guide documents these options based on van Genuchten and Brooks-Corey 
 saturation functions.

RESIDUAL_SATURATION <float>
 Indicates the fluid residual saturation [-].


Optional Cards:
---------------
BETAC <float>
 Placeholder. Currently not used.

MAX_CAPILLARY_PRESSURE <float>
 Cut off for maximum capillary pressure [Pa].  **Currently supported in the** 
 **C02 modes only.**

POWER <float>
 Placeholder. Currently not used.

Examples
--------
 ::

  SATURATION_FUNCTION sf1
    SATURATION_FUNCTION_TYPE VAN_GENUCHTEN
    PERMEABILITY_FUNCTION_TYPE BURDINE
    RESIDUAL_SATURATION 0.16d0
    LAMBDA 0.3391d0
    ALPHA 7.2727d-4
  /

  SATURATION_FUNCTION sf2
    SATURATION_FUNCTION_TYPE BROOKS_COREY
    PERMEABILITY_FUNCTION_TYPE BURDINE
    RESIDUAL_SATURATION 0.1299d0
    LAMBDA 0.7479d0
    ALPHA 1.10d-5
  /
  
  SATURATION_FUNCTION sf3
    SATURATION_FUNCTION_TYPE VAN_GENUCHTEN
    PERMEABILITY_FUNCTION_TYPE MUALEM
    RESIDUAL_SATURATION 0.16d0
    LAMBDA 0.3391d0
    ALPHA 7.2727d-4
  /
