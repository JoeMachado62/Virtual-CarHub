@echo off
REM #########################################################################
REM
REM CHANGE THESE ENTRIES ONLY

REM Write data to this location on the local system
set DATA=C:\Data\ChromeImageGallery

REM FTP User
set USERNAME=

REM FTP Password
set PASSWORD=

REM Location of the wget command
set WGET=C:\WW\wget
REM
REM #########################################################################

REM Chrome production FTP URL for Chrome Image Gallery data
set URL=ftp://%USERNAME%:%PASSWORD%@ftp.chromedata.com/media/ChromeImageGallery

REM Options for the wget command (On Unix use "man wget" for details)
REM For --cut-dirs: 1 removes "media", 2 removes "media/ChromeImageGallery"
set OPTS=--mirror --cut-dirs=2 --timeout=60 --tries=10 --no-verbose --no-host-directories --directory-prefix=%DATA%

echo %WGET% %OPTS% %URL%
%WGET% %OPTS% %URL%
