#!/bin/perl -w
use strict;
chdir "/home/patch/griode/" or die $!;

# Check for command pipe
my $cmdPipe = '.griode.commands';
if(! -p $cmdPipe ){
    -e $cmdPipe and unlink $cmdPipe; # Some file where pipe will be created
    print `mkfifo $cmdPipe`;
}

# Check griode is running
my $pid = `cat .griode.pid`;
my $running = grep{/^$pid\s/} `ps x`;
if(!$running){
    my $griode_cmd = 'LOG_LEVEL=DEBUG GRIODE_AUDIO_DRIVER=jack' .
	'  ./griode.py 2>&1 |tee /tmp/griode.log';
    my $p = fork();

    if($p == 0) {
	# Child
	`$griode_cmd`;
	exit;
    }
}

# Check if jack running
my $res =`jack_wait -c 2>/dev/null`;
chomp $res;
$res eq "running" or die "Jack is not running\n";

# wait fo all ports to become available
my $fs_j_left = 'fluidsynth:left';
my $fs_j_right = 'fluidsynth:right';
while(1) {
    my $i = 0; 

    my $fs_l = grep {/$fs_j_left/} `jack_lsp`;
    my $fs_r = grep {/$fs_j_right/} `jack_lsp`;
    $fs_l and $fs_r and last;
    $i > 10 and die "Jack not set up for fluidsynth\n";
    sleep 1;
    $i++;
}
print "Griode/Fluidsynth operating\n";

my $jack_left_command = "jack_connect $fs_j_left system:playback_1";
my $jack_right_command = "jack_connect $fs_j_right system:playback_2";


print `$jack_left_command 2>&1 `;
print `$jack_right_command 2>&1 `;

wait;

# Clean up
unlink($cmdPipe);


