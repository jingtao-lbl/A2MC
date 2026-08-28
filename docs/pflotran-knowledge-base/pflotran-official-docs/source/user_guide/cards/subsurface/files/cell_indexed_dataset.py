import sys
import math
from h5py import *
import numpy

filename = 'cell_indexed_dataset.h5'
h5file = File(filename,mode='w')

n = 10

# create integer array for cell ids
iarray = numpy.arange(n,dtype='i4')
# convert to 1-based
iarray[:] += 1
dataset_name = 'Cell Ids'
h5dset = h5file.create_dataset(dataset_name, data=iarray)

# create double array for porosities
rarray = numpy.zeros(n,dtype='f8')
rarray[:] = 0.25
rarray[4:7] = 0.3
dataset_name = 'poros99'
h5dset = h5file.create_dataset(dataset_name, data=rarray)

h5file.close()
