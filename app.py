"""ReelTranscript: browser-based, password-protected Facebook transcription workspace."""
from __future__ import annotations

import hmac
import os
import secrets
import streamlit as st
from core import MAX_URLS, export_csv, export_zip, extract_links, import_checkpoint
from jobs import JobManager

st.set_page_config(page_title='ReelTranscript · Facebook Bulk Transcriber',
                   page_icon='🎙️',layout='wide')

@st.cache_resource(show_spinner=False)
def manager()->JobManager:
    return JobManager()

def check_password():
    expected=os.getenv('APP_PASSWORD','')
    try:
        expected=st.secrets.get('APP_PASSWORD',expected)
    except Exception:
        pass
    if not expected:
        st.error('App locked: Configure APP_PASSWORD in Streamlit Secrets before using the website.')
        st.info('App settings → Secrets → APP_PASSWORD = "your-own-long-unique-password". Do not use your Facebook password.')
        st.stop()
    if st.session_state.get('authenticated'):
        return
    st.title('🔒 Private transcription workspace')
    attempt=st.text_input('App password (NOT your Facebook password)',type='password')
    if not hmac.compare_digest(attempt,expected):
        st.info('Enter your app password to unlock the workspace.')
        st.stop()
    st.session_state.authenticated=True
    st.rerun()

def get_job_token()->str:
    if 'job_token' not in st.session_state:
        st.session_state.job_token=secrets.token_urlsafe(32)
    return st.session_state.job_token

def display_progress(token:str):
    state=manager().snapshot(token)
    results=state['results']
    done=sum(x.get('status')=='done' for x in results.values())
    failures=sum(x.get('status')=='failed' for x in results.values())
    skipped=sum(x.get('status')=='skipped' for x in results.values())
    cols=st.columns(4)
    cols[0].metric('Links entered',len(state['urls']))
    cols[1].metric('Transcribed',done)
    cols[2].metric('Failed',failures)
    cols[3].metric('Skipped',skipped)
    if state['state']=='running':
        planned=max(state['planned_this_run'],1)
        st.progress(state['processed_this_run']/planned,
                    text=f"{state['processed_this_run']} / {planned} processed — {state['message']}")
        if state['current']:
            st.caption('Current: '+state['current'][:130])
        if st.button('⏹ Stop after current video',key='stop_worker'):
            manager().stop(token)
            st.warning('Stop requested. Current video will finish first.')
    elif state['state'] in ('complete','stopped'):
        st.success(state['message'])
    elif state['state']=='error':
        st.error(state['message'])
    else:
        st.info('No active job. Add URLs and click Start.')
    if results:
        preview=[{
            'Status':obj.get('status',''),
            'Title':obj.get('title',''),
            'Source URL':url,
            'Transcript preview':(obj.get('transcript') or '')[:160],
            'Error':obj.get('error',''),
        } for url,obj in results.items()]
        st.dataframe(preview,use_container_width=True,hide_index=True)
        a,b=st.columns(2)
        with a:
            st.download_button('⬇ Download transcripts.csv',export_csv(results),
                               file_name='transcripts.csv',mime='text/csv',use_container_width=True)
            st.download_button('⬇ Download TXT transcripts.zip',export_zip(results,'txt'),
                               file_name='transcripts_txt.zip',mime='application/zip',use_container_width=True)
        with b:
            st.download_button('💾 Save checkpoint.csv',export_csv(results,checkpoint=True),
                               file_name='checkpoint.csv',mime='text/csv',use_container_width=True)
            st.download_button('⬇ Download SRT subtitles.zip',export_zip(results,'srt'),
                               file_name='subtitles_srt.zip',mime='application/zip',use_container_width=True)
        st.caption('Save checkpoint.csv regularly. Cloud restarts can erase unfinished work.')

@st.fragment(run_every='3s')
def live_dashboard(token:str):
    display_progress(token)

def main():
    check_password()
    token=get_job_token()
    st.title('🎙️ ReelTranscript')
    st.markdown('**Facebook Reel and video transcripts, in your browser.**')
    st.caption('Up to 500 Facebook URLs · automatic queue · free AI model · CSV, TXT and SRT')
    st.warning('Only process videos you own or have permission to download. Facebook may reject automated access. No Facebook login or cookies are used.')

    left,right=st.columns([1.7,1],gap='large')
    with left:
        st.subheader('① Add video URLs')
        pasted=st.text_area('One link per line (or paste a list)',height=195,
                            placeholder='https://www.facebook.com/share/r/REEL_ID/\nhttps://www.facebook.com/share/v/VIDEO_ID/')
        uploaded=st.file_uploader('Optional: upload TXT or CSV containing links',type=['txt','csv'])
        extra=''
        if uploaded:
            if uploaded.size>2*1024*1024:
                st.error('URL list must be smaller than 2 MB.')
            else:
                extra=uploaded.getvalue().decode('utf-8-sig',errors='replace')
        urls=extract_links(pasted+'\n'+extra)
        st.caption(f'**{len(urls)} unique Facebook links loaded** (maximum {MAX_URLS}). Tracking parameters are removed.')
    with right:
        st.subheader('② Settings')
        model_name=st.selectbox('Transcription quality',['tiny','base'],
                                index=0,format_func=lambda x:'Fast · Tiny' if x=='tiny' else 'Better · Base')
        lang=st.selectbox('Spoken language',['English','Auto-detect'])
        language='en' if lang=='English' else None
        count_option=st.selectbox('Process per run',[5,25,100,500],
                                  format_func=lambda x:f'{x} videos'+(' (recommended test)' if x==5 else ''))
        retry_failed=st.checkbox('Retry previously failed URLs')
        consent=st.checkbox('I own these videos or have permission to download and transcribe them.')
        st.caption('Individual video limit: 10 minutes and 60 MB of downloaded audio.')
        if st.button('▶ Start transcription',type='primary',use_container_width=True,
                     disabled=not urls or not consent):
            prior=manager().snapshot(token)['results']
            try:
                count=manager().start(token,urls,prior,model_name=model_name,
                                      language=language,limit=count_option,retry_failed=retry_failed)
                if not count:
                    st.info('Nothing new to transcribe. Enable retry for failures.')
                else:
                    st.success(f'Started a batch of {count} videos.')
            except (ValueError,RuntimeError) as ex:
                st.error(str(ex))

    with st.expander('↩ Resume from a previous checkpoint.csv'):
        checkpoint=st.file_uploader('Select checkpoint.csv',type=['csv'],key='checkpoint')
        if st.button('Import checkpoint',disabled=checkpoint is None):
            if manager().snapshot(token)['state']=='running':
                st.error('Stop your running batch before importing a checkpoint.')
            else:
                try:
                    restored=import_checkpoint(checkpoint.getvalue())
                    job=manager().get_or_create(token)
                    with job.lock:
                        job.results.update(restored)
                    st.success(f'Restored {len(restored)} videos. Re-paste URLs and continue.')
                except (ValueError,UnicodeError) as ex:
                    st.error(str(ex))
    st.subheader('③ Live progress and downloads')
    live_dashboard(token)
    st.divider()
    st.caption('Free cloud hosting may restart or sleep. Save checkpoints often. '
               'For reliable 500-video jobs use a dedicated server. Not affiliated with Meta or TurboScribe.')

if __name__=='__main__':
    main()
