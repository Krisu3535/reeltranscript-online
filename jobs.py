"""Run one background transcription queue at a time; transient in-memory checkpoints."""
from __future__ import annotations
from dataclasses import dataclass, field
import threading
import time
from typing import Callable
from transcriber import process_video

@dataclass
class Job:
    urls:list[str]=field(default_factory=list)
    results:dict=field(default_factory=dict)
    state:str='idle'
    current:str=''
    processed_this_run:int=0
    planned_this_run:int=0
    message:str=''
    last_active:float=field(default_factory=time.time)
    stop_event:threading.Event=field(default_factory=threading.Event)
    lock:threading.RLock=field(default_factory=threading.RLock)

    def snapshot(self)->dict:
        with self.lock:
            return {'urls':list(self.urls),'results':{k:dict(v) for k,v in self.results.items()},
                    'state':self.state,'current':self.current,
                    'processed_this_run':self.processed_this_run,
                    'planned_this_run':self.planned_this_run,'message':self.message}

class JobManager:
    def __init__(self, *,model_factory:Callable|None=None,processor:Callable|None=None):
        self.jobs:dict[str,Job]={}
        self.lock=threading.RLock()
        self.model_lock=threading.RLock()
        self.models:dict[str,object]={}
        self.active_token:str|None=None
        self.model_factory=model_factory or self.default_model_factory
        self.processor=processor or process_video

    @staticmethod
    def default_model_factory(name:str):
        from faster_whisper import WhisperModel
        return WhisperModel(name,device='cpu',compute_type='int8',cpu_threads=2,num_workers=1)

    def get_model(self,name:str):
        with self.model_lock:
            if name not in self.models:
                self.models[name]=self.model_factory(name)
            return self.models[name]

    def get_or_create(self,token:str)->Job:
        with self.lock:
            self.prune_locked()
            if token not in self.jobs:
                self.jobs[token]=Job()
            self.jobs[token].last_active=time.time()
            return self.jobs[token]

    def prune_locked(self):
        cutoff=time.time()-86400
        for token,job in list(self.jobs.items()):
            if job.state!='running' and job.last_active<cutoff:
                self.jobs.pop(token,None)

    def snapshot(self,token:str)->dict:
        return self.get_or_create(token).snapshot()

    def stop(self,token:str):
        self.get_or_create(token).stop_event.set()

    def start(self,token:str,urls:list[str],prior:dict,*,model_name:str,
              language:str|None,limit:int,retry_failed:bool=False)->int:
        if model_name not in ('tiny','base') or limit<1 or limit>500:
            raise ValueError('Invalid processing configuration.')
        job=self.get_or_create(token)
        with self.lock:
            if self.active_token is not None:
                raise RuntimeError('The server is already processing a batch. Try later.')
            with job.lock:
                if job.state=='running':
                    raise RuntimeError('Your batch is already running.')
                job.results.update({key:dict(val) for key,val in prior.items()})
                job.urls=list(urls)
                pending=[url for url in urls if url not in job.results or
                         (retry_failed and job.results[url].get('status')=='failed')]
                queue=pending[:limit]
                if not queue:
                    return 0
                job.state='running'
                job.current=''
                job.processed_this_run=0
                job.planned_this_run=len(queue)
                job.message='Loading speech model…'
                job.stop_event.clear()
                self.active_token=token
            worker=threading.Thread(target=self._run,args=(token,queue,model_name,language),
                                    name='reel-transcriber',daemon=True)
            try:
                worker.start()
            except Exception:
                self.active_token=None
                with job.lock:
                    job.state='error'
                    job.message='Could not start background worker.'
                raise
            return len(queue)

    def _run(self,token:str,queue:list[str],model_name:str,language:str|None):
        job=self.jobs[token]
        manager=self
        class LazyModel:
            # Load the Whisper model only if a video actually downloads.
            # Facebook access errors should not waste time downloading model weights.
            def transcribe(self,*args,**kwargs):
                return manager.get_model(model_name).transcribe(*args,**kwargs)
        try:
            model=LazyModel()
            for i,url in enumerate(queue,start=1):
                if job.stop_event.is_set():
                    break
                with job.lock:
                    job.current=url
                    job.message=f'Processing video {i} of {len(queue)}'
                result=self.processor(url,model,language)
                with job.lock:
                    job.results[url]=result
                    job.processed_this_run=i
                    job.last_active=time.time()
            with job.lock:
                stopped=job.stop_event.is_set()
                job.state='stopped' if stopped else 'complete'
                job.message='Stopped after current video.' if stopped else 'Batch finished; download results and checkpoint.'
        except Exception as ex:
            with job.lock:
                job.state='error'
                job.message=f'Processing interrupted: {str(ex)[:160]}'
        finally:
            with job.lock:
                job.current=''
            with self.lock:
                if self.active_token==token:
                    self.active_token=None
