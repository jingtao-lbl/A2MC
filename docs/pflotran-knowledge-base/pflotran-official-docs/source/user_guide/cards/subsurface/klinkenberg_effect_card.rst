Back to :ref:`card-index`

.. _klinkenberg-effect-card:

KLINKENBERG_EFFECT
=====================
Introduces a permeability correction factor 
into the gas transport equation to account for the Klinkenberg effect. 
In flow tests, at low pressures and especially at low permeabilities, the 
observed permeability to gas is larger than the permeability to liquid 
(which is the input "intrinsic" permeability).  This phenomena is 
due to slippage (i.e. non-zero fluid velocity) along the surface of the 
pore walls inside the porous medium, which can occur for the gas phase
but not the liquid phase(s).

The correction factor is modeled as (1 + b * k\ :sup:`a` / P\ :sub:`g`)


Required Cards:
---------------

KLINKENBERG_EFFECT
 Opens the KLINKENBERG_EFFECT block.  Must have a closing END statement.

A <double>
 Exponent for the (instrinsic, i.e. liquid-phase) permeability.

B <double>
 Constant that controls the pressure asymptote. 


Example:
--------- 

 ::
 
  KLINKENBERG_EFFECT
    A -0.33d0  ! exponent
    B  0.98d0  ! constant
  END

