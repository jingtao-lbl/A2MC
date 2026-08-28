Back to :ref:`card-index`

.. _input-record-file-card:

INPUT_RECORD_FILE
=================
Creates an input record file for each simulation.

Required Cards:
---------------

INPUT_RECORD_FILE
 Including this keyword will print an input record file for each simulation.
 The input record file prints out the values of the parameters and options that
 were specified in the input file which PFLOTRAN internalized and used for the
 simulation. This information is useful to catch mistakes in the input file,
 such as duplicate definitions of a certain parameter (which one was used?) or
 parameters or options that were commented out on accident (commented parameters
 won't be internalized, and thus won't appear on the input record file).
 
 The input record file will have the filename [pflotran].rec where [pflotran]
 is the name of the input file prefix.
 
 
Example:
--------
 ::

  SIMULATION
    SIMULATION_TYPE SUBSURFACE
    PROCESS_MODELS
      SUBSURFACE_FLOW flow
        ...
      /
      SUBSURFACE_TRANSPORT transport
        ...
      /
    /
    INPUT_RECORD_FILE
  END
  
An example input record file is shown below:
 ::
 
  --------------------------------------------------------------------------------
  --------------------------------------------------------------------------------
  PFLOTRAN INPUT RECORD    12/02/2016 16:42 (-07:00 UTC)
  --------------------------------------------------------------------------------
  --------------------------------------------------------------------------------
	input file:  bf_krp12.in
	    group:  
      n processors:  1
  
  --------------------------------------------------------------------------------
  ---------------------------: CHECKPOINTS
	      specific times: OFF
  
  
  ---------------------------:  
			  pmc: PMCSubsurface                   
	      pmc timestepper: FLOW                            
	initial timestep size: 8.6400000000000006 sec
			  pm: flow                            
			mode: general
  
  --------------------------------------------------------------------------------
	      simulation type: subsurface
		    flow mode: general
  
  --------------------------------------------------------------------------------
  ---------------------------: TIME
		max. timestep: 1.0000000E-01  yr at time 0.0000000E+00  yr
		  final time: 1.0000000E+00  yr
  
  --------------------------------------------------------------------------------
  ---------------------------: OUTPUT FILES
	      periodic screen: ON
	    screen increment: 1           
	    output time unit: yr
  ---------------------------: snapshot file output
	    periodic timestep: OFF
		periodic time: OFF
	      specific times: ON
		  times (yr): 1.0000000E+00 ,
		variable list: Temperature [C]
			      Liquid Pressure [Pa]
			      Gas Pressure [Pa]
			      Liquid Saturation []
			      Gas Saturation []
			      Liquid Density [kg/m^3]
			      Gas Density [kg/m^3]
			      X_g^l []
			      X_l^l []
			      X_g^g []
			      X_l^g []
			      Liquid Energy [MJ/kmol]
			      Gas Energy [MJ/kmol]
			      Thermodynamic State []
			      Material ID []
	  print initial time: ON
	    print final time: ON
  ---------------------------: observation file output
		      format: tecplot
	    periodic timestep: OFF
		periodic time: OFF
	      specific times: OFF
		variable list: Temperature
			      Liquid Pressure [Pa]
			      Gas Pressure [Pa]
			      Liquid Saturation []
			      Gas Saturation []
			      Liquid Density [kg/m^3]
			      Gas Density [kg/m^3]
			      X_g^l []
			      X_l^l []
			      X_g^g []
			      X_l^g []
			      Liquid Energy [MJ/kmol]
			      Gas Energy [MJ/kmol]
			      Thermodynamic State []
			      Material ID []
	  print initial time: ON
	    print final time: ON
  ---------------------------: mass balance file output
		      format: tecplot
	    periodic timestep: OFF
		periodic time: OFF
	      specific times: OFF
	  print initial time: OFF
	    print final time: ON
  
  
  --------------------------------------------------------------------------------
  ---------------------------: GRID
		    grid type: structured
			    : cartesian
	  number grid cells X: 10        
	  number grid cells Y: 1         
	  number grid cells Z: 1         
		  delta-X (m):   1.0000E+01  1.0000E+01  1.0000E+01  1.0000E+01  1.0000E+01  1.0000E+01  1.0000E+01  1.0000E+01  1.0000E+01  1.0000E+01
		  delta-Y (m):   1.0000E+01
		  delta-Z (m):   1.0000E+01
		    bounds X: 0.0000000E+00  ,1.0000000E+02  m
		    bounds Y: 0.0000000E+00  ,1.0000000E+01  m
		    bounds Z: 0.0000000E+00  ,1.0000000E+01  m
		global origin: (x) 0.0000000E+00  m
			    : (y) 0.0000000E+00  m
			    : (z) 0.0000000E+00  m
  
  --------------------------------------------------------------------------------
  ---------------------------: REGIONS
		      region: all
		  defined by: COORDINATE(S)
	      X coordinate(s): 0.0000000E+00  1.0000000E+02 m
	      Y coordinate(s): 0.0000000E+00  1.0000000E+01 m
	      Z coordinate(s): 0.0000000E+00  1.0000000E+01 m
  ---------------------------: 
		      region: left_end
		  defined by: COORDINATE(S)
	      X coordinate(s): 0.0000000E+00  0.0000000E+00 m
	      Y coordinate(s): 0.0000000E+00  1.0000000E+01 m
	      Z coordinate(s): 0.0000000E+00  1.0000000E+01 m
			face: WEST
  ---------------------------: 
		      region: right_end
		  defined by: COORDINATE(S)
	      X coordinate(s): 1.0000000E+02  1.0000000E+02 m
	      Y coordinate(s): 0.0000000E+00  1.0000000E+01 m
	      Z coordinate(s): 0.0000000E+00  1.0000000E+01 m
			face: EAST
  ---------------------------: 
  
  --------------------------------------------------------------------------------
  ---------------------------: STRATA
	strata material name: beam
		    from file: beam
      associated region name: all
		    strata is: active
	realization-dependent: FALSE
  ---------------------------: 
  
  --------------------------------------------------------------------------------
  ---------------------------: MATERIAL PROPERTIES
      material property name: beam
		  material id: 1           
	material property is: active
		permeability: isotropic
			k_xx: 1.0000000000000001E-015    m^2
			k_yy: 1.0000000000000001E-015    m^2
			k_zz: 1.0000000000000001E-015    m^2
		  tortuosity: 1.0000000000000000   
		rock density: 2800.0000000000000    kg/m^3
		    porosity: 0.50000000000000000  
		  tortuosity: 1.0000000000000000   
      specific heat capacity: 1.0000000000000000E-003    J/kg-C
	dry th. conductivity: 1.0000000000000000    W/m-C
	wet th. conductivity: 1.0000000000000000    W/m-C
    cc / saturation function: L08_a1e-3
  ---------------------------: 
  
  --------------------------------------------------------------------------------
  ---------------------------: CHARACTERISTIC CURVES
    characteristic curve name: L08_a1e-3
	  saturation function: Bragflo KRP12 modified brooks corey
			alpha: 1.0000000000000000E-003   
		      lambda: 0.80000000000000004  
	    gas residual sat.: 0.10000000000000001  
		      socmin: 1.0000000000000000E-002   
		    soceffmin: 1.0000000000000000E-003   
	liquid residual sat.: 0.10000000000000001  
      max capillary pressure: 1000000000.0000000   
    liq. relative perm. func.: none
    gas relative perm. func.: none
  ---------------------------: 
    characteristic curve name: L06_a1e-3
	  saturation function: Bragflo KRP12 modified brooks corey
			alpha: 1.0000000000000000E-003   
		      lambda: 0.59999999999999998  
	    gas residual sat.: 0.10000000000000001  
		      socmin: 1.0000000000000000E-002   
		    soceffmin: 1.0000000000000000E-003   
	liquid residual sat.: 0.10000000000000001  
      max capillary pressure: 1000000000.0000000   
    liq. relative perm. func.: none
    gas relative perm. func.: none
  ---------------------------: 
    characteristic curve name: L04_a1e-3
	  saturation function: Bragflo KRP12 modified brooks corey
			alpha: 1.0000000000000000E-003   
		      lambda: 0.40000000000000002  
	    gas residual sat.: 0.10000000000000001  
		      socmin: 1.0000000000000000E-002   
		    soceffmin: 1.0000000000000000E-003   
	liquid residual sat.: 0.10000000000000001  
      max capillary pressure: 1000000000.0000000   
    liq. relative perm. func.: none
    gas relative perm. func.: none
  ---------------------------: 
    characteristic curve name: L02_a1e-3
	  saturation function: Bragflo KRP12 modified brooks corey
			alpha: 1.0000000000000000E-003   
		      lambda: 0.20000000000000001  
	    gas residual sat.: 0.10000000000000001  
		      socmin: 1.0000000000000000E-002   
		    soceffmin: 1.0000000000000000E-003   
	liquid residual sat.: 0.10000000000000001  
      max capillary pressure: 1000000000.0000000   
    liq. relative perm. func.: none
    gas relative perm. func.: none
  ---------------------------: 
    characteristic curve name: L08_a1e-3_smo
	  saturation function: Bragflo KRP12 modified brooks corey
			alpha: 1.0000000000000000E-003   
		      lambda: 0.80000000000000004  
	    gas residual sat.: 0.10000000000000001  
		      socmin: 1.0000000000000000E-002   
		    soceffmin: 1.0000000000000000E-003   
	liquid residual sat.: 0.10000000000000001  
      max capillary pressure: 1000000000.0000000   
    liq. relative perm. func.: none
    gas relative perm. func.: none
  ---------------------------: 
    characteristic curve name: L06_a1e-3_smo
	  saturation function: Bragflo KRP12 modified brooks corey
			alpha: 1.0000000000000000E-003   
		      lambda: 0.59999999999999998  
	    gas residual sat.: 0.10000000000000001  
		      socmin: 1.0000000000000000E-002   
		    soceffmin: 1.0000000000000000E-003   
	liquid residual sat.: 0.10000000000000001  
      max capillary pressure: 1000000000.0000000   
    liq. relative perm. func.: none
    gas relative perm. func.: none
  ---------------------------: 
    characteristic curve name: L04_a1e-3_smo
	  saturation function: Bragflo KRP12 modified brooks corey
			alpha: 1.0000000000000000E-003   
		      lambda: 0.40000000000000002  
	    gas residual sat.: 0.10000000000000001  
		      socmin: 1.0000000000000000E-002   
		    soceffmin: 1.0000000000000000E-003   
	liquid residual sat.: 0.10000000000000001  
      max capillary pressure: 1000000000.0000000   
    liq. relative perm. func.: none
    gas relative perm. func.: none
  ---------------------------: 
    characteristic curve name: L02_a1e-3_smo
	  saturation function: Bragflo KRP12 modified brooks corey
			alpha: 1.0000000000000000E-003   
		      lambda: 0.20000000000000001  
	    gas residual sat.: 0.10000000000000001  
		      socmin: 1.0000000000000000E-002   
		    soceffmin: 1.0000000000000000E-003   
	liquid residual sat.: 0.10000000000000001  
      max capillary pressure: 1000000000.0000000   
    liq. relative perm. func.: none
    gas relative perm. func.: none
  ---------------------------: 
  
  --------------------------------------------------------------------------------
  ---------------------------: CHEMISTRY
  
  --------------------------------------------------------------------------------
  ---------------------------: INITIAL CONDITIONS
    initial condition listed: #1           
	    applies to region: all
	  flow condition name: initial
  ---------------------------: 
  
  --------------------------------------------------------------------------------
  ---------------------------: BOUNDARY CONDITIONS
      boundary condition name: left_end
	    applies to region: left_end
	  flow condition name: left_end
  ---------------------------: 
      boundary condition name: right_end
	    applies to region: right_end
	  flow condition name: right_end
  ---------------------------: 
  
  --------------------------------------------------------------------------------
  ---------------------------: SOURCE-SINKS
  
  --------------------------------------------------------------------------------
  ---------------------------: FLOW CONDITIONS
	  flow condition name: initial
	  sub condition name: 
	  sub condition type: DIRICHLET
	  sub condition name: 
	  sub condition type: DIRICHLET
	  sub condition name: 
	  sub condition type: DIRICHLET
  ---------------------------: 
	  flow condition name: left_end
	  sub condition name: 
	  sub condition type: DIRICHLET
	  sub condition name: 
	  sub condition type: DIRICHLET
	  sub condition name: 
	  sub condition type: DIRICHLET
  ---------------------------: 
	  flow condition name: right_end
	  sub condition name: 
	  sub condition type: DIRICHLET
	  sub condition name: 
	  sub condition type: DIRICHLET
	  sub condition name: 
	  sub condition type: DIRICHLET
  ---------------------------: 
  
  --------------------------------------------------------------------------------
  ---------------------------: TRANSPORT CONDITIONS
  
  --------------------------------------------------------------------------------
  ---------------------------: EQUATIONS OF STATE (EOS)
  --------------------------------------------------------------------------------
  ---------------------------: WATER
		water density: constant, 1000.0000000000000    kg/m^3
	      water viscosity: constant,    1.0000000000000000E-003 Pa-sec
		steam density: default, IFC67
	      steam enthalpy: default, IFC67
  --------------------------------------------------------------------------------
  ---------------------------: GAS
		  gas density: default, ideal
		gas viscosity: default
		gas enthalpy: default, ideal
	    henry's constant: default, air
  --------------------------------------------------------------------------------
