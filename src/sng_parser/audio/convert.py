from io import BytesIO
import soundfile as sf

def to_opus(filepath: str) -> BytesIO:
    filename, ext = filepath.split('.')
    with sf.SoundFile(filepath, 'r') as f:
        out = BytesIO()
        out.name = filename+'.opus'
        with sf.SoundFile(out, 'w', samplerate=f.samplerate, channels=f.channels, format='ogg', subtype='Opus', endian=f.endian) as g:
            g.write(f.read())
    out.seek(0)
    return out