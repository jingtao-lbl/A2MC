import sys

min_args = 3
if len(sys.argv) <= min_args:
    sys.exit('Number of arguments must be greater than {}.'.format(min_args))

available_modes = ['RICHARDS','TH','GENERAL','MPHASE','HYDRATE','SCO2',
                   'WIPP_FLOW','RT','NWT','DUMMY']

filenames = sys.argv
mode = sys.argv[1]
if not mode in available_modes:
    sys.exit('{} is not an available mode in generate_tmp.py.'.format(mode))
outfilename = sys.argv[2]
filenames.pop(0) # remove the name of the script
filenames.pop(0) # remove mode
filenames.pop(0) # remove outfilename

print('Generating {}'.format(outfilename.split('/')[-1]))
     
basic_dictionary = {}
expert_dictionary = {}
for filename in filenames:
    try: 
        f = open(filename,encoding='utf-8',mode='r')
    except IOError:
        sys.exit('Unable to open file {}.'.format(filename))
    list_ = []
    strings = []
    expert = False
    skip_card = False
    for line in f:
        if line.startswith('#'):
            continue
        if len(line.rstrip()) > 0 and not line.startswith(' '):
            if list_ and not skip_card:
                keyword = list_[0]
                if keyword.startswith(':REF:`'):
                    keyword = keyword[6:]
                list_.append(strings)
                if keyword in basic_dictionary or keyword in expert_dictionary:
                    sys.exit('Key {} already exists in Python dictionary. '.
                             format(keyword)+
                             'Currently constructing {}.'.format(outfilename))
                if expert:
                    expert_dictionary[keyword] = list_
                else:
                    basic_dictionary[keyword] = list_
            list_ = []
            strings = []
            expert = False
            skip_card = False
        if not list_ and len(line.strip()) > 0:
            w = line.split()
            list_.append(w[0].upper())
            list_.append(line.strip())
        elif line.strip().startswith('@'):
            w = line.strip().lstrip('@').split()
            keyword = w[0].strip()
            w = w[1:]
            if keyword.strip().startswith('SUPPORTED_MODES'):
                supported_modes = w
                skip_card = True
                for local_mode in supported_modes:
                    if not local_mode in available_modes:
                        sys.exit('Supported mode {} is '.format(local_mode)+
                                 'not an available mode in generate_tmp.py.')
                    if local_mode == mode:
                        skip_card = False
                        break
            elif keyword.strip().startswith('UNSUPPORTED_MODES'):
                unsupported_modes = w
                skip_card = False
                for local_mode in unsupported_modes:
                    if not local_mode in available_modes:
                        sys.exit('Unsupported mode {} is '.format(local_mode)+
                                 'not an available mode in generate_tmp.py.')
                    if local_mode == mode:
                        skip_card = True
                        break
            elif keyword.startswith('EXPERT'):
                expert = True
            else:
                sys.exit('Unrecognized tag: {} in {}'.format(keyword,filename))
        else:
            strings.append(line.rstrip())
    if len(strings) > 0:
        if list_ and not skip_card:
            list_.append(strings)
            keyword = list_[0]
            if keyword in basic_dictionary or keyword in expert_dictionary:
                sys.exit('Key {} already exists in Python dictionary. '.
                         format(keyword)+
                         'Currently constructing {}.'.format(outfilename))
            if expert:
                expert_dictionary[keyword] = list_
            else:
                basic_dictionary[keyword] = list_
    f.close()
    
f = open(outfilename,encoding='utf-8',mode='w')
if len(basic_dictionary) > 0:
    f.write('\n**Basic Settings**\n\n')
for entry in sorted(basic_dictionary):
    f.write('{}\n'.format(basic_dictionary[entry][1].strip()))
    strings = basic_dictionary[entry][2]
    for string in strings:
        f.write('{}\n'.format(string))
if not mode.startswith('DUMMY'):
    if len(expert_dictionary) > 0:
        if len(basic_dictionary) > 0:
            f.write('\n--------------------\n')
        f.write('\n**Expert Settings**\n\n')
for entry in sorted(expert_dictionary):
    f.write('{}\n'.format(expert_dictionary[entry][1].strip()))
    strings = expert_dictionary[entry][2]
    for string in strings:
      f.write(' {}\n'.format(string.strip()))
f.close()
