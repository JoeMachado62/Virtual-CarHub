#!/bin/bash

###############################################################################
#
# CHANGE THESE ENTRIES ONLY
#
# Write data to this location on the local system
#
DATA=/opt/chrome/Data/ChromeImageGallery
#
# FTP User
USER=
#
# FTP Password
PASS=
#
###############################################################################

# Chrome production FTP URL for ChromeImageGallery data
URL="ftp://${USER}:${PASS}@ftp.chromedata.com/media/ChromeImageGallery"

# Location of the wget command
WGET="/usr/bin/wget"

# Options for the wget command (On Unix use "man wget" for details)
# For --cut-dirs: 1 removes "media", 2 removes "media/ChromeImageGallery"
OPTS="--mirror     \
      --cut-dirs=2 \
      --timeout=60 \
      --tries=10   \
      --no-verbose \
      --no-host-directories \
      --directory-prefix=$DATA"

echo $WGET $OPTS $URL
$WGET $OPTS $URL

RC=$?

if [ $RC -eq 0 ]
then
  echo "Success"
else
  echo "Failed with exit code $RC"
fi

exit $RC
