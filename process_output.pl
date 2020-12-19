#!/usr/bin/perl -w
use strict;

## Sits on stdout of griode.py and maintains a file of state.  Logging must be on `INFO` level or `DEBUGGING`

# current_mapping  [Chromatic|Magic|Diatonic]
# current_scale
my $key = 0;
my $scale = "";
my $mapping = "";
my $instrument = '';
$|++;
while(<>){
    /XXX (.+)$/ or next;
    chomp;
    my $one = $1;
    if($one =~ /Mapping: (\S+)/){
	$mapping = $1;
    }elsif($one =~ /key (\d+) scale (.+)\s*$/){
	$key = $1;
	$scale = $2;
    }elsif($one =~ /instrument B\d+ P\d+: (.+)\s*$/){
	$instrument = $1;
    }
    print "\r$mapping $scale $key $instrument                       ";
}
