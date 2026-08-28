#!/bin/bash

echo 'beginning deployment'

echo 'setting up ssh'
echo -e $PRIVATE_SSH_KEY >> /root/.ssh/id_rsa
chmod 600 /root/.ssh/id_rsa
echo 'transfering tarball'
scp -P 2222 -oHostKeyAlgorithms=+ssh-dss -oStrictHostKeyChecking=no /tmp/codeship.tar.gz pflotran@108.167.189.107:~
exit_status=$?
if [ $exit_status -eq 0 ]; then
  if [[ $CI_BRANCH = master ]]; then
    TARGET_DIR=public_html/documentation-dev
  elif [[ $CI_BRANCH =~ ^maint ]]; then
    TARGET_DIR=public_html/documentation
  elif [[ $CI_BRANCH =~ ^test ]]; then
    TARGET_DIR=public_html/documentation-test
  else
    echo 'failed to deploy due to unsupported branch:' $CI_BRANCH 
    exit 1
  fi
  echo 'transfer successful'
  echo 'extracting tarball to' $TARGET_DIR
  ssh -p 2222 -oHostKeyAlgorithms=+ssh-dss -oStrictHostKeyChecking=no pflotran@108.167.189.107 "/bin/rm -Rf $TARGET_DIR/* && tar -xzvf codeship.tar.gz -C $TARGET_DIR/. && /bin/rm codeship.tar.gz"
  exit_status=$?
  if [ $exit_status -eq 0 ]; then
    echo 'extraction successful'
    echo 'successful deployment'
  else
    echo 'extraction failed'
  fi
else
  echo 'transfer failed'
fi
exit $exit_status
