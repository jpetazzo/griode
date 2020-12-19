#!/bin/perl -w
use strict;

my $griode_cmd = 'LOG_LEVEL=DEBUG GRIODE_AUDIO_DRIVER=jack ./griode.py 2>&1 |tee /tmp/griode.log';
my $jack_left_command = 'jack_connect fluidsynth:left system:playback_1';
my $jack_right_command = 'jack_connect fluidsynth:right system:playback_2';
my $pid = fork();
if($pid == 0) {
    # Child
    `$griode_cmd`;
    exit;
}
sleep 3;
print `$jack_left_command`;
print `$jack_right_command`;
wait;



