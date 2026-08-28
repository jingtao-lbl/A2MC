.. _pm_wipp_source_sink:

The WIPP Source Sink Process Model
==================================

The WIPP Source Sink Process Model (WSSPM) determines gas and brine generation 
in the waste areas. It has been developed by Jennifer Frederick (Sandia National
Laboratories - SNL), under the guidance of Brad Day (SNL), Todd Zeitler (SNL),
and Glenn Hammond (SNL).

General Algorithmic Design
--------------------------

The WSSPM consists of several defined ``waste panel`` and ``inventory`` objects. 
Each ``waste panel`` object consists of a ``region`` object that defines the
location of the waste panel, and a pointer to an ``inventory`` object. The
``waste panel`` object then creates its own inventory where it keeps track of
several chemical species and chemical equation rate constants. Each 
``waste panel`` determines gas and brine generation rates according to a 
function of the chemical equation rate constants and stoichiometric constants in
each chemical equation involving gas or brine.

The process model is called at each Newton iteration, using the current iterate's
unperturbed and perturbed values for the liquid saturation to
calculate the rate constants which determine gas and brine generation rates. 
When the process model is called, the rate constants are determined according to 
the remaining amounts of limiting chemical species in the relevant chemical 
equation. The gas and brine generation rates (which are a function of the rate 
constants and the stoichiometric constants) are used in the current iteration
and are assigned in the governing equations for fluid mass conservation. 

At the next time step, the chemical equation rate constants are used to update 
the inventory of remaining chemical species. Rate smoothing and tapering
performed in the previous time step ensures that chemical species amounts do
not go negative (e.g. overstep the update). The algorithm then starts over
again and calculates the rate constants according to the updated inventory.

The following sections document the WSSPM algorithms in detail:

Effective Brine Saturation
--------------------------

The effective brine saturation, :math:`s_{eff}`, is obtained from the actual
brine saturation, :math:`s`, according to:

.. math::
   :label:
   
   \saturation_{eff} = \saturation - \saturation_{min} + \left({s_{wick}\left({1.0 - e^{\alpha B}}\right)}\right)
   
   B = 200\left({max(s-s_{min},0)}\right)^{2}
   
where :math:`s_{min}` is a chemistry cutoff brine saturation parameter below 
which chemistry does not occur (specified by ``SOCMIN`` in the input deck), 
:math:`s_{wick}` is a wicking saturation for brine (specified by ``SAT_WICK``
in the input deck), and :math:`\alpha` is a unitless rate smoothing parameter 
(specified by ``ALPHARXN`` in the input deck).
   
Furthermore, the value of :math:`s_{eff}` is constrained to a value between 0 
and 1 with the following conditionals:

.. math::
   :label:
   
   \saturation_{eff} = min(s_{eff},1)
   
   \saturation_{eff} = max(s_{eff},0)
   
The conditionals are important because when :math:`s_{wick} > 0` it is possible 
for :math:`s_{eff}` to be larger than unity, which is not physical.

Anoxic Iron Corrosion Reaction
------------------------------

Iron corrosion is modeled by

.. math::
   :label: iron_corrosion
   
   Fe + 2H_{2}O = Fe(OH)_{2} + H_{2}
   
For every mole of :math:`Fe` consumed, 2 moles of brine are consumed, one mole 
of :math:`Fe(OH)_{2}` is produced, and one mole of :math:`H_{2}` is produced. 
The reaction rate constant for anoxic iron corrosion, :math:`K_{c}`, is 
calculated according to:

.. math::
   :label:
   
   K_{c} = \left({R_{CI}s_{eff} + R_{CH}\left({1-s_{eff}}\right)}\right)
   
.. math::
   :label:
   
   R_{CI} = \frac {r_{CI} D_{s} \density_{Fe}} {W_{Fe}}
   
.. math::
   :label:
   
   R_{CH} = \frac {r_{CH} D_{s} \density_{Fe}} {W_{Fe}}
   
where :math:`r_{CI}` is the inundated corrosion rate in [m/s] (specified by 
``CORRMCO2`` in the input deck), :math:`r_{CH}` is the humid corrosion rate in 
[m/s] (specified by ``HUMCORR`` in the input deck), :math:`D_s` is the
available iron surface area concentration in [m2/m3], :math:`\density_{Fe}` is
the density of iron in [kg/m3], and :math:`W_{Fe}` is the molecular weight of
iron in [kg/mol]. The resulting units for the reaction rate
:math:`K_{c}` are [mol-Fe/m3/s]. The value for :math:`D_s` is calculated as

