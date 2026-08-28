Reaction Sandbox
================

Background
----------

Researchers often have a suite of reactions tailored to a unique problem
scenario, but these reaction networks only exist in their respective
research codes. The “reaction sandbox” provides these researchers with a
venue for implementing user-defined reactions within PFLOTRAN. Reaction
networks developed within the reaction sandbox can leverage existing
biogeochemical capability within PFLOTRAN (e.g. equilibrium aqueous
complexation, mineral precipitation–dissolution, etc.) or function
independently. Please note that although the reaction sandbox
facilitates the integration of user-defined reactions, the process still
requires a basic understanding of PFLOTRAN and its approach to solving
reaction through the Newton-Raphson method. For instance, one must
understand the purpose and function of the rt\_auxvar and global\_auxvar
objects.

Implementing the Reaction Sandbox
---------------------------------

The core framework of reaction sandbox leverages Fortran 2003
object–oriented extendable derived types and methods and consists of two
modules:

-  Reaction\_Sandbox\_module (reaction\_sandbox.F90)

-  Reaction\_Sandbox\_Base\_class (reaction\_sandbox\_base.F90).

To implement a new reaction within the reaction sandbox, one creates a
new class by extending the Reaction\_Sandbox\_Base\_class and adds the
new class to the Reaction\_Sandbox\_module. The following steps
illustrate this process through the creation of the class
Reaction\_Sandbox\_Example\_class that implements a first order decay
reaction.

1. Copy reaction\_sandbox\_template.F90 to a new filename (e.g.
   reaction\_sandbox\_example.F90).

2. Replace all references to Template/template with the new reaction
   name.

   -  ``Template`` :math:`\rightarrow` ``Example``

   -  ``template`` :math:`\rightarrow` ``example``

3. Add necessary variables to the module and/or the extended derived
   type.

   ::

       character(len=MAXWORDLENGTH) :: species_name
       PetscInt :: species_id
       PetscReal :: rate_constant

4. Add the necessary functionality within the following subroutines:

   1. ExampleCreate: Allocate the reaction object, initializing all
      variables to zero and nullifying arrays. **Be sure to nullify
      ExampleCreate%next which comes from the base class.** E.g.,

      ::

            allocate(ExampleCreate)
            ExampleCreate%species_name = ''
            ExampleCreate%species_id = 0
            ExampleCreate%rate_constant = 0.d0
            nullify(ExampleCreate%next)

   2. ExampleRead: Read parameters in from the input file block
      ``EXAMPLE``. E.g.,

      ::

            ...
            case('SPECIES_NAME')
              call InputReadWord(input,option,this%species_name, &
                                 PETSC_TRUE)
              call InputErrorMsg(input,option,'species_name', &
                             'CHEMISTRY,REACTION_SANDBOX,EXAMPLE')
            ...

   3. ExampleSetup: Construct the reaction network (e.g. array
      allocation, establishing linkages, etc.). E.g.,

      ::

            ...
            this%species_id = &
              GetPrimarySpeciesIDFromName(this%species_name, &
                                          reaction,option)
            ...

   4. ExampleReact: Calculate contribution of reaction to the residual
      (units = moles/sec) and Jacobian (units = kg water/sec). E.g.,

      ::

            ...
            Residual(this%species_id) = &
              Residual(this%species_id) - &
              this%rate_constant*porosity* &
              global_auxvar%sat(iphase)*volume*1.d3* &
              rt_auxvar%total(this%species_id,iphase)
            ...
            Jacobian(this%species_id,this%species_id) = &
            Jacobian(this%species_id,this%species_id) + &
              this%rate_constant*porosity* &
              global_auxvar%sat(iphase)*volume*1.d3*
              rt_auxvar%aqueous%dtotal(this%species_id, &
                                       this%species_id,iphase)
            ...

   5. ExampleDestroy: Deallocate any dynamic memory within the class
      (without deallocating the object itself).

5. Ensure that the methods within the extended derived type point to the
   proper procedures in the module

   ::

         procedure, public :: ReadInput => ExampleRead
         procedure, public :: Setup => ExampleSetup
         procedure, public :: Evaluate => ExampleReact
         procedure, public :: Destroy => ExampleDestroy

6. Within reaction\_sandbox.F90:

   1. Add Reaction\_Sandbox\_Example\_class+ to the list of modules to
      be “used” at the top of the file.

   2. Add a case statement in RSandboxRead2 for the keyword defining the
      new reaction and create the reaction within. I.e.

      ::

              case('EXAMPLE')
                new_sandbox => ExampleCreate()
