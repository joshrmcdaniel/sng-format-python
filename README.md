# sng-format-python
-----------------------
Python implementation for parsing and handling .sng files. [See the .sng format spec for information](https://github.com/mdsitton/SngFileFormat/tree/main).

It is capable of reading SNG files, extracting metadata, file indexes, and file data. There is a function to write to disk as well.

I have not tested this thoroughly, but I've had zero issues with it so far.


## Example usage
```python

## Decoding
from decode import write_parsed_sng, read_sng_file, parse_sng
outdir = 'test'
sng_file = read_sng_file('example.sng')
parsed_sng = parse_sng(sng_file)
write_parsed_sng(parsed_sng, outdir)

# Encoding
from encode import read_file_meta, encode_sng
xor_bytes = os.urandom(16)
metadata = read_file_meta(outdir)
encode_sng('encoded.sng', outdir, 1, xor_bytes, metadata)

```