.. math::
   :label:
   
   D_s = D_{sa} D_{conc}
   
where :math:`D_{sa}` is the iron drum surface area in [m2] (specified by
``ASDRUM`` in the input deck), and :math:`D_{conc}` is the iron drum
concentration in the waste panel in [1/m3] (specied by ``DRMCONC`` in the input
deck). The parameter ``DRMCONC`` should be equivalent to BRAGFLO's ratio
``DRROOM/VROOM``.


The instantaneous rates for each chemical species for anoxic iron corrosion are 
shown in the table below. Positive rates indicate a source while negative rates 
indicate a sink. The default value for the stoichiometric matrix is also shown.

+----------+---------------+--------------+------------------+
| species  | rate          | STCO_##      | units            |
+==========+===============+==============+==================+
| Fe       | :math:`-K_c`  | STCO_13 = -1 | mol-Fe/m3/s      |
+----------+---------------+--------------+------------------+
| H2O      | :math:`-2K_c` | STCO_12 = -2 | mol-H2O/m3/s     |
+----------+---------------+--------------+------------------+
| Fe(OH)2  | :math:`+K_c`  | STCO_15 = +1 | mol-Fe(OH)2/m3/s |
+----------+---------------+--------------+------------------+
| H2       | :math:`+K_c`  | STCO_11 = +1 | mol-H2/m3/s      |
+----------+---------------+--------------+------------------+

The initial amount of iron in an inventory is specified under the ``INVENTORY``
block with the following parameters: ``IRONCHW``, ``IRONRHW``, ``IRNCCHW``,
``IRNCRHW``. The total amount of iron in the inventory is the sum of these
parameters.

Biodegradation Reactions of Cellulosics, Plastics, and Rubbers
--------------------------------------------------------------

Biodegradation reactions are modeled using a lumped approach:

.. math::
   :label: biodegradation_lumped
   
   \frac {1}{6} C_{6}H_{10}O_{5} = X_m(H_2|C) H_{2} + X_m(H_2O|C) H_{2}O
   
This lumped model is derived from the two dominant reactions:

.. math::
   :label: denitrification
   
   C_{6}H_{10}O_{5} + 4.8H^{+} + 4.8NO_{3}^{-} = 7.4H_{2}O + 6CO_{2} + 2.4N_{2}
   
.. math::
   :label: sulfate_reduction
   
   C_{6}H_{10}O_{5} + 6H^{+} + 3SO_{4}^{2-} = 5H_{2}O + 6CO_{2} + 3H_{2}S
   
where Eq. :eq:`denitrification` represents denitrification, and Eq. 
:eq:`sulfate_reduction` represents sulfate reduction. Methanogenesis is not
included. The formula :math:`C_{6}H_{10}O_{5}` represents biodegradable 
materials, which can consist of cellulosics, rubbers, and plastics.

The reaction rates for biodegradation is calculated as

.. math::
   :label:
   
   K_{b} = \left({R_{BI}s_{eff} + R_{BH}\left({1-s_{eff}}\right)}\right)
   
.. math::
   :label:
   
   R_{BI} = \chi_b r_{BI} D_{c} P_{bio} 
   
.. math::
   :label:
   
   R_{BH} = \chi_b r_{BH} D_{c} P_{bio}
   
where :math:`r_{BI}` is the inundated biodegradation rate in 
[mol-cellulosics/kg-cellulosics/s] (specified by ``GRATMICI`` in the input deck), 
:math:`r_{BH}` is the humid biodegradation rate in [mol-cellulosics/kg-cellulosics/s]
(specified by ``GRATMICH`` in the input deck), :math:`D_{c}` is the initial mass
concentration of biodegradables in the waste panel in [kg-cellulosics/m3], :math:`P_{bio}`
is a unitless probability parameter of attaining sampled microbial gas
generation rates (specified by ``BIOGENFC`` in the input deck), and :math:`\chi_b`
is a flag which is set to 0 or 1 depending on whether biodegradation is
included in the simulation (as controlled by ``PROBDEG`` in the input deck).
The resulting units for the reaction rate :math:`K_{b}` are 
[mol-cellulosics/m3/s]. The value for :math:`D_c` is calculated as

