#!/bin/sh

# generate codeship_deploy_key and codeship_deploy_key.pub, configured to not require passphrase
docker run -it --rm -v $(pwd):/keys/ codeship/ssh-helper generate "gehammo@sandia.gov" && \
# store codeship_deploy_key as one liner entry into codeship.env file under `PRIVATE_SSH_KEY`
docker run -it --rm -v $(pwd):/keys/ codeship/ssh-helper prepare && \
# remove original private key file
rm -f codeship_deploy_key && \
# encrypt file
jet encrypt codeship.env codeship.env.encrypted && \
# ensure that `.gitignore` includes all sensitive files/directories
docker run -it --rm -v $(pwd):/app -w /app ubuntu:16.04 \
/bin/bash -c 'echo -e "codeship.aes\ncodeship_deploy_key\ncodeship_deploy_key.pub\ncodeship.env\n.ssh" >> .gitignore'
