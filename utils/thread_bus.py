# Source Generated with Decompyle++
# File: thread_bus.pyc (Python 3.11)

import queue
from typing import Callable

class UiBus:
    '''线程安全的 UI 消息总线：子线程 put，主线程 after 轮询。'''
    
    def __init__(self):
        self.queue = queue.Queue()

    
    def log(self = None, msg = None):
        self.queue.put(('log', msg))

    
    def progress(self = None, value = None, maximum = None):
        self.queue.put(('progress', {
            'value': value,
            'maximum': maximum }))

    
    def info(self = None, title = None, msg = None):
        self.queue.put(('info', (title, msg)))

    
    def error(self = None, title = None, msg = None):
        self.queue.put(('error', (title, msg)))

    
    def done(self):
        self.queue.put(('done', None))

    
    def drain(self = None, handler = None):
        '''从队列中取出所有待处理消息，依次调用 handler(kind, payload)。'''
        if handler is None:
            return
        while True:
            try:
                kind, payload = self.queue.get_nowait()
                handler(kind, payload)
            except Exception:
                break


