import sys
import tempfile
import time
from signal import SIGINT
from multiprocessing import Process

from nose import SkipTest

from zmq.tests import BaseZMQTestCase

from IPython.external.decorator import decorator

from IPython.zmq.parallel import error
from IPython.zmq.parallel.client import Client
from IPython.zmq.parallel.ipcluster import launch_process
from IPython.zmq.parallel.entry_point import select_random_ports
from IPython.zmq.parallel.tests import processes,add_engines

# simple tasks for use in apply tests

def segfault():
    """this will segfault"""
    import ctypes
    ctypes.memset(-1,0,1)

def wait(n):
    """sleep for a time"""
    import time
    time.sleep(n)
    return n

def raiser(eclass):
    """raise an exception"""
    raise eclass()

# test decorator for skipping tests when libraries are unavailable
def skip_without(*names):
    """skip a test if some names are not importable"""
    @decorator
    def skip_without_names(f, *args, **kwargs):
        """decorator to skip tests in the absence of numpy."""
        for name in names:
            try:
                __import__(name)
            except ImportError:
                raise SkipTest
        return f(*args, **kwargs)
    return skip_without_names


def setup():
    add_engines(2)

class ClusterTestCase(BaseZMQTestCase):
    
    def add_engines(self, n=1, block=True):
        """add multiple engines to our cluster"""
        self.engines.extend(add_engines(n))
        if block:
            self.wait_on_engines()
    
    def wait_on_engines(self, timeout=5):
        """wait for our engines to connect."""
        n = len(self.engines)+self.base_engine_count
        tic = time.time()
        while time.time()-tic < timeout and len(self.client.ids) < n:
            time.sleep(0.1)
        
        assert not len(self.client.ids) < n, "waiting for engines timed out"
    
    def connect_client(self):
        """connect a client with my Context, and track its sockets for cleanup"""
        c = Client(profile='iptest', context=self.context)
        # c._iopub_socket.close()
        # for name in filter(lambda n:n.endswith('socket'), dir(c)):
        #     self.sockets.append(getattr(c, name))
        return c
    
    def assertRaisesRemote(self, etype, f, *args, **kwargs):
        try:
            try:
                f(*args, **kwargs)
            except error.CompositeError as e:
                e.raise_exception()
        except error.RemoteError as e:
            self.assertEquals(etype.__name__, e.ename, "Should have raised %r, but raised %r"%(e.ename, etype.__name__))
        else:
            self.fail("should have raised a RemoteError")
            
    def setUp(self):
        BaseZMQTestCase.setUp(self)
        self.client = self.connect_client()
        self.base_engine_count=len(self.client.ids)
        self.engines=[]
    
    def tearDown(self):
        self.client.clear(block=True)
        # close fds:
        for e in filter(lambda e: e.poll() is not None, processes):
            processes.remove(e)
        
        # allow flushing of incoming messages to prevent crash on socket close
        self.client.wait(timeout=2)
        time.sleep(0.1)
        self.client.spin()
        # self.client.close()
        BaseZMQTestCase.tearDown(self)
        # this will be redundant when pyzmq merges PR #88
        self.context.term()
        # print tempfile.TemporaryFile().fileno(),
        # sys.stdout.flush()
        