.. math::
   :label:
   
   D_{c} = \frac {M_{C_{6}H_{10}O_{5}}} {V}
   
where :math:`V` is the waste panel volume (internally calculated according to
the ``region`` object), and :math:`M_{C_{6}H_{10}O_{5}}` is the total initial 
mass of biodegradables in the waste panel. The total initial mass of
biodegradables is calculated as a function of input deck parameters according 
to

.. math::
   :label:
   
   M_{C_{6}H_{10}O_{5}} = M_{cellulosics} + \chi_{rp} \left(M_{rubbers} + \beta M_{plastics}\right)
   
where :math:`\beta` is the unitless mass ratio of plastics to equivalent
carbon in the waste panel (specified by ``PLASFAC`` in the input deck),
:math:`\chi_{rp}` is a flag which is set to 0 or 1 depending on whether 
rubbers and plastics are included in the simulation (as controlled by 
``PROBDEG`` in the input deck),
:math:`M_{cellulosics}` is the sum of input deck parameters ``CELLCHW``, 
``CELLRHW``, ``CELCCHW``, ``CELCRHW``, ``CELECHW``, ``CELERHW``, 
:math:`M_{rubbers}` is the sum of input deck parameters ``RUBBCHW``, 
``RUBBRHW``, ``RUBCCHW``, ``RUBCRHW``, ``RUBECHW``, ``RUBERHW``, and 
:math:`M_{plastics}` is the sum of input deck parameters ``PLASCHW``, 
``PLASRHW``, ``PLSCCHW``, ``PLSCRHW``, ``PLSECHW``, and ``PLSERHW``.

A summary of the logic about ``PROBDEG`` is summarized in the follow table:

+----------------+---------------------------+-----------------------+
| PROBDEG value  | Meaning                   | Flag value            |
+================+===========================+=======================+
|  0             | No biodegradation occurs  | :math:`\chi_{b} = 0`; |
|                |                           | :math:`\chi_{rp} = 0` |
+----------------+---------------------------+-----------------------+
|  1             | Biodegradation occurs     | :math:`\chi_{b} = 1`; |
|                | for cellulosics only      | :math:`\chi_{rp} = 0` |
+----------------+---------------------------+-----------------------+
|  2             | Biodegradation occurs     | :math:`\chi_{b} = 1`; |
|                | for all materials         | :math:`\chi_{rp} = 1` |
+----------------+---------------------------+-----------------------+

   
The instantaneous rates for each chemical species for biodegradation in Eq. :eq:`biodegradation_lumped` are 
calculated by assuming an average (and lumped) stoichiometry for the 
denitrification (Eq. :eq:`denitrification`) and sulfate reduction (:eq:`sulfate_reduction`) reactions. 

:math:`N_{2}` and :math:`H_{2}S` are lumped and treated as :math:`H_{2}`. 
:math:`CO_{2}` is not tracked 
because it is assumed to be entirely consumed in carbonation processes with magnesium
materials in the repository. Nitrate and sulfate are also not tracked 
since they are assumed to be plentiful, however, the initial amount of nitrate
and sulfate are used to calculate the stoichiometry coefficient for gas and
brine production as follows:

.. math::
   :label: F_factors
   
   X_m(H_2|C) = \frac{2.4}{6}F_{NO3} + \frac{3}{6}F_{SO4}
   
   X_m(H_2O|C) = \frac{7.4}{6}F_{NO3} + \frac{5}{6}F_{SO4}
   
   
where :math:`F_{NO3}` is the fraction of carbon consumed through the 
denitrification reaction and :math:`F_{SO4}` is the fraction of carbon consumed 
by sulfate reduction. The calculation of :math:`F_{NO3}` and :math:`F_{SO4}` is shown below:

 ::
 
   A1 = TOTMOLBIO
   A2 = GRATMICI * TOTKGBIO * SECPERYER * 10000.d0
   MAX_C = min(A1,A2)
   F_NO3 = MOL_NO3 * (6.d0/4.8d0) / MAX_C
   F_NO3 = min(F_NO3,1.d0)
   F_SO4 = 1.d0 - F_NO3
   
