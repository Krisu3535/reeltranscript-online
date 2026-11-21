"""Best-effort access to authorized Facebook media, then local Whisper transcription.

No Facebook credentials, cookies, proxy rotation or pay-per-use transcription API.
"""
from __future__ import annotations
from pathlib import Path
import subprocess
import tempfile
from core import make_srt, normalize_facebook_url

MAX_DURATION_SECONDS = 10 * 60
MAX_FILE_BYTES = 60 * 1024 * 1024

class TooLongError(Exception):
    pass

def inspect_duration(path: Path) -> float | None:
    try:
        proc=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration',
            '-of','default=noprint_wrappers=1:nokey=1',str(path)],
            capture_output=True,text=True,timeout=15,check=False)
        return float(proc.stdout.strip()) if proc.returncode==0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None

def download_audio(url: str, directory: Path) -> tuple[Path,str]:
    safe_url=normalize_facebook_url(url)
    if not safe_url:
        raise ValueError('Invalid Facebook link.')
    from yt_dlp import YoutubeDL

    def check_duration(info: dict, *, incomplete: bool=False):
        if info.get('duration') is not None and float(info['duration'])>MAX_DURATION_SECONDS:
            return 'Video exceeds the 10-minute safety limit.'
        return None

    opts={
        'format':'bestaudio/best',
        'outtmpl':str(directory/'source.%(ext)s'),
        'noplaylist':True,'quiet':True,'no_warnings':True,
        'retries':1,'fragment_retries':1,'socket_timeout':20,
        'max_filesize':MAX_FILE_BYTES,'skip_unavailable_fragments':False,
        'match_filter':check_duration,
        'postprocessors':[{'key':'FFmpegExtractAudio','preferredcodec':'mp3','preferredquality':'5'}],
    }
    # No cookiesfrombrowser, cookiefile, account login, proxy, or bypass options.
    with YoutubeDL(opts) as dl:
        metadata=dl.extract_info(safe_url,download=True)
    if not metadata:
        raise RuntimeError('Facebook did not provide an accessible audio stream.')
    if metadata.get('duration') and float(metadata['duration'])>MAX_DURATION_SECONDS:
        raise TooLongError('Video exceeds the 10-minute safety limit.')
    found=list(directory.glob('source*.mp3'))
    if not found:
        raise RuntimeError('No audio retrieved; video may require login or block automated access.')
    audio=found[0]
    if audio.stat().st_size>MAX_FILE_BYTES:
        raise RuntimeError('Audio exceeds the 60 MB safety limit.')
    duration=inspect_duration(audio)
    if duration is not None and duration>MAX_DURATION_SECONDS:
        raise TooLongError('Video exceeds the 10-minute safety limit.')
    return audio,str(metadata.get('title') or 'Facebook video')[:200]

def process_video(url: str, model, language: str | None='en') -> dict:
    result={'url':url,'title':'','status':'failed','language':'',
            'transcript':'','error':'','srt':''}
    try:
        with tempfile.TemporaryDirectory(prefix='reel_audio_') as folder:
            audio,result['title']=download_audio(url,Path(folder))
            segments_iter,info=model.transcribe(
                str(audio),language=language,beam_size=1,
                vad_filter=True,condition_on_previous_text=False)
            segments=[{'start':s.start,'end':s.end,'text':s.text.strip()}
                      for s in segments_iter if s.text.strip()]
            result['transcript']=' '.join(item['text'] for item in segments)
            result['srt']=make_srt(segments)
            result['language']=str(getattr(info,'language',language or ''))
            if result['transcript']:
                result['status']='done'
            else:
                result['error']='No recognizable speech detected.'
    except TooLongError as ex:
        result['status']='skipped'
        result['error']=str(ex)
    except Exception as ex:
        result['error']=str(ex).strip()[:250] or type(ex).__name__
    return result
