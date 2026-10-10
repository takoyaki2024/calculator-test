# Original synthetic playback fixture

`baseline.mp4`: 6 seconds, 160x90, 10 fps, H.264 baseline/yuv420p video and AAC
mono 44.1 kHz audio (440 Hz sine). Original machine-generated test pattern/tone;
no third-party or user media. Released under CC0 for tests.

Generated once using the development environment's existing ffmpeg:

```sh
ffmpeg -f lavfi -i 'testsrc2=size=160x90:rate=10' \
  -f lavfi -i 'sine=frequency=440:sample_rate=44100' -t 6 \
  -c:v libx264 -profile:v baseline -pix_fmt yuv420p -g 10 \
  -c:a aac -b:a 32k -movflags +faststart baseline.mp4
```

No fixture generation or FFmpeg executable is needed by the application/CI.

`work-red.mp4` and `work-blue.mp4`: original CC0 synthetic solid-color clips,
one second, 64x64, H.264/yuv420p, no audio. These verify that different work
references produce different real decoded frames, including the packaged worker.
Generated once using the development environment's ffmpeg color source; no real
user or third-party media is included.
