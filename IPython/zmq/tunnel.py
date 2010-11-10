

#-----------------------------------------
# Imports
#-----------------------------------------

from __future__ import print_function

import os,sys, atexit
from multiprocessing import Process
from getpass import getpass, getuser

try:
    import paramiko
except ImportError:
    paramiko = None
else:
    from forward import forward_tunnel

try:
    from IPython.external import pexpect
except ImportError:
    pexpect = None

from IPython.zmq.parallel.entry_point import select_random_ports

#----------------------------------------------------
# Code
#----------------------------------------------------

#--------- check for passwordless login ----------
def try_passwordless_ssh(server, keyfile, paramiko=None):
    if paramiko is None:
        paramiko = sys.platform == 'win32'
    if not paramiko:
        f = _try_passwordless_openssh
    else:
        f = _try_passwordless_paramiko
    return f(server, keyfile)

def _try_passwordless_openssh(server, keyfile):
    cmd = 'ssh -f '+ server
    if keyfile:
        cmd += ' -i ' + keyfile
    cmd += ' exit'
    p = pexpect.spawn(cmd)
    while True:
        try:
            p.expect('[Ppassword]:', timeout=.1)
        except pexpect.TIMEOUT:
            continue
        except pexpect.EOF:
            return True
        else:
            return False

def _try_passwordless_paramiko(server, keyfile):
    username, server, port = _split_server(server)
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.WarningPolicy())
    try:
        client.connect(server, port, username=username, key_filename=keyfile,
               look_for_keys=True)
    except paramiko.AuthenticationException:
        return False
    else:
        client.close()
        return True


def tunnel_connection(socket, addr, server, keyfile=None, password=None, paramiko=None):
    lport = select_random_ports(1)[0]
    transport, addr = addr.split('://')
    ip,rport = addr.split(':')
    rport = int(rport)
    if paramiko is None:
        paramiko = sys.platform == 'win32'
    if paramiko:
        tunnelf = paramiko_tunnel
    else:
        tunnelf = openssh_tunnel
    tunnel = tunnelf(lport, rport, server, remoteip=ip, keyfile=keyfile, password=password)
    socket.connect('tcp://127.0.0.1:%i'%lport)
    return tunnel

def openssh_tunnel(lport, rport, server, remoteip='127.0.0.1', keyfile=None, password=None, timeout=15):
    """Create an ssh tunnel using command-line ssh that connects port lport
    on this machine to localhost:rport on server.  The tunnel
    will automatically close when not in use, remaining open
    for a minimum of timeout seconds for an initial connection.
    """
    if pexpect is None:
        raise ImportError("pexpect unavailable, use paramiko_tunnel")
    ssh="ssh "
    if keyfile:
        ssh += "-i " + keyfile 
    cmd = ssh + " -f -L 127.0.0.1:%i:127.0.0.1:%i %s sleep %i"%(lport, rport, server, timeout)
    tunnel = pexpect.spawn(cmd)
    failed = False
    while True:
        try:
            tunnel.expect('[Pp]assword:', timeout=.1)
        except pexpect.TIMEOUT:
            continue
        except pexpect.EOF:
            if tunnel.exitstatus:
                print (tunnel.exitstatus)
                print (tunnel.before)
                print (tunnel.after)
                raise RuntimeError("tunnel '%s' failed to start"%(cmd))
            else:
                return tunnel.pid
        else:
            if failed:
                print("Password rejected, try again")
                password=None
            if password is None:
                password = getpass("%s's password: "%(server))
            tunnel.sendline(password)
            failed = True
    
def _split_server(server):
    if '@' in server:
        username,server = server.split('@', 1)
    else:
        username = getuser()
    if ':' in server:
        server, port = server.split(':')
        port = int(port)
    else:
        port = 22
    return username, server, port

def paramiko_tunnel(lport, rport, server, remoteip='127.0.0.1', keyfile=None, password=None, timeout=15):
    """launch a tunner with paramiko in a subprocess. This should only be used
    when shell ssh is unavailable (e.g. Windows).
    """
    if paramiko is None:
        raise ImportError("Paramiko not available")
    
    if password is None:
        if not _check_passwordless_paramiko(server, keyfile):
            password = getpass("%s's password: "%(server))

    p = Process(target=_paramiko_tunnel, 
            args=(lport, rport, server, remoteip), 
            kwargs=dict(keyfile=keyfile, password=password))
    p.daemon=False
    p.start()
    atexit.register(_shutdown_process, p)
    return p
    
def _shutdown_process(p):
    if p.isalive():
        p.terminate()

def _paramiko_tunnel(lport, rport, server, remoteip, keyfile=None, password=None):
    """function for actually starting a paramiko tunnel, to be passed
    to multiprocessing.Process(target=this).
    """
    username, server, port = _split_server(server)
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.WarningPolicy())

    try:
        client.connect(server, port, username=username, key_filename=keyfile,
                       look_for_keys=True, password=password)
#    except paramiko.AuthenticationException:
#        if password is None:
#            password = getpass("%s@%s's password: "%(username, server))
#            client.connect(server, port, username=username, password=password)
#        else:
#            raise
    except Exception as e:
        print ('*** Failed to connect to %s:%d: %r' % (server, port, e))
        sys.exit(1)

    # print ('Now forwarding port %d to %s:%d ...' % (lport, server, rport))

    try:
        forward_tunnel(lport, remoteip, rport, client.get_transport())
    except KeyboardInterrupt:
        print ('SIGINT: Port forwarding stopped cleanly')
        sys.exit(0)
    except Exception as e:
        print ("Port forwarding stopped uncleanly: %s"%e)
        sys.exit(255)

if sys.platform == 'win32':
    ssh_tunnel = paramiko_tunnel
else:
    ssh_tunnel = openssh_tunnel

    
__all__ = ['tunnel_connection', 'ssh_tunnel', 'openssh_tunnel', 'paramiko_tunnel', 'try_passwordless_ssh']















