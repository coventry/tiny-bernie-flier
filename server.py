import tempfile, BaseHTTPServer, cgi, os, shutil, SocketServer, time
import Queue, threading

logname = '~/bernie-%s.log' % time.ctime().replace(' ', '-')
logname = os.path.expanduser(logname)
logfile = open(logname, 'w')
logqueue = Queue.Queue()
def logwork():
    while True:
        logitem = logqueue.get()
        print >> logfile, logitem
        logfile.flush()
        logqueue.task_done()
# Commit a single thread to logging, so log entries don't overwrite.
logthread = threading.Thread(target=logwork)
logthread.start()
def log(s):
    logqueue.put('%s %s' % (time.ctime(), str(s)))

doctemplate = r'''\documentclass[letterpaper,12pt]{article}

\newcommand{\MeetingTime}{%s}
\newcommand{\MeetingAddress}{%s}
\newcommand{\MeetingPlacename}{%s}
\newcommand{\GroupName}{%s}
\newcommand{\GroupURL}{\tt %s}
\newcommand{\State}{%s}
\newcommand{\PDate}{%s}
\newcommand{\Vote}{%s}
\newcommand{\ContactInfo}{%s}

\input{fulldoc}

\end{document}'''

docvars = ('meetingtime meetingaddress meetingplacename groupname '
           'groupurl state pdate action contactinfo').split()

form = open('form.html').read()

primary_dates = {}
caucus_states = set()
for line in open('primaries.txt'):
    date, states = line.strip().split('\t')
    states = [s.strip() for s in states.split(',')]
    for state in states:
        if 'caucus' in state:
            state = state.replace(' caucus', '')
            caucus_states.add(state)
        assert state not in primary_dates
        primary_dates[state] = ' '.join(date.split())

class RequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.wfile.write(form)
        
    latex_escapes = {
        '&':  r'\&',
        '%':  r'\%', 
        '$':  r'\$', 
        '#':  r'\#', 
        '_':  r'\letterunderscore{}', 
        '{':  r'\letteropenbrace{}', 
        '}':  r'\letterclosebrace{}',
        '~':  r'\lettertilde{}', 
        '^':  r'\letterhat{}', 
        '\\': r'\letterbackslash{}',
    }

    def escape_latex_string(self, s):
        '''Make string safe for processing by LaTeX'''
        return "".join([self.latex_escapes.get(char, char)
                        for char in s])

    def do_POST(self):
        ctype, pdict = cgi.parse_header(self.headers.getheader(
            'content-type'))
        if ctype == 'multipart/form-data':
            postvars = cgi.parse_multipart(self.rfile, pdict)
        elif ctype == 'application/x-www-form-urlencoded':
            length = int(self.headers.getheader('content-length'))
            postvars = cgi.parse_qs(self.rfile.read(length), 
                                    keep_blank_values=1)
        else:
            postvars = {}
        # normalize keys, escape values for latex
        postvars = dict((n.lower(), 
                         self.escape_latex_string(' '.join(v)))
                        for n, v in postvars.items())
        # Make sure every value is non-trivial
        postvars = dict((n, v or n) for n, v in postvars.items())
        postvars['pdate'] = primary_dates.get(postvars['state'], 'Jan 1')
        caucusp = postvars['state'] in caucus_states 
        postvars['action'] = 'Caucus' if caucusp else 'Vote'
        log((self.client_address[0], postvars))
        doc = doctemplate % tuple(postvars.get(n, n) for n in docvars)
        f = tempfile.NamedTemporaryFile(suffix='.tex', dir='.')
        f.write(doc)
        f.flush()
        rmcommand = 'rm -f %s.*' % (f.name[:-4])
        try:
            if os.system('pdflatex ' + f.name):
                raise RuntimeError("Failed to make pdf file")
            self.send_response(200)
            self.send_header('Content-type', 'application/pdf')
            self.end_headers()
            shutil.copyfileobj(open(f.name.replace('.tex', '.pdf')),
                               self.wfile)
            del f
        finally:
            os.system(rmcommand)

class ThreadedHTTPServer(SocketServer.ThreadingMixIn, 
                         BaseHTTPServer.HTTPServer):
    """Handle requests in a separate thread."""

if __name__ == '__main__':
    BaseHTTPServer.test(RequestHandler, ThreadedHTTPServer)
