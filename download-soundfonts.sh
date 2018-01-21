#!/bin/sh

# General User
URL="https://www.dropbox.com/s/4x27l49kxcwamp5/GeneralUser_GS_1.471.zip?dl=1"
ARCHIVE="generaluser.zip"
FILEPATH="GeneralUser GS 1.471/GeneralUser GS v1.471.sf2" 
FILENAME="generaluser.sf2"
if ! [ -f "$FILENAME" ]; then
	if ! [ -f "$ARCHIVE" ]; then
		curl -L -o "$ARCHIVE" "$URL"
	fi
	unzip -p "$ARCHIVE" "$FILEPATH" > "$FILENAME"
	rm "$ARCHIVE"
fi

# Fluid SoundFont
URL="http://http.debian.net/debian/pool/main/f/fluid-soundfont/fluid-soundfont_3.1.orig.tar.gz"
ARCHIVE="fluidsoundfont.tgz"
FILEPATH="fluid-soundfont-3.1/FluidR3_GM.sf2"
FILENAME="fluidsoundfont.sf2"

if ! [ -f "$FILENAME" ]; then
	if ! [ -f "$ARCHIVE" ]; then
		curl -L -o "$ARCHIVE" "$URL"
	fi
	tar -Ozxf "$ARCHIVE" "$FILEPATH" > "$FILENAME"
	rm "$ARCHIVE"
fi

