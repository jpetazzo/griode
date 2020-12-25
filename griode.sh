#!/bin/perl -w
use strict;
chdir "/home/patch/griode/" or die $!;
my $griode_cmd = 'LOG_LEVEL=DEBUG GRIODE_AUDIO_DRIVER=jack ./griode.py 2>&1 |tee /tmp/griode.log';
my $jack_left_command = 'jack_connect fluidsynth:left system:playback_1';
my $jack_right_command = 'jack_connect fluidsynth:right system:playback_2';
my $pid = fork();

print `jack_wait -w` ;
if($pid == 0) {
    # Child
    `$griode_cmd`;
    exit;
}
sleep 3;

`echo FooBar >> /tmp/griode2.log`;
print `$jack_left_command 2>&1 |tee -a /tmp/griode2.log`;
print `$jack_right_command 2>&1 |tee -a /tmp/griode2.log`;
wait;