where ``TOTMOLBIO`` is the total moles of biodegradables in the waste panel,
``TOTKGBIO`` is the total mass of biodegradables in the waste panel,
``SECPERYEAR`` is a conversion factor that converts from seconds to years,
and the value of 10,000 represents the WIPP safety period (years). 

The instantaneous rates for each chemical species for biodegradation 
are shown in the table below. Positive rates indicate a source while negative 
rates indicate a sink.  The default value for the stoichiometric matrix is also 
shown. Note that :math:`H_2` gas is produced during this reaction even though
it is not a reactant in the chemical equations. This is due to the treatment 
of :math:`N_2` and :math:`H_2S` gases as :math:`H_2` gas.
   
+--------------------------+------------------------+---------------------+-------------------------+---------------+
| species                  | rate                   | STCO_##             | units                   | notes         |
+==========================+========================+=====================+=========================+===============+
| :math:`C_{6}H_{10}O_{5}` | :math:`-K_b`           | STCO_24 = -1        | mol-biodegradables/m3/s |               |
+--------------------------+------------------------+---------------------+-------------------------+---------------+
| :math:`H^{+}`            | n/a                    | n/a                 | n/a                     | not tracked   |
+--------------------------+------------------------+---------------------+-------------------------+---------------+
| :math:`NO_3^-`           | n/a                    | n/a                 | n/a                     | not tracked   |
+--------------------------+------------------------+---------------------+-------------------------+---------------+
| :math:`SO_4^{2-}`        | n/a                    | n/a                 | n/a                     | not tracked   |
+--------------------------+------------------------+---------------------+-------------------------+---------------+
| :math:`H_{2}O`           | :math:`K_bX_m(H_2O|C)` | :math:`X_m(H_2O|C)` | mol-H2O/m3/s            |               |
+--------------------------+------------------------+---------------------+-------------------------+---------------+
| :math:`CO_{2}`           | n/a                    | n/a                 | n/a                     | not tracked   |
+--------------------------+------------------------+---------------------+-------------------------+---------------+
| :math:`N_{2}`            | n/a                    | n/a                 | n/a                     | lumped as H2  |
+--------------------------+------------------------+---------------------+-------------------------+---------------+
| :math:`H_{2}S`           | n/a                    | n/a                 | n/a                     | lumped as H2  |
+--------------------------+------------------------+---------------------+-------------------------+---------------+
| :math:`H_2`              | :math:`K_bX_m(H_2|C)`  | :math:`X_m(H_2|C)`  | mol-H2/m3/s             |               |
+--------------------------+------------------------+---------------------+-------------------------+---------------+
   
The initial amount of nitrate and sulfate in an inventory is specified under 
the ``INVENTORY`` block with the following parameters: ``NITRATE``, ``SULFATE``.

Iron Sulfidation Reaction
-------------------------

Iron sulfidation reactions are modeled as

.. math::
   :label: iron_corrosion_sulfidation
   
   Fe(OH)_{2} + H_{2}S = FeS + 2H_{2}0
   
and

.. math::
   :label: iron_sulfidation
   
   Fe + H_{2}S = FeS + H_{2}
   
where Eq. :eq:`iron_corrosion_sulfidation` represents sulfidation of iron hydroxide (a corrosion product), 
and Eq. :eq:`iron_sulfidation` represents sulfidation of iron.

The reaction rate is calculated as

.. math::
   :label:
   
   K_{s} = X_m(H_2S|C) K_b
   
where :math:`K_{b}` is the biodegradation rate (the rate-limiting step which generates H2S), 
and :math:`X_m(H_2S|C)` is the ratio of moles H2S produced per mole of cellulosics consumed. 
This is the parameter ``RXH2S`` in the BRAGFLO v6.02 User's Manual. 
Currently the value of :math:`X_m(H_2|C)` (SMIC_H2) used for :math:`X_m(H_2S|C)` in PA calculations.

