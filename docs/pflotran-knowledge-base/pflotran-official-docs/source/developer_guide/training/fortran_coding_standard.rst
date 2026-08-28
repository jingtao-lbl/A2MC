PFLOTRAN Fortran Formatting Protocol
====================================

.. role:: fortran(code)
   :language: fortran

Guidelines
----------
* Free format
* Use :fortran:`&` for continuation
* Use :fortran:`==`, :fortran:`>`, :fortran:`<`, :fortran:`>=`, :fortran:`<=` instead of :fortran:`.eq.`, :fortran:`.eqv.`, :fortran:`.gt.`, :fortran:`.lt.`, :fortran:`.ge.`, :fortran:`.le.`.
* Do not use goto statements (may not be possible in legacy code blocks)
* Avoid *optional* arguments in favor of procedure interfaces. E.g., use

  .. code-block:: fortran

   interface LookupTableEvaluateUniform
     module procedure LookupTableEvaluateUniform1
     module procedure LookupTableEvaluateUniform2
     module procedure LookupTableEvaluateUniform3
   end interface
   ...
   function LookupTableEvaluateUniform1(this,lookup1)
   ...
   function LookupTableEvaluateUniform2(this,lookup1,lookup2)
   ...
   function LookupTableEvaluateUniform3(this,lookup1,lookup2,lookup3)

  instead of

  .. code-block:: fortran

   function LookupTableEvaluateUniform(this,lookup1,lookup2,lookup3)
     ...
     class(lookup_table_uniform_type) :: this
     PetscReal :: lookup1
     PetscReal, optional :: lookup2
     PetscReal, optional :: lookup3

  Yes, many exist in the code, but **we are trying eliminate them**.

* Use two-space indentation with **no tabs**.

  .. code-block:: fortran

   subroutine PrintIJK()

     PetscInt :: i

     do k = 1, 100
       do j = 1, 100
         do i = 1, 100
           print *, i, j, k
         enddo
       enddo
     enddo

   end subroutine PrintIJK

* Use a maximum source width of 80 characters. Use a continuation line beyond.

  .. code-block:: fortran

   !123456789+123456789+123456789+123456789+123456789+123456789+123456789+123456789+
                   print *, 'This sentence is just barely too long for a single &
                            &line.'
                   call LongSubroutineWithManyArguments(argument1, argument2, &
                                                        argument3, argument4)

* Use a maximum of 32 characters for module/subroutine/variable names.  Try to be as concise as possible.
* Capitalization

 * All Fortran syntax should be lower case.

   .. code-block:: fortran

    module File_IO_module

      use Print_module

    contains

    subroutine PrintInfo()

      if () then
      else
      elseif
      endif

    end subroutine PrintInfo

 * Parameters are all caps.

   .. code-block:: fortran

    PetscInt, parameter, public :: MAXWORDLENGTH = 32
    character(len=MAXWORDLENGTH) :: word

 * All subroutines/function names should be CamelCase without underscores.

   .. code-block:: fortran

    call FileIOInit()
    call FileIODestroy()

 * All variable/class/derived type names should be lower case with underscores between words.

   .. code-block:: fortran

    PetscMPIInt :: my_rank
    type(abc_type) :: new_abc
    class(xyz_class_type), pointer :: new_xyz

* All Fortran syntax with multiple words should have a space between words, except for conditionals and loops:  :fortran:`elseif`, :fortran:`endif`, :fortran:`enddo`.

  .. code-block:: fortran

   select case
   end select
   end subroutine

  Exceptions:

  .. code-block:: fortran

   elseif
   endif
   enddo

* Pin all module, subroutine, function, and contains declarations up against the left side.  This leaves more room for indentation.
* The default private/public attribute for modules is :fortran:`private`.
* Place :fortran:`implicit none` at the top of every module.
* Use :fortran:`PetscReal` instead of :fortran:`double precision` or :fortran:`real*8`.
* Use :fortran:`PetscInt` instead of :fortran:`integer`.
* Use :fortran:`PetscBool` instead of :fortran:`logical`.
* Use :fortran:`PETSC_TRUE/PETSC_FALSE` instead of :fortran:`.true./.false.`.
* For array declarations, use the most concise and flexible format without the *dimension* statement.

  .. code-block:: fortran

   PetscReal :: array(6)
   PetscInt :: array_1D(6), array_2D(3,100)

  instead of

  .. code-block:: fortran

   PetscReal, dimension(6) :: array
   PetscInt, dimension(6) :: array_1D
   PetscInt, dimension(3,100) :: array_2D

  Note that arrays of the same data type may be declared on separate lines for clarity.

