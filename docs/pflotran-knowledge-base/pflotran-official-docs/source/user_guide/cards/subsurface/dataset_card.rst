Back to :ref:`card-index`

.. _dataset-card:

DATASET
=======
Specifies a dataset to be associated with parameters sets in the model.  

Required Cards:
---------------
DATASET <optional string>
 Opens the DATASET block with the name of the dataset in the string.  
 If the name is not provided, the NAME entry below must be included.

FILENAME <string>
 Name of file containing data.

HDF5_DATASET_NAME <string>
 Name of the group within an HDF5 file where the data resides.

NAME <string>
 Name of the dataset if not included with DATASET card.  
 **Note:** this string overwrites the optional string specified after 
 the DATASET card.

REALIZATION_DEPENDENT
 A toggle card that will load the dataset based on the realization ID.
 For instance, if a dataset named "perm" is tied to PERMEABILITY within a
 :ref:`material-property-card` and the realization ID is 99, PFLOTRAN searches
 for an HDF5 dataset labeled "perm99".

Cell-Indexed Datasets
+++++++++++++++++++++
Cell indexed datasets specify a value for each grid cell in the domain. 
These datasets may only be used for initial conditions and material 
properties.
Within the HDF5 file, the dataset takes the following form:

 1. A top-level HDF5 dataset named *Cell Ids* lists the integer IDs of all
    cells as aligned with the dataset values, typically numbered 1-N, but
    theoretically, the user can list the IDs randomly and the data will
    end up in the correct location.
 2. A top level HDF5 dataset named after the dataset in the PFLOTRAN input
    file stores the data assigned to the cells. The name in the PFLOTRAN
    input file must match the dataset name in the HDF5 file. When
    realization-dependent, the realization id will be appended automatically
    in PFLOTRAN to match the name in the HDF5 file.
 
The attached :download:`cell_indexed_dataset.py <files/cell_indexed_dataset.py>` generates a cell-indexed poros99 dataset.

Gridded Datasets
++++++++++++++++
For most any location in an input file where the FILE or LIST keyword 
could be applied, the user may use the keyword DATASET followed by 
the name of the dataset entered under a 
DATASET block elsewhere in the input file.  However, the user must exercise 
vigilance to ensure that the dataset is properly organized in the HDF5 file and 
is aligned spatially with the domain.  
Gridded Datasets are distributed on a **uniform Cartesian grid**
in 1D, 2D or 3D from which PFLOTRAN may interpolate values.
Within the HDF5 file, the dataset takes the following form (names used in these steps refer to the examples below):

 1. At the top of the HDF5 file (i.e. outside of any lower level groups), the user creates an HDF5 Group, in this case named *river_head*.  
 2. Within the Group, two separate HDF5 Datasets are created: one named 
    *Data* and the other *Time*, where *Time* is optional.

  a. The ''Data'' Dataset is N dimensional array corresponding to the rank 
     of the data plus a time dimension, if transient. The time dimension 
     is indexed farthest to the right (dim1,dim2,...,t).
  b. The ''Time'' Dataset is one dimensional and holds the times associated 
     with the data in the *Data* dataset, if transient. It sized equal to 
     the number of times in the *Data* dataset. See *Time Units* below.

 3. Add the following HDF5 Attributes to the HDF5 Group

  a. Dimension <string>: where options are X, Y, Z, XY, XZ, YZ, XYZ
  b. Discretization <double array>: the grid spacing for the dimensions in *a*
  c. Origin <double array>: the origin of the dimensions in *a*
  d. Max Buffer Size <int>: size of internal buffer storing (time) slices
     of a transient dataset when the entire dataset cannot be held in memory.
     Must be greater than 1 for non-STEP interpolation.
  e. Space Interpolation Method <string>: string = 'STEP' or 'LINEAR'
  f. Cell Centered <bool>: the dataset is cell centered.  Otherwise, it is node 
     centered and you need an additional entry for each dimension (e.g. nx+1 
     values for X).
  g. Time Units <string>: time units for ''Time'' Dataset. Required only
     only if time units are not seconds (s). Options include second, minute,
     hour, day, week, month, year. You can also use abbreviations: 
     s,min,h,d,w,mo,y.

The attached :download:`gridded_dataset.h5 <files/gridded_dataset.h5>` illustrates 
the usage.

Examples
--------

Dataset use in FLOW_CONDITION

 ::

  DATASET y_river_boundary_head
    FILENAME data.h5
    HDF5_DATASET_NAME river_head
  END

  FLOW_CONDITION river
    TYPE
      LIQUID_PRESSURE HYDROSTATIC
    /
    DATUM DATASET y_river_boundary_head
    LIQUID_PRESSURE 101325.d0
  END

Porosity dataset used in MATERIAL_PROPERTY that is consistent with :download:`cell_indexed_dataset.py <files/cell_indexed_dataset.py>`

 ::

  DATASET por
    HDF5_DATASET_NAME poros99
    FILENAME cell_index_dataset.h5
  END

  MATERIAL_PROPERTY soil1
    ID 1
    POROSITY DATASET por
    TORTUOSITY 1.d0
  END

Realization-dependent dataset use in MATERIAL_PROPERTY

 ::

  DATASET perm
    FILENAME hanford_unit.h5
    REALIZATION_DEPENDENT
  END

  DATASET poros
    FILENAME hanford_unit.h5
    REALIZATION_DEPENDENT
  END

  MATERIAL_PROPERTY hanford_unit
    ...
    POROSITY DATASET poros
    PERMEABILITY 
      ...
      DATASET perm
      ...
    /
    ...
  END

Dataset use in a transport CONSTRAINT

 ::

  DATASET initial_pH
    HDF5_DATASET_NAME pH
    FILENAME parameters-543.h5
  END

  DATASET initial_Calcite_vol_frac
    HDF5_DATASET_NAME Calcite_vol_frac
    FILENAME parameters-543.h5
  END

  CONSTRAINT initial
    CONCENTRATIONS
      H+     1.d-8      P  DATASET initial_pH
      HCO3-  1.d-3      G  CO2(g)
      Ca++   5.d-4      M  Calcite
    /
    MINERALS
      Calcite DATASET initial_Calcite_vol_frac 1.d0
    /
  END
