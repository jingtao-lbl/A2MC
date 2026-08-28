Introduction
============

PFLOTRAN solves a system of generally nonlinear partial differential
equations describing multiphase, multicomponent and multiscale reactive
flow and transport in porous materials. The code is designed to run on
massively parallel computing architectures as well as workstations and
laptops (e.g. Hammond et al., 2011). Parallelization is achieved through
domain decomposition using the PETSc (Portable Extensible Toolkit for
Scientific Computation) libraries for the parallelization framework
(Balay et al., 1997).

PFLOTRAN has been developed from the ground up for parallel scalability
and has been run on up to :math:`2^{18}` processor cores with problem
sizes up to 2 billion degrees of freedom. Written in object oriented,
modern Fortran, the code requires the latest compilers compatible with
Fortran 2003/2008.  As a requirement of running problems
with a large number of degrees of freedom, PFLOTRAN allows reading input
data that would be too large to fit into memory if allocated to a single
processor core. The current limitation to the problem size PFLOTRAN can
handle is the limitation of the HDF5 file format used for parallel IO to
32 bit integers. Noting that :math:`2^{32} = 4,294,967,296`, this gives
an estimate of several billion degrees of freedom for the maximum
problem size that can be currently run with PFLOTRAN. Hopefully this
limitation will be remedied in the near future.

Currently PFLOTRAN can handle a number of subsurface processes involving
flow and transport in porous media including the Richards equation;
aniosothermal, miscible, multiphsae flow; and
multicomponent reactive transport with aqueous complexation, sorption
and mineral precipitation and dissolution. Reactive transport equations
are solved using a fully implicit Newton-Raphson algorithm. 
In addition to single continuum
processes, a novel approach is used to solve equations resulting from a
multiple interacting continuum method for modeling flow and transport in
fractured media. This implementation is still under development.
Finally, an elastic geomechanical model is implemented.

A novel feature of the code is its ability to run multiple
realizations simultaneously, for example with different
permeability and porosity fields, on one or more processor cores per
run. This can be extremely useful when conducting sensitivity analyses
and quantifying model uncertainties. When running on machines with many
processes this means that hundreds of simulations can be conducted in the
amount of time needed for a single realization.

For questions regarding installing PFLOTRAN on workstations, small 
clusters, and supercomputers, and bug reports, please constant:
``pflotran-users at googlegroups dot com``. For questions regarding
running PFLOTRAN, contact: ``pflotran-users at googlegroups dot com``.