The rate constant :math:`K_{s}` is split into 
:math:`K_{s}^{c}`, representing sulfidation of the corrosion products of iron (Fe(OH)2) 
(rate for Eq. :eq:`iron_corrosion_sulfidation`), and 
:math:`K_{s}^{i}`, representing sulfidation of metallic iron (rate for Eq. :eq:`iron_sulfidation`). 
Fe(OH)2 sulfidation kinetically dominates Fe sulfidation. 
This is modeled by first determining the available Fe(OH)2 .  If Fe(OH)2 is available in 
excess of H2S generation during a given time step, then :math:`K_{s}` is entirely portioned to 
:math:`-K_s^c`, and :math:`-K_s^i` is zero.
If there is not enough Fe(OH)2 available to react with all of the H2S generated during a timestep, 
then :math:`K_{s}` is first portioned to :math:`-K_s^c` according to available Fe(OH)2, then the 
remaining :math:`K_{s}` is portioned to :math:`-K_s^i`.

The instantaneous rates for each chemical species for iron sulfidation are 
shown in the table below. Positive rates indicate a source while negative rates 
indicate a sink. The default value for the stoichiometric 
matrix is also shown. Note that :math:`H_2S` is not tracked.

+----------+--------------------------+--------------+------------------+-------------+
| species  | rate                     | STCO_##      | units            | notes       |
+==========+==========================+==============+==================+=============+
| Fe       | :math:`-K_s^i`           | STCO_43 = -1 | mol-Fe/m3/s      |             |
+----------+--------------------------+--------------+------------------+-------------+
| Fe(OH)2  | :math:`-K_s^c`           | STCO_35 = -1 | mol-Fe(OH)2/m3/s |             |
+----------+--------------------------+--------------+------------------+-------------+
| H2S      | n/a                      | n/a          | n/a              | not tracked |
+----------+--------------------------+--------------+------------------+-------------+
| FeS      | :math:`+K_s^i`           | STCO_36 = +1 | mol-H2/m3/s      |             |
|          | :math:`+K_s^c`           | STCO_46 = +1 |                  |             |
+----------+--------------------------+--------------+------------------+-------------+
| H2       | :math:`+K_s^i`           | STCO_31 = -1 | mol-H2/m3/s      |             |
|          | :math:`+K_s^c`           | STCO_41 =  0 | mol-H2/m3/s      |             |
+----------+--------------------------+--------------+------------------+-------------+
| H2O      | :math:`+2K_s^c`          | STCO_32 = +2 | mol-H2O/m3/s     |             |
+----------+--------------------------+--------------+------------------+-------------+

MgO Hydration Reaction
----------------------

MgO hydration to brucite is modeled by

.. math::
   :label: mgo_hydration
   
   MgO + H_{2}O = Mg(OH)_{2}
   
For every mole of MgO consumed, one mole of brine is consumed and one mole of 
brucite is produced. The reaction rate constant for for MgO hydration to
brucite, :math:`K_{m}`, is calculated according to:

.. math::
   :label:
   
   K_{m} = \left({R_{MI}s_{eff} + R_{MH}\left({1-s_{eff}}\right)}\right)
   
.. math::
   :label:
   
   R_{MI} = max(r_{MI},r_{MH}) D_{m}
   
.. math::
   :label:
   
   R_{MH} = r_{MH} D_{m}
   
where :math:`r_{MI}` is the inundated brucite rate in [mol-brucite/kg-MgO/s] 
(specified by ``BRUCITES`` or ``BRUCITEC`` in the input deck depending on
deep brine intrusion), :math:`r_{MH}` is the humid brucite rate in
[mol-brucite/kg-MgO/s] (specified by ``BRUCITEH`` in the input deck), and 
:math:`D_{m}` is the initial mass concentration of MgO. The value for 
:math:`D_{m}` is calculated according to

.. math::
   :label:
   
   D_{m} = \frac {M_{biodegradables} W_{MgO} X} {V W_{biodegradables}}
   
where :math:`V` is the volume of the waste panel in [m3], 
:math:`M_{biodegradables}` is the total initial mass of biodegradables in [kg],
:math:`W_{biodegradables}` is the average molecular weight of the 
biodegradables in [kg/mol], :math:`W_{MgO}` is the molecular weight of MgO, and
:math:`X` is a unitless MgO excess factor which is the ratio of moles of MgO 
to moles of organic carbon in the waste panel (specified by ``MGO_EF`` in the 
input deck). This amount of MgO is chosen because it should be a sufficient 
amount of MgO to remove CO2 produced during biodegradation reactions via the 
product brucite.

