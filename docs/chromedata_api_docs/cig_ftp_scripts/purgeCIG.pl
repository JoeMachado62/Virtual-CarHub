#!/usr/bin/perl
use strict;
use File::Basename;
use File::Copy;
use File::Find;
use File::Path;

###############################################################################
#
# CHANGE THIS ENTRY ONLY
#
# Search for ".listing" files starting at this base location
#
my $DATA      = '/opt/chrome/Data/ChromeImageGallery';
#
###############################################################################

# Set Debug to 0 to remove old data
# Set Debug to 1 to show old data but not remove it
my $Debug     = 1;

# Change nothing below this point
my @List1;
my $ListFiles = {};
my $RealFiles = {};

my @Remove;
my @Alert;

# Locate all ".listing" files created by the wget process
sub findListing {
    if ( $_ eq "\.listing" ) {
	push @List1, $File::Find::name;
    }
}

# Create a file list from a ".listing" file
sub grabList {
    my $f = shift;
    $ListFiles = {};

    my @a;
    open(IN, $f) or die "Unable to open $f\n";
    while (<IN>) {
	chomp;   # Remove newline
	chop;
	my (@a) = split / /;
	next if basename($a[$#a]) =~ /^\.+$/;
	$ListFiles->{$a[$#a]} = 1;
    }
   close IN;
    return $ListFiles;
}

# Create a file list from and actual folder
sub grabReal {
    my $f = shift;
    $RealFiles = {};

    opendir DIR, dirname($f) or die "Unable to read directory ".dirname($f)."\n";
    my (@Files) = grep { !/^\.listing$/ && !/^\.+$/ } readdir DIR;
    closedir DIR;

    foreach (@Files) { $RealFiles->{$_} = 1; }
    return $RealFiles;
}

# Compare hashes of file listings
sub Compare {
    my $a = shift;
    my $b = shift;
    my @rtn;

    foreach my $f (keys %$a) {
	next if defined $b->{$f};
	push @rtn, $f;
    }
    return @rtn;
}

# Find all ".listing" files
find(\&findListing, $DATA);

# Compare file lists from ".listing" files with actual directory contents
foreach my $List (@List1) { 
    my $A = &grabList($List);
    my $B = &grabReal($List);

    foreach my $F (&Compare($A, $B)) { push @Alert,  dirname($List)."/".$F; }
    foreach my $F (&Compare($B, $A)) { push @Remove, dirname($List)."/".$F; }
}

# Files which exist but are not listed in the ".listing" file
# These are out of date and should be removed
print "Files existing but not downloaded\n" unless $#Remove < 0;
foreach (@Remove) { 
    print $_."\n";
    if ( $Debug == 0 ) {
	if ( -f $_ ) {
	    unlink $_;
	} else {
	    rmtree([$_], 0, 0);
	}
    }
}

# Files listed in the ".listing" file but which do not exist on disk
# Any number greater than 0 indicates an error with the wget process
print "Files in download which do not exist\n" unless $#Alert < 0;
foreach (@Alert) { 
    print $_."\n";
}

print "\n";
print "Remove: ", $#Remove+1, "\n";
print "Error:  ", $#Alert+1, "\n";

exit;
