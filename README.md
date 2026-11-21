# ReelTranscript Online

Browser-based bulk Facebook Reels/video transcription. Paste up to **500 links** and export transcripts as **CSV**, individual **TXT files**, and **SRT subtitles**. Runs the free open-source `faster-whisper` model; no paid transcription API.

> **Status:** Source published to GitHub. Streamlit hosting must be activated separately; a repository is not a live website. Facebook URL access is best-effort and has not been confirmed for the two sample Facebook links.

## Free hosting: Streamlit Community Cloud

1. Visit https://share.streamlit.io and sign in with your GitHub account.
2. Create a new app from repository **Krisu3535/reeltranscript-online**, branch **main**, entrypoint **app.py**.
3. In the app's **Advanced settings → Secrets** (or its settings after deployment), configure:
   ```toml
   APP_PASSWORD = "choose-a-long-unique-password"
   ```
   Use a password created for this app, **not** your Facebook, GitHub or email password. **Never commit a real secrets.toml**.
4. Deploy, open the resulting `*.streamlit.app` URL and enter your app password.
5. Test with **2–5 public Facebook videos you have permission to download**, starting with a `5 videos` batch.
6. Download `transcripts.csv`, `subtitles_srt.zip` and `checkpoint.csv`. Save checkpoint frequently and use it to resume after server restarts.

The app will refuse to run until `APP_PASSWORD` is set. It does not ask for Facebook credentials or browser cookies.

## Limitations

- Free cloud CPU/RAM may be insufficient for large runs. **500 videos are not guaranteed** to complete for free or in one session.
- The app currently uses `yt-dlp` for accessible Facebook audio. Facebook may reject `/share/r/` and `/share/v/` links even when TurboScribe handles them.
- Individual video limit: 10 minutes, 60 MB downloaded audio. Smaller batches (5, then 25) are safer on free hosting.
- A cloud restart can delete unfinished queue/results. Download checkpoint CSV regularly.
- Only process content you own or have permission to download. Facebook restricts unauthorized automated collection, including when no login is used.
- Transcripts are held temporarily in server memory. Hosting provider infrastructure processes the retrieved files. No login cookies, paid AI API, account scraping workaround or proxy rotation are included.

## Repository structure

- `app.py`: Streamlit web UI, login gate, progress and exports
- `core.py`: URL filtering, CSV/TXT/SRT/checkpoint helpers
- `jobs.py`: resumable in-memory queue
- `transcriber.py`: yt-dlp audio retrieval and local faster-whisper processing
- `requirements.txt`: Python dependencies
- `packages.txt`: FFmpeg system dependency
- `.streamlit/config.toml`: theme
- `.streamlit/secrets.toml.example`: password configuration example (not a real secret)
- `tests/`: mocked offline checks
- `.github/workflows/tests.yml`: automated checks on pushes

## Run locally

Install Python 3.11+, FFmpeg and:
```bash
python -m pip install -r requirements.txt
export APP_PASSWORD="your-long-unique-app-password"
streamlit run app.py
```
On Windows, set `APP_PASSWORD` with PowerShell `$env:APP_PASSWORD="..."` instead of `export`.

## Tests

```bash
python -m unittest discover -s tests -v
```

These offline checks use mocked media; they do **not** prove that Facebook video URLs work from the hosting provider. The application is not affiliated with Meta or TurboScribe.
