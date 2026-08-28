Back to :ref:`card-index`

Back to :ref:`chemistry-card`

.. _geochemical-database:

Geochemical Database
====================

*Note: Contributed by Luis Manuel*

Structure of the chemical database read by PFLOTRAN
---------------------------------------------------
All text is written between single quotes.
On the first line the temperature points are defined, e.g.:
::

'temperature points' 8 0. 25. 60. 100. 150. 200. 250. 300.

Then different sections follow where each section ends with a 'null', e.g.:
::

'null' 0 0 0

|
| Sections:
|  0 - primary species and colloids
|  1 - aq species
|  2 - gases
|  3 - minerals
|  4 - surface complexes

Structure of each section
-------------------------
Each section can contain many lines. Within every section, the lines contain the same fields.
The fields are separated by spaces.

0 - primary species and colloids fields:
........................................
 - name
 - a0 -- ion size parameter
 - Z -- charge
 - molarWeight

1 - secondary species fields:
.............................
 - name 
 - Number of species in aqueous complex 
 - For each species:
 
  -  species stoichiometry 
  -  species name 

 - For each temperature:

  -  logK 

 -  a0 
 -  Z 
 - molarWeight 

2 - gases fields:
.................
 - name
 - molar volume (cm\ :sup:`3`\/mol)
 - Number of aqueous species in secondary reaction
 - For each species:

  -  species stoichiometry 
  -  species name

 - For each temperature:

  -  gas logK

 - gas molar weight

3 - minerals fields:
....................
- name
- molar volume 
- Number of aqueous species in mineral reaction 
- For each species: 

 -  species stoichiometry 
 -  species name 

- For each temperature: 

 -  mineral logK 

- mineral molar weight 

4 - surface complexes:
......................
- name 
- Number of species in surface complexation reaction
- For each species:

 -  species stoichiometry
 -  species name
