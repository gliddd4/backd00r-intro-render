#!/bin/bash
# Builds the ending and the full video. Output: out/backd00r-onboarding-full.mp4 and -small.mp4
set -e
E=$(cd "$(dirname "$0")" && pwd)
O=$PWD/out; W=$PWD/work; mkdir -p $O $W/base $W/frames
cd $W/base
cp $E/inputs/ref.rgb.gz $E/inputs/ladder.rgba.gz . && gunzip -f *.gz && cp $E/inputs/stars.txt .
g++ -std=c++17 -O3 -ffast-math -march=native $E/src/ending.cpp -o ending
./ending frame.ppm ladder.rgba 0 0 -1   # makes the sky cache once
N=$(nproc); COUNT=142; FIRST=236; LOOP=160
for w in $(seq 0 $((N-1))); do
  cp -r $W/base $W/w$w
  only=$(python3 -c "print(','.join(str(k) for k in range($COUNT) if k%$N==$w and k!=$COUNT-1)+',$((COUNT-1))')")
  (cd $W && QUICK=1 RATE=20 LOOP_PART=$w/$N python3 -I $E/src/frames.py $W/w$w $W/frames $COUNT $FIRST "$only" $LOOP > $W/w$w.log 2>&1) &
done
wait
ls $W/frames | wc -l
ffmpeg -hide_banner -loglevel error -y -framerate 20 -pattern_type glob -i "$W/frames/f*.jpg" -framerate 20 -stream_loop 1 -i $W/frames/loop%03d.jpg -filter_complex "[0:v][1:v]concat=n=2:v=1[o]" -map "[o]" -pix_fmt yuv420p -c:v libx264 -crf 18 $W/e.mp4
python3 -I $E/fx/twods.py $W/e.mp4 $O/backd00r-ending.mp4
python3 -I $E/fx/g_look.py $E/highway $W/g
ffmpeg -hide_banner -loglevel error -y -framerate 5 -pattern_type glob -i "$W/g/f*.jpg" -vf "fps=20,format=yuv420p" -c:v libx264 -crf 18 $W/g.mp4
CUT=${CUT:-11.8}
ffmpeg -hide_banner -loglevel error -y -i $W/g.mp4 -i $O/backd00r-ending.mp4 -filter_complex "[0:v]trim=0:$CUT,setpts=PTS-STARTPTS,fps=20,scale=1080:2340,setsar=1[a];[1:v]fps=20,scale=1080:2340,setsar=1[b];[a][b]concat=n=2:v=1[o]" -map "[o]" -c:v libx264 -crf 23 -pix_fmt yuv420p -movflags +faststart -preset veryfast $O/backd00r-onboarding-full.mp4
ffmpeg -hide_banner -loglevel error -y -i $O/backd00r-onboarding-full.mp4 -vf scale=540:-2 -c:v libx264 -crf 26 -preset veryfast -movflags +faststart $O/backd00r-onboarding-full-small.mp4
ls -la $O
