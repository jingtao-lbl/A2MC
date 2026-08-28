#!/bin/sh
num_errors=0
CARDS_DIR=./source/user_guide/cards

# ---------------------------------------------------------------------------- #
# ---------------------------------------------------------------------------- #
# SIMULATION options

# ---------------------------------------------------------------------------- #
# FLOW

# GENERAL 
python3 ./tools/generate_tmp.py GENERAL \
$CARDS_DIR/simulation/subsurface_flow_modes/sim_general.tmp \
$CARDS_DIR/raw_txt/simulation/simulation_general.txt \
$CARDS_DIR/raw_txt/simulation/simulation_gen_hyd.txt \
$CARDS_DIR/raw_txt/simulation/simulation_subsurface_flow.txt \
$CARDS_DIR/raw_txt/simulation/simulation.txt
num_errors=$((num_errors + $?))

# HYDRATE 
python3 ./tools/generate_tmp.py HYDRATE \
$CARDS_DIR/simulation/subsurface_flow_modes/sim_hydrate.tmp \
$CARDS_DIR/raw_txt/simulation/simulation_hydrate.txt \
$CARDS_DIR/raw_txt/simulation/simulation_gen_hyd.txt \
$CARDS_DIR/raw_txt/simulation/simulation_subsurface_flow.txt \
$CARDS_DIR/raw_txt/simulation/simulation.txt
num_errors=$((num_errors + $?))

# MPHASE 
python3 ./tools/generate_tmp.py MPHASE \
$CARDS_DIR/simulation/subsurface_flow_modes/sim_mphase.tmp \
$CARDS_DIR/raw_txt/simulation/simulation_mphase.txt \
$CARDS_DIR/raw_txt/simulation/simulation_subsurface_flow.txt \
$CARDS_DIR/raw_txt/simulation/simulation.txt
num_errors=$((num_errors + $?))

# RICHARDS
python3 ./tools/generate_tmp.py RICHARDS \
$CARDS_DIR/simulation/subsurface_flow_modes/sim_richards.tmp \
$CARDS_DIR/raw_txt/simulation/simulation_richards.txt \
$CARDS_DIR/raw_txt/simulation/simulation_subsurface_flow.txt \
$CARDS_DIR/raw_txt/simulation/simulation.txt
num_errors=$((num_errors + $?))

# TH
python3 ./tools/generate_tmp.py TH \
$CARDS_DIR/simulation/subsurface_flow_modes/sim_th.tmp \
$CARDS_DIR/raw_txt/simulation/simulation_th.txt \
$CARDS_DIR/raw_txt/simulation/simulation_subsurface_flow.txt \
$CARDS_DIR/raw_txt/simulation/simulation.txt
num_errors=$((num_errors + $?))

# SCO2
python3 ./tools/generate_tmp.py SCO2 \
$CARDS_DIR/simulation/subsurface_flow_modes/sim_sco2.tmp \
$CARDS_DIR/raw_txt/simulation/simulation_sco2.txt \
$CARDS_DIR/raw_txt/simulation/simulation_subsurface_flow.txt \
$CARDS_DIR/raw_txt/simulation/simulation.txt
num_errors=$((num_errors + $?))

# WIPP_FLOW 
python3 ./tools/generate_tmp.py WIPP_FLOW \
$CARDS_DIR/simulation/subsurface_flow_modes/sim_wipp_flow.tmp \
$CARDS_DIR/raw_txt/simulation/simulation_wipp_flow.txt \
$CARDS_DIR/raw_txt/simulation/simulation_subsurface_flow.txt \
$CARDS_DIR/raw_txt/simulation/simulation.txt
num_errors=$((num_errors + $?))

# ---------------------------------------------------------------------------- #
# TRANSPORT

# RT
python3 ./tools/generate_tmp.py RT \
$CARDS_DIR/simulation/subsurface_transport_modes/sim_rt.tmp \
$CARDS_DIR/raw_txt/simulation/simulation_reactive_transport.txt \
$CARDS_DIR/raw_txt/simulation/simulation.txt
num_errors=$((num_errors + $?))