The instantaneous rates for each chemical species for MgO hydration to brucite 
are shown in the table below. Positive rates indicate a source while negative 
rates indicate a sink. The default value for the stoichiometric matrix is also 
shown.

+----------+---------------+--------------+------------------+
| species  | rate          | STCO_##      | units            |
+==========+===============+==============+==================+
| MgO      | :math:`-K_m`  | STCO_57 = -1 | mol-MgO/m3/s     |
+----------+---------------+--------------+------------------+
| H2O      | :math:`-K_m`  | STCO_52 = -1 | mol-H2O/m3/s     |
+----------+---------------+--------------+------------------+
| Mg(OH)2  | :math:`+K_m`  | STCO_58 = +1 | mol-Mg(OH)2/m3/s |
+----------+---------------+--------------+------------------+
   

Brucite and MgO Carbonation
----------------------------------------------

Brucite carbonation to hydromagnesite is modeled by

.. math::
   :label: brucite_carbonation
   
   5Mg(OH)_{2} + 4CO_{2} = Mg_{5}(CO_{3})_{4}:4H_{2}O
   
MgO carbonation to magnesite is modeled by

.. math::
   :label: mgo_carbonation
   
   MgO + CO_{2} = Mg(CO_{3})
   
These two reactions are modeled in a similar fashion to the iron hydroxide and iron 
sulfidation reactions.  CO2, generated from the biodegradation reaction,  is assumed 
to be the limiting reactant.  The CO2 generation rate is given by

.. math::
   :label:
   
   K_{h} = X_m(CO_2|C) K_b
   
where :math:`X_m(CO_2|C) = 1` is the ratio of moles of CO2 produced per mole of carbon
generated by the biodegradation reactions, and :math:`K_{b}` is the biodegradation rate.
 
The rate constant :math:`K_{h}` is then split between the brucite carbonation reaction, 
:math:`K_{h, brucite}` and the MgO carbonation reaction, :math:`K_{h, MgO}`.  
Brucite carbonation is assumed to kinetically dominate MgO carbonation. 
If the amount of brucite available to react during a timestep is in excess of the CO2 generated, 
then :math:`K_{h}` is entirely portioned to :math:`K_{h, brucite}`, and :math:`K_{h, MgO}` is zero.
If the amount of brucite available to react during a timestep is less than the CO2 generated, 
then :math:`K_{h}` is portioned to :math:`K_{h, brucite}` such that all of the available brucite is consumed, 
then the remaining fraction of :math:`K_{h}` is portioned to :math:`K_{h, MgO}`.

The instantaneous rates for each chemical species for brucite carbonation and MgO carbonation 
are shown in the tables below. Positive rates indicate a source 
while negative rates indicate a sink. The default value for the stoichiometric 
matrix is also shown.

+----------------+-------------------------------+-----------------+------------------+--------------+
| species        | rate                          | STCO_##         | units            | notes        |
+================+===============================+=================+==================+==============+
| Mg(OH)2        | :math:`K_{h, brucite}`        | STCO_68 = -1.25 | mol-Mg(OH)2/m3/s |              |
+----------------+-------------------------------+-----------------+------------------+--------------+
| CO2            | n/a                           | n/a             | n/a              | not tracked  |
+----------------+-------------------------------+-----------------+------------------+--------------+
| Hydromagnesite | :math:`K_{h, brucite}`        | STCO_60 = +0.25 | mol-hymag/m3/s   |              |
+----------------+-------------------------------+-----------------+------------------+--------------+

+----------------+-------------------------------+-----------------+------------------+--------------+
| species        | rate                          | STCO_##         | units            | notes        |
+================+===============================+=================+==================+==============+
| MgO            | :math:`K_{h, MgO}`            | STCO_77 = -1    | mol-MgO/m3/s     |              |
+----------------+-------------------------------+-----------------+------------------+--------------+
| CO2            | n/a                           | n/a             | n/a              | not tracked  |
+----------------+-------------------------------+-----------------+------------------+--------------+
| Magnesite      | :math:`K_{h, MgO}`            | STCO_79 = +1    | mol-MgCO3/m3/s   |              |
+----------------+-------------------------------+-----------------+------------------+--------------+


Hydromagnesite Dehydration Reaction
-----------------------------------

Hydromagnesite is not considered thermodynamically stable under repository
conditions, and is expected to dehydrate to form magnesite, producing brine, as
modeled by

