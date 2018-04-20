#!/bin/sh
for N in $(seq 1 8);
do
	[ -f songs/$N.mid ] || continue
	./mid2loop.py songs/$N.mid 1 $N 2
	./mid2loop.py songs/$N.mid 2 $N 4
done
