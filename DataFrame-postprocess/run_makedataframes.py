##################################################################################
# Description
##################################################################################
# This script reads in arbitrary MET ASCII output files 
# and creates Pandas dataframes containing a time series for each file type
# versus lead time to a verification period. The dataframes are saved into a
# Pickled dictionary organized by MET file extension as key names, taken
# agnostically from bash wildcard patterns.
#
# Batches of hyper-parameter-dependent data can be processed by constructing
# lists of proc_gridstat arguments which define configurations that will be mapped
# to run in parallel through Python multiprocessing.
#
##################################################################################
# License Statement
##################################################################################
#
# Copyright 2023 CW3E, Contact Colin Grudzien cgrudzien@ucsd.edu
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#     http://www.apache.org/licenses/LICENSE-2.0
# 
#     Unless required by applicable law or agreed to in writing, software
#     distributed under the License is distributed on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#     See the License for the specific language governing permissions and
#     limitations under the License.
# 
##################################################################################
# Imports
##################################################################################
import sys
import os
import numpy as np
import pandas as pd
import pickle
import copy
import glob
from datetime import datetime as dt
from datetime import timedelta
import multiprocessing 
from multiprocessing import Pool
from DataFrame_config import *

##################################################################################
# Construct hyper-paramter array for batch processing ASCII outputs
##################################################################################
# convert to date times
if len(STRT_DT) != 10:
    print('ERROR: STRT_DT, ' + STRT_DT + ', is not in YYYYMMDDHH format.')
    sys.exit(1)
else:
    iso = STRT_DT[:4] + '-' + STRT_DT[4:6] + '-' + STRT_DT[6:8] + '_' +\
            STRT_DT[8:]
    strt_dt = dt.fromisoformat(iso)

if len(STOP_DT) != 10:
    print('ERROR: STOP_DT, ' + STOP_DT +\
            ', is not in YYYYMMDDHH format.')
    sys.exit(1)
else:
    iso = STOP_DT[:4] + '-' + STOP_DT[4:6] + '-' + STOP_DT[6:8] + '_' +\
            STOP_DT[8:]
    stop_dt = dt.fromisoformat(iso)

if len(CYC_INC) != 2:
    print('ERROR: CYC_INC, ' + CYC_INC + ', is not in HH format.')
    sys.exit(1)
else:
    cyc_inc = CYC_INC + 'H'

# container for map
CNFGS = []

# generate the date range for the analyses
analyses = pd.date_range(start=strt_dt, end=stop_dt, freq=cyc_inc).to_pydatetime()

print('Processing configurations:')
for anl_dt in analyses:
    anl_strng = anl_dt.strftime('%Y%m%d%H')
    for CTR_FLW in CTR_FLWS:
        for MEM_ID in MEM_IDS:
            for GRD in GRDS:
                if MEM_ID == '':
                    mem_id = ''
                else:
                    mem_id = '/' + MEM_ID

                if GRD == '':
                    grd = ''
                else:
                    grd = '/' + GRD

                # storage for configuration settings as arguments of proc_gridstat
                # the function definition and role of these arguments are in the
                # next section directly below
                CNFG = []

                # forecast zero hour date time
                CNFG.append(anl_strng)
    
                # control flow / directory name
                CNFG.append(CTR_FLW)
    
                # grid to be processed
                CNFG.append(GRD)
    
                # path to ASCII input cycle directories from IN_ROOT
                CNFG.append('/' + CTR_FLW )
                
                # path to ASCII outputs from cycle directory
                CNFG.append(mem_id + grd)
    
                # path to output pandas cycle directories from OUT_ROOT
                CNFG.append('/' + CTR_FLW)
    
                # append configuration to be mapped
                CNFGS.append(CNFG)