.. math::
   :label: hymagcon
   
   Mg_{5}(CO_{3})_{4}:4H_{2}O = 4MgCO_{3} + Mg(OH)_{2} + 4H_{2}O
   
The reaction rate constant for hydromagnesite dehydration, :math:`K_{y}`, is
calculated according to:

.. math::
   :label:
   
   K_{y} = R_{hymagcon} C_{hymag}
   
where :math:`R_{hymagcon}` is the hydromagnesite conversion rate in 
[mol-hydromagnesite/kg-hydromagnesite/s] (specified by ``HYMAGCON`` in the input deck), and 
:math:`C_{hymag}` is the current mass concentration of hydromagnesite in the waste 
panel (calculated internally). The units of :math:`K_{y}` are 
[mol-hydromagnesite/m3/s].

The instantaneous rates for each chemical species for hydromagnesite dehydration 
are shown in the table below. Positive rates indicate a source while negative 
rates indicate a sink. The default value for the stoichiometric 
matrix is also shown.

+----------------+---------------+--------------+------------------+
| species        | rate          | STCO_##      | units            |
+================+===============+==============+==================+
| Hydromagensite | :math:`-K_y`  | STCO_80 = -1 | mol-hymag/m3/s   |
+----------------+---------------+--------------+------------------+
| MgCO3          | :math:`+4K_y` | STCO_89 = +4 | mol-MgCO3/m3/s   |
+----------------+---------------+--------------+------------------+
| Mg(OH)2        | :math:`+K_y`  | STCO_88 = +1 | mol-Mg(OH)2/m3/s |
+----------------+---------------+--------------+------------------+
| H2O            | :math:`+4K_y` | STCO_82 = +4 | mol-H2O/m3/s     |
+----------------+---------------+--------------+------------------+

Gas Generation Rate
-------------------

The gas generation rate is calculated by summing the hydrogen and nitrogen rates
from each of the modeled reactions. The following reactions produce or consume H2 gas:

+-----------------------+-----------------------+--------------------+-------------+
| reaction              | rate                  | STCO_##            | units       | 
+=======================+=======================+====================+=============+
| anoxic iron corrosion | :math:`+K_c`          | STCO_11 = +1       | mol-H2/m3/s |      
+-----------------------+-----------------------+--------------------+-------------+
| biodegradation        | :math:`K_b X_m(H_2|C)`| :math:`X_m(H_2|C)` | mol-H2/m3/s |       
+-----------------------+-----------------------+--------------------+-------------+
| FeOH sulfidation      | :math:`+K_s^c`        | STCO_41 = -1       | mol-H2/m3/s |        
+-----------------------+-----------------------+--------------------+-------------+

The hydrogen gas generation rate is the sum of the "rate" column in the table
above,

.. math::
   :label: gas_generation
   
   R_{gas} = K_c + K_bX_m(H_2|C) + K_s^c
   
This rate is assigned as a gas source term in the governing equations for fluid
flow (see :ref:`mode-general`).

Brine Generation Rate
---------------------

The brine generation rate is calculated by summing the H2O rates
from each of the modeled reactions. The following reactions produce brine:

+-----------------------+------------------------+---------------------+--------------+
| reaction              | rate                   | STCO_##             | units        | 
+=======================+========================+=====================+==============+
| anoxic iron corrosion | :math:`-2K_c`          | STCO_12 = -2        | mol-H2O/m3/s |        
+-----------------------+------------------------+---------------------+--------------+
| biodegradation        | :math:`K_b X_m(H_2O|C)`| :math:`X_m(H_2O|C)` | mol-H2O/m3/s | 
+-----------------------+------------------------+---------------------+--------------+
| iron sulfidation      | :math:`+2K_s^c`        | STCO_32 = +2        | mol-H2O/m3/s |         
+-----------------------+------------------------+---------------------+--------------+
| MgO hydration         | :math:`-K_m`           | STCO_52 = -1        | mol-H2O/m3/s |         
+-----------------------+------------------------+---------------------+--------------+
| Hymag dehydration     | :math:`+4K_y`          | STCO_82 = +4        | mol-H2O/m3/s |         
+-----------------------+------------------------+---------------------+--------------+

The brine generation rate is the sum of the "rate" column in the table
above,