# NWT
python3 ./tools/generate_tmp.py NWT \
$CARDS_DIR/simulation/subsurface_transport_modes/sim_nwt.tmp \
$CARDS_DIR/raw_txt/simulation/simulation_nuclear_waste_transport.txt \
$CARDS_DIR/raw_txt/simulation/simulation.txt
num_errors=$((num_errors + $?))

# ---------------------------------------------------------------------------- #
# ---------------------------------------------------------------------------- #
# TIMESTEPPER options

# ---------------------------------------------------------------------------- #
# FLOW

# GENERAL 
python3 ./tools/generate_tmp.py GENERAL \
$CARDS_DIR/simulation/subsurface_flow_modes/timestepper_general.tmp \
$CARDS_DIR/raw_txt/timestepper/timestepper_subsurface_flow.txt
num_errors=$((num_errors + $?))

# HYDRATE 
python3 ./tools/generate_tmp.py HYDRATE \
$CARDS_DIR/simulation/subsurface_flow_modes/timestepper_hydrate.tmp \
$CARDS_DIR/raw_txt/timestepper/timestepper_subsurface_flow.txt
num_errors=$((num_errors + $?))

# MPHASE 
python3 ./tools/generate_tmp.py MPHASE \
$CARDS_DIR/simulation/subsurface_flow_modes/timestepper_mphase.tmp \
$CARDS_DIR/raw_txt/timestepper/timestepper_subsurface_flow.txt
num_errors=$((num_errors + $?))

# RICHARDS
python3 ./tools/generate_tmp.py RICHARDS \
$CARDS_DIR/simulation/subsurface_flow_modes/timestepper_richards.tmp \
$CARDS_DIR/raw_txt/timestepper/timestepper_subsurface_flow.txt
num_errors=$((num_errors + $?))

# TH
python3 ./tools/generate_tmp.py TH \
$CARDS_DIR/simulation/subsurface_flow_modes/timestepper_th.tmp \
$CARDS_DIR/raw_txt/timestepper/timestepper_subsurface_flow.txt
num_errors=$((num_errors + $?))

# SCO2
python3 ./tools/generate_tmp.py SCO2 \
$CARDS_DIR/simulation/subsurface_flow_modes/timestepper_sco2.tmp \
$CARDS_DIR/raw_txt/timestepper/timestepper_subsurface_flow.txt
num_errors=$((num_errors + $?))

# WIPP_FLOW 
python3 ./tools/generate_tmp.py WIPP_FLOW \
$CARDS_DIR/simulation/subsurface_flow_modes/timestepper_wipp_flow.tmp \
$CARDS_DIR/raw_txt/timestepper/timestepper_wipp_flow.txt
num_errors=$((num_errors + $?))

# ---------------------------------------------------------------------------- #
# TRANSPORT

# RT
python3 ./tools/generate_tmp.py RT \
$CARDS_DIR/simulation/subsurface_transport_modes/timestepper_rt.tmp \
$CARDS_DIR/raw_txt/timestepper/timestepper_rt_nwt.txt
num_errors=$((num_errors + $?))

# NWT
python3 ./tools/generate_tmp.py NWT \
$CARDS_DIR/simulation/subsurface_transport_modes/timestepper_nwt.tmp \
$CARDS_DIR/raw_txt/timestepper/timestepper_rt_nwt.txt
num_errors=$((num_errors + $?))

# ---------------------------------------------------------------------------- #
# ---------------------------------------------------------------------------- #
# NEWTON options
# ---------------------------------------------------------------------------- #
# FLOW

# generic Newton
# DUMMY causes the script to skip all mode-specific cards
python3 ./tools/generate_tmp.py DUMMY \
$CARDS_DIR/subsurface/newton.tmp \
$CARDS_DIR/raw_txt/newton/newton.txt
num_errors=$((num_errors + $?))

# GENERAL
python3 ./tools/generate_tmp.py GENERAL \
$CARDS_DIR/simulation/subsurface_flow_modes/newton_general.tmp \
$CARDS_DIR/raw_txt/newton/newton_general.txt \
$CARDS_DIR/raw_txt/newton/newton_gen_hyd.txt \
$CARDS_DIR/raw_txt/newton/newton_tolerances.txt \
$CARDS_DIR/raw_txt/newton/newton_subsurface_flow.txt \
$CARDS_DIR/raw_txt/newton/newton.txt
num_errors=$((num_errors + $?))

