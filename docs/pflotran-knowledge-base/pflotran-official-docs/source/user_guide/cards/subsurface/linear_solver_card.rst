Back to :ref:`card-index`

.. _linear-solver-card:

LINEAR_SOLVER
=============
Specifies linear solver type and parameters associated with convergence.

Required Cards:
---------------
LINEAR_SOLVER
 Opens the linear solver block.

 *Default solver is Bi-CGStab with block Jacobi preconditioning and ILU[0] in* 
 *each block*.

Optional Cards:
---------------
**Note: See the** PETSc_ **users manual for a more definitive explanation of** 
**the ATOL, RTOL, and DTOL solver tolerances below.**

.. _PETSc: http://www.mcs.anl.gov/petsc/documentation/index.html

ATOL <float>
 Declare convergence when the 2-norm of residual is less than ATOL :math:`\left(\|b-A x_n)\|<\text{ATOL}\right)`. (default: :math:`10^{-50}`).

DTOL <float>
 Declare divergence when the 2-norm of the residual is greater than DTOL times the 2-norm of the initial residual :math:`\left(\frac{\|b-A x_n\|}{\|b-A x_0\|}>\text{DTOL}\right)`. (default: :math:`10^{4}`).

LU_ZERO_PIVOT_TOL <float>
 Specifies zero pivot tolerance for ILU/LU preconditioners.

MAXIMUM_NUMBER_OF_ITERATIONS <int>
 Maximum number of linear solver iterations.

PRECONDITIONER <string>
 Specifies preconditioner type, where options include: NONE, ILU, LU, BJACOBI, 
 ADDITIVE_SCHWARZ or ASM, HYPRE, CPR. Interchangeable with PC_TYPE (from PETSc).

RTOL <float>
 Declare convergence when the 2-norm of the residual is less than RTOL times the 2-norm of the initial residual :math:`\left(\frac{\|b-A x_n\|}{\|b-A x_0\|}<\text{RTOL}\right)`. (default: :math:`10^{-5}`).

SOLVER <string>
 Specifies solver type, where options include: DIRECT, ITERATIVE, GMRES, BCGS, 
 IBCGS. Interchangeable with KSP_TYPE (from PETSc).  DIRECT uses LU and 
 ITERATIVE employs Bi-CGStab (BCGS) and block Jacobi preconditioning with 
 ILU[0] in each block.

STOP_ON_FAILURE
 Forces the simulation to stop when the linear solver fails to converge.

Expert Level
++++++++++++
CPR_OPTIONS
 When using the Constrained Pressure Residual Preconditioner 
 (PRECONDITIONER CPR), multiple options can be set. SOLVER FGMRES and 
 MAXIMUM_NUMBER_OF_ITERATION 1000 are highly recommended.

  CPR_TYPE <string> 
   COMBINATIVE is a two-stage preconditioner where Algebraic Multigrid
   (AMG) is applied to decoupled pressure block of the Jacobian matrix, and
   Block-Jacobi ILU(0) is applied globally as the second stage.
   ADDITIVE is a three-stage preconditioner where AMG is applied to the
   saturation block of the Jacobian matrix in addition to
   COMBINATIVE method. Default = COMBINATIVE.

  CPR_EXTRACTION_TYPE <string>
   Defines the approach to decoupling the block matrix.
   There are two main methods: alternate-block-factorization(ABF)
   and quasi-implicit-pressure-explicit-saturation (QIMPES).
   Available cards are ABF, ABF_TWO_UNKNOWNS, ABF_IMMISCIBLE, ABF_THREE_UNKNOWNS,
   ABF_MISCIBLE, ABF_GENERIC, QIMPES_IMMISCIBLE, QIMPES_TWO_UNKNOWNS,
   QIMPES. Default = QIMPES.

  T1_SCALE
   This options scales the decoupled pressure block to keep the shape of long
   waves of diffusion characteristics for AMG. This scaling is recommended and
   used by default.
  
  T1_NO_SCALE
   Turns off T1_SCALE
  
  T3_SCALE
   This option scales the decoupled saturation block as described in T1_SCALE.
  
  T3_NO_SCALE
   Turns off T3_SCALE. Recommended and used by default.
 
Examples
--------
 ::

  LINEAR_SOLVER
    SOLVER DIRECT
  /

  LINEAR_SOLVER
    SOLVER ITERATIVE
  /

  LINEAR_SOLVER
    SOLVER GMRES
    PRECONDITIONER ILU
  /

**Advanced PETSc options**

 ::

  LINEAR_SOLVER
    KSP_TYPE IBCGS
    PC_TYPE ASM
  /

  LINEAR_SOLVER
    KSP_TYPE PCNONE
    PC_TYPE LU
    LU_ZERO_PIVOT_TOL 1d-15
  /

**CPR options basic**

 ::

  LINEAR_SOLVER
    MAXIMUM_NUMBER_OF_ITERATIONS 1000        
    SOLVER FGMRES
    PRECONDITIONER CPR
  END

**CPR options advanced**

 ::

  LINEAR_SOLVER
    MAXIMUM_NUMBER_OF_ITERATIONS 1000
    SOLVER FGMRES
    PRECONDITIONER CPR
    CPR_OPTIONS
      CPR_TYPE COMBINATIVE
      CPR_EXTRACTION_TYPE QIMPES
      T1_SCALE
    END
  END
