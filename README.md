# sng-format-python
-----------------------
Python implementation for parsing and handling .sng files. [See the .sng format spec for information](https://github.com/mdsitton/SngFileFormat/tree/main).

It is capable of reading SNG files, extracting metadata, file indexes, and file data. There is a function to write to disk as well.

I have not tested this thoroughly, but I've had zero issues with it so far.


## Example usage
```python

import sng_parser

outdir = 'test'

# Decoding
sng_parser.convert_sng_file('example.sng', outdir)

# Encoding
sng_parser.to_sng_file('encoded.sng', outdir)

```