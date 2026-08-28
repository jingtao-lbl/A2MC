.. _wipp_waste_form:

The WIPP Waste Form and UFD Decay Process Models
================================================

The radionuclide waste inventory within a waste panel in the WIPP is modeled
in PFLOTRAN using the Waste Form Process Model with the UFD Decay Process
Model. The Waste Form Process Model is 
:ref:`formally documented here<pm_waste_form>`, and is responsible for 
calculating the radionuclide decay and ingrowth in the solid waste form bulk
and the resulting source term to the surround environment upon breach. The
UFD Decay Process Model is :ref:`formally documented here<pm_ufd_decay>`
and is responsible for decay and ingrowth of the radionuclides that are
released into the surrounding environment, as well as phase partitioning
of the radionuclides into aqueous, sorbed, and precipitated phases, assuming
equilibrium. Both of these process models are peers of the Reactive Transport
Process Model. The WIPP PA user should be sufficiently familiar with how
these process models operate independently, in order to better understand
how these process models work together.

PFLOTRAN Process Model Work Flow
--------------------------------

At each time step in a PFLOTRAN simulation, process models are executed
according to a hierarchy that is structured upon peers and children.
Process models that are peers of each other execute and synchronize at
waypoints within the simulation (e.g., at the end of a time step, or at
output time intervals). In contrast, process models that are children of a
parent process model synchronize to their parent's time step (which may be 
different than the simulation time step size), taking as many steps as
neccessary to catch up with their parent's time step.

Both the Waste Form Process Model (WFPM) and the UFD Decay Process Model 
(UDPM) are peers of the Reactive Transport Process Model (RTPM). The RTPM
is a child of the Flow Process Model (FPM). For the peer relationship between
the RTPM, WFPM, and UDPM, the execution ordering is important. The RTPM is
executed first, the WFPM is executed second, and the UDPM is executed third.
For example, at the beginning of a time step, the FPM will step to t+dt. Next,
the RTPM will execute as the first child to calculate the new solute field 
at time t+dt, taking as many steps as neccessary to get to t+dt. Next, the 
WFPM will execute and update the solute field that the RTPM calculated for 
t+dt, or will calculate the source term for the next time step based on the 
updated solute field that the RTPM calculated for t+dt. Finally, the UDPM will 
execute and apply phase partitioning to the solute field that the RTPM has 
calculated and the WFPM has updated for time t+dt. The simulation then takes 
the next time step, repeating the procedure.

Code PANEL
----------

In a PFLOTRAN WIPP PA simulation, the ordering of the RTPM, WFPM, and UDPM 
mimick code PANEL. PANEL's PA role is to estimate the mobilized radioactive 
contaminant load in the brine phase of the brine/gas mixture that seeps or 
flows out of the repository's decommissioned waste panels. PANEL is responsible
for calculuating the radionuclide source term and decaying the radionuclides 
within the waste panel. PANEL plays no role in the physics of the fluid flow
in or near the repository.
 
To compute initial inventory, PANEL linearly scales the entire repository
inventory to each waste panel by a volume ratio. Because each of the eight
waste panels are the same size, the volume ratio is 0.1044, unless otherwise
specified. PANEL calculates decay and ingrowth of the radionuclide inventory
within each waste panel as the simulation proceeds according to the Bateman
equation using 50 year time steps. 

PANEL distributes the current solid waste inventory mass into the 
liquid volume of each waste panel so that the liquid remains saturated with 
respect to each radionuclide. If the remaining available amount of a certain 
radionuclide is not enough to saturate the liquid volume of a waste panel, the 
entire remaining amount is released. When an element has several isotopes, the
molar proportions of those isotopes dissolved in the brine are taken to be the
same as the molar proportions in the total inventory contained in the waste 
panel. The solubility limit for each radionuclide is actually an enhanced
solubility, and accounts for radionuclides dissolved in the aqueous phase, as
well as radionuclides sorbed onto colloids. Mobilization by colloidally 
suspended particulate matter is treated in exactly the same way as dissolution.
The concentration of each dissolved radionuclide in the waste panel is 
assumed uniform, and supersaturation is not allowed. The waste panel inventory
is assumed to be available immediately, which is to say that all internal
seals have failed at the moment of panel closure.

