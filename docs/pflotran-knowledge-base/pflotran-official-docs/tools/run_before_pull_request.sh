#!/bin/sh

MAKE_LOG="make.log"

if [ ! -d "tools" ]; then
  cd ..
fi

echo 'begin build'

echo 'building html'
make clean
make html 2>&1 | tee $MAKE_LOG
NUM_ERROR=$(grep -c "ERROR:" "$MAKE_LOG")
NUM_WARNING=$(grep -c "WARNING:" "$MAKE_LOG")
NUM_TOTAL=`expr $NUM_ERROR + $NUM_WARNING`
exit_status=0
if [ $NUM_TOTAL -eq 0 ]; then
  echo 'build succeeded. you may submit a pull request'
else
  echo
  echo 'build failed due to the following warnings or errors'
  if [ $NUM_ERROR -gt 0 ]; then
    echo
    echo 'Errors:'
    echo
    grep 'ERROR:' $MAKE_LOG
  fi
  if [ $NUM_WARNING -gt 0 ]; then
    echo
    echo 'Warnings:'
    echo
    grep 'WARNING:' $MAKE_LOG
  fi
  echo
  echo 'build failed due to the preceding warnings or errors. please fix'
  echo
  exit_status=1
fi
/bin/rm -f $MAKE_LOG
exit $exit_status
