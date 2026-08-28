import sys
import shutil
import os
import re
import fnmatch

math = re.compile(r':math:`(?P<math_string>.*?)`')

def refactor_file(filename):
    f = open(filename,'r')
    f2 = open(filename+'.tmp','w')
    while 1:
        line = f.readline()
        if not line:
            break
        line = line.replace('`:math:','` :math')
        line = math.sub('$\g<math_string>$',line)
        f2.write(line)
    f.close()
    f2.close()
    shutil.copy(filename+'.tmp',filename)
    os.remove(filename+'.tmp')


for root, dirnames, filenames in os.walk('.'):
    for filename in filenames:
        if filename.endswith(('.rst','.txt')):
            filename = os.path.join(root,filename)
            print(filename)
            refactor_file(filename)

print('done')