.. math::
   :label: water_generation
   
   R_{H2O} = -2 K_c + K_bX_m(H_2O|C) + 5 K_b^s + 2 K_s^c - K_m + 4 K_y
   
This rate is assigned as a liquid source term in the governing equations for 
fluid flow (see :ref:`mode-general`) after taking into account the weight of
salt:

.. math::
   :label: brine_generation
   
   R_{brine} = R_{H2O} / (1 - 0.01S)
   
where :math:`S` is the salt weight percent as indicated by ``SALT_PERCENT``.

Reaction Rate Smoothing and Tapering
------------------------------------

Prior to using the calculated rate constants from each model reaction, the rates
are smoothed and tapered. The main purpose of smoothing and tapering the 
reaction rate constants is to avoid running out of a reactant during the 
duration of the current timestep when the remaining inventory is updated. Rate 
smoothing is implemented according to

.. math::
   :label:
   
   K_{smoothed} = K \left({1 - e^{\left({\alpha \frac{C}{C_i}}\right)}}\right)
   
The smoothed rate is a function of the raw calculated rate, :math:`K`, and the
ratio of the current concentration of a relevant species to its initial 
concentration in the waste panel. The parameter :math:`\alpha` is specified by
``ALPHARXN`` in the input deck. When the relevant species concentration relative
to it's initial concentration falls low, the reaction rate constant is decreased
so that it follows a smooth curve to zero. 
For each modeled reaction, the relevant species is typically the limiting 
species that appears on the left hand side of the chemical equation, as 
summarized in the following table:

+-----------------------+-------------------+
| reaction              | species for C/Ci  |
+=======================+===================+
| anoxic iron corrosion | Fe                |      
+-----------------------+-------------------+
| biodegradation        | C6H10O5           |
+-----------------------+-------------------+
| iron sulfidation      | Fe                |        
+-----------------------+-------------------+
| MgO hydration         | MgO               |   
+-----------------------+-------------------+
| brucite carbonation   | MgO               |
+-----------------------+-------------------+
| HM dehydration        | MgO               |       
+-----------------------+-------------------+

Immediately after smoothing, the smoothed reaction rate constant is additionally 
tapered (e.g. the rate is limited to the amount of the limiting reactant divided 
by the current timestep size). While the 
concept is similar to smoothing, the relevant species for tapering can be different for
each equation, especially when there are multiple equations per modeled reaction
(as is the case for biodegradation and iron sulfidation), and it is possible
for there to be more than one limiting species. The following table summarizes
the species which are used to taper each reaction rate:

+-----------------------+---------------------------+----------------------+
| reaction              | rate                      | species for tapering | 
+=======================+===========================+======================+
| anoxic iron corrosion | :math:`K_c`               | Fe                   |        
+-----------------------+---------------------------+----------------------+
| biodegradation        | :math:`K_b`               | C6H10O5              | 
+-----------------------+---------------------------+----------------------+
| Fe sulfidation        | :math:`K_s^i`             | Fe                   |  
+-----------------------+---------------------------+----------------------+
| Fe(OH)2 sulfidation   | :math:`K_s^c`             | Fe(OH)2              |        
+-----------------------+---------------------------+----------------------+
| MgO hydration         | :math:`K_m`               | MgO                  | 
+-----------------------+---------------------------+----------------------+
| brucite carbonation   | :math:`K_{h, brucite}`    | Mg(OH)2              |         
+-----------------------+---------------------------+----------------------+
| MgO carbonation       | :math:`K_{h, MgO}`        | MgO                  |         
+-----------------------+---------------------------+----------------------+
| HM dehydration        | :math:`K_y`               | hydromagnesite       |         
+-----------------------+---------------------------+----------------------+

Chemical Species Inventory Update
---------------------------------

At the beginning of each time step, each tracked chemical species is
updated using the reaction rate constant calculated at the end of the previous
time step and the length of the previous time step. 
The update is calculated according to

.. math::
   :label: update
   
   C_{t} = C_{t-1}  + \left( K_{t-1} dt \right)
   
where :math:`C_{t}` is the updated concentration for the current time step,
:math:`C_{t-1}` is the old concentration in the previous time step, 
:math:`K_{t-1}` is the rate constant calculated in the previous time step, and
:math:`dt` is the length of the previous time step. 



 
