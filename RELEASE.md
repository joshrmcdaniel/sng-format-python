# v1.3.0
================================================================================
Features
- Convert .wav, .ogg, and .mp3 files to .opus during encoding
  - Encoding is done in parallel
  - You can do specify encoding on the cli with the `-e` option, defaults to `False`

Bug fixes:
- Fix illegal char validation
- Various other things

TODO:
- clean up writing of encoded media
- support multiple sng file decoding in parallel?