PANEL can take in as input, the flow velocity field, and uses this information
to calculate the source term due to brine flow out of the waste panel, by
assigning a radionculide concentration to the brine outflow. It also uses
the velocity field to dilute the liquid within the waste panel according to
the brine inflow. The concentration of the brine outflow is passed to BRAGFLO
as a radionculide source term.
 
How FPM, RTPM, WFPM, and UDPM Replace Code PANEL
------------------------------------------------

At the beginning of a PFLOTRAN WIPP PA simulation, the entire repository's
radionucilde inventory is specified in the WFPM, and the waste form
mechanism should be chosen as the WIPP mechanism. The WIPP mechanism assigns
an instantaneous dissolution behavior to the waste form, meaning the entire
inventory dissolves into the aqueous phase instantly at a time specified by
the user (e.g., a breach time). Up to the breach time, the WFPM calculates
the decay and ingrowth of the radionuclide inventory within the solid waste 
form, but no radionuclides are released from the waste form. To match PANEL 
behavior, a t=0 yr breach time should be specified by the user, so that the 
waste form breaches during the first time step of the simulation. Any number 
of waste forms can be assigned to a waste panel region, as long as the waste 
panel inventory and volume is properly assigned and distributed among the 
waste form(s) in the waste panel. 

Upon breach, the wase form inventory is distributed within the 
liquid phase of the waste form region by scaling the distribution of the total 
inventory to each grid cell of the waste form region by the volume ratio of
each grid cell in the waste form region to the total volume of the waste 
form region. Again, the waste form region may be a subset of the waste
panel region if multiple waste forms occupy the waste panel region. After 
this initial time step when breach occurs, the WFPM is no longer active
because the waste form volume is reduced to zero. 

According to the process model hierarchy described above, immediately after
the WFPM executes to t+dt of the FPM's time step, the UDPM executes. The
UDPM is responsible for calculating radionuclide decay and ingrowth of
radionuclides in the pore fluid, as well a phase partitioning. Therefore,
the UDPM takes the total mass of each radionuclide and (a) evolves the 
abundances of each radionuclide according to the decay chain for time t+dt,
and then (b) partitions the radionuclides into aqueous, sorbed, and 
precipitated phases according to elemental solubility limits and elemental
Kd values (for sorption). This means that at the time step when the waste
forms in the waste panels breach, the waste form inventory that was 
released into the aqueous phase evolves along the decay chain to time t+dt,
and then gets partitioned into aqueous, sorbed, and precipitated phases.
The user should specify a solubility limit that is equal to the enhanced
solubility limit in PANEL, and no sorbtion (e.g., Kd=0) in the waste
panel region. These settings will cause phase partitioning that matches
PANEL's behavior: the radionuclide inventory in the instantly breached
waste form will be dissolved up to its enhanced solubility limit, no sorption
will occur onto the host rock, and the remaining will be precipitated as a
solid mineral in the waste panel. 

At the next time step, the FPM will execute first. The FPM calculates the 
velocity field at time t+dt. The RTPM, which is the child of the FPM executes 
next, transporting the dissolved aqueous mass of the radionuclide inventory 
within the waste panel (and in fact, in the entire domain), updating the
solute field to t+dt of the FPM's time step. Since the WFPM is no longer 
active (no waste form objects remain), the UDPM is executed. The UDPM updates
the abundances of each radionuclide in each phase along the decay chain, and 
then re-partitions the radionuclides into the new equilibrium phases (e.g., 
aqueous, sorbed, and precipitated). This procedure is repeated until the end 
of the simulation.      












