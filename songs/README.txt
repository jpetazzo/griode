Shell scripts to set up the instrument

Send commands to griode:
cat <<EOF > ../.griode.commands
scale [0, 3, 6, 7, 10]
instrument 1 0 1126 Chords
draw
EOF