* All variables in the function/subroutine argument list should be at the top of the routine with a blank line separating them from the 'implicit none'.  The local variables should come below with a blank line separating them from the variables in the subroutine argument list.

  .. code-block:: fortran

   subroutine Example(integer_in, real_in)

     implicit none
                              ! subroutine arguments declared first
     PetscInt :: integer_in
     PetscReal :: real_in
                              ! blank line separating local variables
     PetscBool :: whatever
     PetscInt :: i
     PetscInt :: integer1, integer2
     PetscInt :: iarray(5)
     PetscReal, pointer :: array(:)

* All pointers used in with PETSc Vec data structures have an `_p` appended.

  .. code-block:: fortran

   PetscReal, pointer :: array_p

* User appropriate spacing to improve readability:

  .. code-block:: fortran

   if(one_number>another_number.and.a_logical==PETSC_TRUE)then

  or

  .. code-block:: fortran

   if ( one_number>another_number.and.a_logical==PETSC_TRUE ) then

  are **better viewed** as

  .. code-block:: fortran

   if (one_number > another_number .and. a_logical == PETSC_TRUE) then

  .. code-block:: fortran

   pressure=rho*gravity*distance

  is **better viewed** as


  .. code-block:: fortran

   pressure = rho*gravity*distance

* Use integer exponents (e.g., x**3) instead of real exponents (e.g., x**3.d0) whenever possible. With the integer approach, the compiler creates a series of multiplication (i.e., x*x*x) which is less expensive to calculate than the $x^3 = e^{3 \ln x}$.

Filename and Module/Class Naming Convention
-------------------------------------------

* Modules and classes are Camel_Case with underscores between words and ``_module`` (or ``_class`` for Fortran 20XX classes) appended.

  ::

   Reaction_Sandbox_module
   Reaction_Sandbox_Example_class
   Reaction_Sandbox_Base_class

* The corresponding filename is the module/class name with (1) ``_module`` or ``_class`` removed, (2) all lower case, and (3) '.F90' appended.

  ::

   reaction_sandbox.F90
   reaction_sandbox_example.F90
   reaction_sandbox_base.F90

* Files containing base classes are always named ``XXX_base.F90``.

  ::

   simulation_base.F90
   reaction_sandbox_base.F90

* Files containing functions/subroutines/modules that are often commonly shared between simulation modes, process models, or implementations are named ``XXX_common.F90``.

  ::

   output_common.F90
   richards_common.F90

* Files containing low level functions/subroutines or non-extended derived types are named ``XXX_aux.F90``.

  ::

   output_aux.F90
   richards_aux.F90

* Files containing functions/subroutines that serve as drivers for all classes of a derived type, should be named ``XXX.F90`` where XXX is the root function.

  ::

   dataset.F90
   reaction_sandbox.F90

Example Fortran Source Code
---------------------------

An example source would be

 .. code-block:: fortran

  module Example_module

    implicit none

    private  ! all variables/subroutines, etc. are private by default

  #include "whatever.h"

    public :: ExampleCreate, ExampleGetTime

    PetscReal, save :: file_global_variable

  contains

  !************************************************************************** !

  subroutine ExampleSetup(integer_in, real_in)
  !
  ! Initializes the grid.
  ! Author: Jane Doe
  ! Date: 01/01/23
  !
    use whatever_module

  #include "whatever.h"

    PetscInt :: integer_in   ! note that the subroutine arguments are
    PetscReal :: real_in     ! declared first

    PetscBool :: whatever    ! note that declarations are group by type
    PetscInt :: i
    PetscInt :: integer1, integer2
    PetscReal :: real1, real2
    PetscReal :: real3, real4
    character(len=MAXWORDLENGTH) :: word
    PetscReal, pointer :: real_p(:)

    ...
    ! use the newer relational operators in logical expressions
    if (grid%ndof >= 2 .and. (.not.logical_whatever .or. &
                              integer1 /= integer2)) then
      do i=1,2
        call Whatever()
      enddo
    elseif (grid%ndof == 1 .and. &
            (.not.logical_whatever .or. integer1 == integer2)) then
      call SomethingElse()
    endif

    ! fortran select case (similar to C switch)
    select case (word)
      case ('flow')
        call Whatever
      case ('transport')
        call Whatever2(argument1, argument2, argument3, argument4, &
                       argument5)
    end select
    ...
    nullify(real_p)

  end subroutine ExampleSetup

  !************************************************************************** !

  PetscReal function ExampleGetTime(...)
  !
  ! Returns the current time in the simulation.
  ! Author: John Doe
  ! Date: 01/01/23
  !
    use another_module

    implicit none

  #include "whatever.h"

    PetscInt :: integer1
    PetscReal :: real1
    character(len=MAXWORDLENGTH) :: word

    ...
    ...
    ExampleGetTime = x

  end function ExampleGetTime

  end module Example_module
