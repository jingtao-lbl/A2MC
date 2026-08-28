#!/bin/sh

MAKE_LOG="make.log"
# environment variables
MAKE_LOG="make.log"
# the following conditional allows one to run this script outside of
# codeship
if [ -d /app ]; then
  APP_DIR=/app
else
  APP_DIR=`pwd`
fi

echo 'begin build'

cd $APP_DIR/documentation
echo 'building html'
make clean
make html 2>&1 | tee $MAKE_LOG
NUM_ERROR=$(grep -c "ERROR:" "$MAKE_LOG")
NUM_WARNING=$(grep -c "WARNING:" "$MAKE_LOG")
NUM_TOTAL=`expr $NUM_ERROR + $NUM_WARNING`
exit_status=0
if [ $NUM_TOTAL -eq 0 ]; then
  echo 'build succeeded'
  echo 'building tarball'
  cd _build/html
  tar -czvf /tmp/codeship.tar.gz *
  exit_status=$?
  if [ $exit_status -gt 0 ]; then
    echo 'tarball failed'
  else
    echo 'tarball succeeded'
  fi
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
  echo 'build failed due to the preceding warnings or errors'
  echo
  exit_status=1
fi
exit $exit_status