# HYDRATE 
python3 ./tools/generate_tmp.py HYDRATE \
$CARDS_DIR/simulation/subsurface_flow_modes/newton_hydrate.tmp \
$CARDS_DIR/raw_txt/newton/newton_hydrate.txt \
$CARDS_DIR/raw_txt/newton/newton_gen_hyd.txt \
$CARDS_DIR/raw_txt/newton/newton_tolerances.txt \
$CARDS_DIR/raw_txt/newton/newton_subsurface_flow.txt \
$CARDS_DIR/raw_txt/newton/newton.txt
num_errors=$((num_errors + $?))

## MPHASE 
python3 ./tools/generate_tmp.py MPHASE \
$CARDS_DIR/simulation/subsurface_flow_modes/newton_mphase.tmp \
$CARDS_DIR/raw_txt/newton/newton_mphase.txt \
$CARDS_DIR/raw_txt/newton/newton_subsurface_flow.txt \
$CARDS_DIR/raw_txt/newton/newton.txt
#num_errors=$((num_errors + $?))
#
## RICHARDS
python3 ./tools/generate_tmp.py RICHARDS \
$CARDS_DIR/simulation/subsurface_flow_modes/newton_richards.tmp \
$CARDS_DIR/raw_txt/newton/newton_subsurface_flow.txt \
$CARDS_DIR/raw_txt/newton/newton.txt
#num_errors=$((num_errors + $?))
#
## TH
python3 ./tools/generate_tmp.py TH \
$CARDS_DIR/simulation/subsurface_flow_modes/newton_th.tmp \
$CARDS_DIR/raw_txt/newton/newton_subsurface_flow.txt \
$CARDS_DIR/raw_txt/newton/newton.txt
num_errors=$((num_errors + $?))

# SCO2
python3 ./tools/generate_tmp.py SCO2 \
$CARDS_DIR/simulation/subsurface_flow_modes/newton_sco2.tmp \
$CARDS_DIR/raw_txt/newton/newton_sco2.txt \
$CARDS_DIR/raw_txt/newton/newton_tolerances.txt \
$CARDS_DIR/raw_txt/newton/newton_subsurface_flow.txt \
$CARDS_DIR/raw_txt/newton/newton.txt
num_errors=$((num_errors + $?))

# WIPP_FLOW 
python3 ./tools/generate_tmp.py WIPP_FLOW \
$CARDS_DIR/simulation/subsurface_flow_modes/newton_wipp_flow.tmp \
$CARDS_DIR/raw_txt/newton/newton_wipp_flow.txt 
num_errors=$((num_errors + $?))

# ---------------------------------------------------------------------------- #
# TRANSPORT

# RT
python3 ./tools/generate_tmp.py RT \
$CARDS_DIR/simulation/subsurface_transport_modes/newton_rt.tmp \
$CARDS_DIR/raw_txt/newton/newton_reactive_transport.txt \
$CARDS_DIR/raw_txt/newton/newton.txt
num_errors=$((num_errors + $?))

# NWT
python3 ./tools/generate_tmp.py NWT \
$CARDS_DIR/simulation/subsurface_transport_modes/newton_nwt.tmp \
$CARDS_DIR/raw_txt/newton/newton_nuclear_waste_transport.txt \
$CARDS_DIR/raw_txt/newton/newton.txt
num_errors=$((num_errors + $?))

# ---------------------------------------------------------------------------- #
# ---------------------------------------------------------------------------- #
# CHEMISTRY options
# ---------------------------------------------------------------------------- #
# RT
python3 ./tools/generate_tmp.py RT \
$CARDS_DIR/subsurface/chemistry/chemistry_options.tmp \
$CARDS_DIR/raw_txt/chemistry/chemistry_options.txt
num_errors=$((num_errors + $?))

if [ $num_errors -ne 0 ]; then
  exit 1
fi