##################################################################################
# Data processing routines
##################################################################################
#  function for multiprocessing parameter map
def proc_gridstat(cnfg):
    # unpack argument list
    anl_strng, ctr_flw, grid, in_cyc_dir, in_dt_subdir, out_cyc_dir = cnfg

    # include underscore if grid is of nonzero length
    if len(grid) > 0:
        grd = '_' + grid
    else:
        grd = ''

    log_dir = OUT_ROOT + '/batch_logs'
    os.system('mkdir -p ' + log_dir)

    with open(log_dir + '/proc_gridstat' + pfx + grd + '_' + ctr_flw + '_' +\
              anl_strng + '.log', 'w') as log_f:

        # define derived data paths 
        in_data_root = IN_ROOT + in_cyc_dir 

        out_data_root = OUT_ROOT + out_cyc_dir
        os.system('mkdir -p ' + out_data_root)
        
        # check for input / output root directory
        if not os.path.isdir(in_data_root):
            print('ERROR: input data root directory ' + in_data_root +\
                    ' does not exist.', file=log_f)
            sys.exit(1)
        
        # check for input / output root directory
        elif not os.path.isdir(out_data_root):
            print('ERROR: output data root directory ' + out_data_root +\
                    ' does not exist.', file=log_f)
            sys.exit(1)
        
        # initiate empty dictionary for storage of dataframes by keyname
        data_dict = {}
    
        # define the gridstat files to open based on the analysis date
        in_paths = in_data_root + '/' + anl_strng + in_dt_subdir  +\
                   '/' + pfx + '*.txt'

        print('Loading grid_stat ASCII outputs from in_paths:', file=log_f)
        print(INDT + in_paths, file=log_f)
    
        # define the output binary file for pickled dataframe per date
        out_dir = out_data_root + '/' + anl_strng
        out_path = out_dir + '/grid_stats' + pfx + grd + '_' + anl_strng + '.bin'
        os.system('mkdir -p ' + out_dir)

        print('Writing Pandas dataframe pickled binary files to out_path:',
                file=log_f)
        print(INDT + out_path, file=log_f)

        # loop sorted grid_stat_pfx* files, sorting compares first on the
        # length of lead time for non left-padded values
        in_paths = sorted(glob.glob(in_paths),
                          key=lambda x:(len(x.split('_')[-4]), x))
        for in_path in in_paths:
            print('Opening file ' + in_path, file=log_f)
    
            # cut the diagnostic type from file name
            fname = in_path.split('/')[-1]
            split_name = fname.split('_')
            postfix = split_name[-1].split('.')
            postfix = postfix[0]
    
            # open file, load column names, then loop lines
            with open(in_path) as f:
                cols = f.readline()
                cols = cols.split()
                
                if len(cols) > 0:
                    fname_df = {} 
                    tmp_dict = {}
                    df_indx = 1
    
                    print(INDT + 'Loading columns:', file=log_f)
                    for col_name in cols:
                        print(INDT * 2 + col_name, file=log_f)
                        fname_df[col_name] = [] 
    
                    fname_df = pd.DataFrame.from_dict(fname_df,
                                                      orient='columns')
    
                    # parse file by line, concatenating columns
                    for line in f:
                        split_line = line.split()
    
                        for i in range(len(split_line)):
                            val = split_line[i]
    
                            # filter NA vals
                            if val == 'NA':
                                val = np.nan
                            tmp_dict[cols[i]] = val
    
                        tmp_dict['line'] = [df_indx]
                        tmp_dict = pd.DataFrame.from_dict(tmp_dict,
                                                          orient='columns')
                        fname_df = pd.concat([fname_df, tmp_dict], axis=0)
                        df_indx += 1
    
                    fname_df['line'] = fname_df['line'].astype(int)
                    
                    if postfix in data_dict.keys():
                        last_indx = data_dict[postfix].index[-1]
                        fname_df['line'] = fname_df['line'].add(last_indx)
                        fname_df = fname_df.set_index('line')
                        data_dict[postfix] = pd.concat([data_dict[postfix],
                                                        fname_df], axis=0)
    
                    else:
                        fname_df = fname_df.set_index('line')
                        data_dict[postfix] = fname_df
    
                else:
                    print('WARNING: file ' + in_path +\
                            ' is empty, skipping this file.', file=log_f)
    
                print('Closing file ' + in_path, file=log_f)
    
        print('Writing out data to ' + out_path, file=log_f)
        with open(out_path, 'wb') as f:
            pickle.dump(data_dict, f)

        print('Completed: ' + anl_strng + '_' + prfx + grid + ctr_flw) 

##################################################################################
# Runs multiprocessing on parameter grid
##################################################################################
# infer available cpus for workers
n_workers = multiprocessing.cpu_count() - 1
print('Running proc_gridstat with ' + str(n_workers) + ' total workers.')

with Pool(n_workers) as pool:
    print(*pool.map(proc_gridstat, CNFGS))

##################################################################################
# end
